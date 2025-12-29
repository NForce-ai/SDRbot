"""Task execution and streaming logic for the CLI."""

import asyncio
import json
import re
from collections.abc import Callable

try:
    import termios
    import tty
except ImportError:
    termios = None  # type: ignore
    tty = None  # type: ignore

from langchain.agents.middleware.human_in_the_loop import (
    ApproveDecision,
    Decision,
    HITLRequest,
    HITLResponse,
    RejectDecision,
)
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command, Interrupt
from pydantic import TypeAdapter, ValidationError
from rich.markdown import Markdown as RichMarkdown
from rich.text import Text

from sdrbot_cli.config import COLORS
from sdrbot_cli.file_ops import FileOpTracker
from sdrbot_cli.image_utils import ImageData, create_multimodal_content
from sdrbot_cli.input import parse_file_mentions
from sdrbot_cli.tools import get_schema_modifying_tools
from sdrbot_cli.ui import (
    TokenTracker,
    format_tool_display,
    format_tool_message_content,
    render_file_operation,
)


class Markdown(RichMarkdown):
    """Custom Markdown that uses white bullets instead of orange."""

    def __rich_console__(self, console, options):
        """Override to inject custom styles for bullets."""
        # Temporarily override the bullet style
        original_get_style = console.get_style

        def patched_get_style(name, default=None):
            if name in ("markdown.item.bullet", "markdown.item.number"):
                return console.get_style("white", default=default)
            return original_get_style(name, default=default)

        console.get_style = patched_get_style
        try:
            yield from super().__rich_console__(console, options)
        finally:
            console.get_style = original_get_style


_HITL_REQUEST_ADAPTER = TypeAdapter(HITLRequest)


async def prompt_for_tool_approval(
    ui_callback: Callable | None,
    approval_callback: Callable,
) -> Decision | dict:
    """Prompt user to approve/reject a tool action via the TUI approval bar.

    Returns:
        Decision (ApproveDecision or RejectDecision)
    """
    result = await approval_callback()

    if result == "approve":
        if ui_callback:
            ui_callback(Text.from_markup("  [green]✓ Tool action approved.[/green]", style="dim"))
            ui_callback(Text("\n"))
        return ApproveDecision(type="approve")
    elif result == "auto_approve_all":
        return {"type": "auto_approve_all"}
    else:  # reject
        if ui_callback:
            ui_callback(Text.from_markup("  [red]❌ Tool action rejected.[/red]", style="dim"))
            ui_callback(Text("\n"))
        return RejectDecision(type="reject", message="User rejected the command")


async def execute_task(
    user_input: str,
    agent,
    assistant_id: str | None,
    session_state,
    token_tracker: TokenTracker | None = None,
    backend=None,
    ui_callback: Callable | None = None,
    todo_callback: Callable | None = None,
    approval_callback: Callable | None = None,
    auto_approve_callback: Callable | None = None,
    token_callback: Callable | None = None,
    status_callback: Callable | None = None,
    images: list[ImageData] | None = None,
) -> None:
    """Execute any task by passing it directly to the AI agent.

    Args:
        user_input: The user's text input
        agent: The agent to execute
        assistant_id: Optional assistant identifier
        session_state: Current session state
        token_tracker: Optional token usage tracker
        backend: Optional backend for file operations
        ui_callback: Callback for UI updates
        todo_callback: Callback for todo list updates
        approval_callback: Callback for tool approval requests
        auto_approve_callback: Callback for auto-approve state changes
        token_callback: Callback for token count updates
        status_callback: Callback for status updates
        images: Optional list of images to include in the message (for multimodal)
    """
    # Parse file mentions and inject content if any
    prompt_text, mentioned_files = parse_file_mentions(user_input)

    if mentioned_files:
        context_parts = [prompt_text, "\n\n## Referenced Files\n"]
        for file_path in mentioned_files:
            try:
                content = file_path.read_text()
                # Limit file content to reasonable size
                if len(content) > 50000:
                    content = content[:50000] + "\n... (file truncated)"
                context_parts.append(
                    f"\n### {file_path.name}\nPath: `{file_path}`\n```\n{content}\n```"
                )
            except Exception as e:
                context_parts.append(f"\n### {file_path.name}\n[Error reading file: {e}]")

        final_input = "\n".join(context_parts)
    else:
        final_input = prompt_text

    config = {
        "configurable": {"thread_id": session_state.thread_id},
        "metadata": {"assistant_id": assistant_id} if assistant_id else {},
    }

    # Store status_callback in session_state so middleware can use it (e.g., for "Compacting...")
    session_state._status_callback = status_callback

    has_responded = False
    current_todos = None  # Track current todo list state

    # Status tracker - updates ChatInput placeholder via status_callback
    class DummyStatus:
        def __init__(self):
            self.active = False

        def start(self):
            self.active = True

        def stop(self):
            self.active = False

        def update(self, message: str):
            if status_callback:
                # Strip markup tags for cleaner display
                clean_message = re.sub(r"\[/?[^\]]+\]", "", message)
                status_callback(clean_message)

    status = DummyStatus()
    spinner_active = True

    tool_icons = {
        "read_file": "📖",
        "write_file": "✏️",
        "edit_file": "✂️",
        "ls": "📁",
        "glob": "🔍",
        "grep": "🔎",
        "shell": "⚡",
        "execute": "🔧",
        "http_request": "🌍",
        "task": "🤖",
        "write_todos": "📋",
    }

    file_op_tracker = FileOpTracker(assistant_id=assistant_id, backend=backend)

    # Track schema-modifying tools for auto-reload
    schema_modifying_tools = get_schema_modifying_tools()
    services_to_reload: set[str] = set()

    # Track which tool calls we've displayed to avoid duplicates
    displayed_tool_ids = set()
    # Buffer partial tool-call chunks keyed by streaming index
    tool_call_buffers: dict[str | int, dict] = {}
    # Buffer assistant text so we can render complete markdown segments
    pending_text = ""

    def flush_text_buffer(*, final: bool = False) -> None:
        """Flush accumulated assistant text as rendered markdown when appropriate."""
        nonlocal pending_text, spinner_active, has_responded
        if not final or not pending_text.strip():
            return
        if spinner_active:
            status.stop()
            spinner_active = False
        if not has_responded:
            has_responded = True
        markdown = Markdown(pending_text.rstrip())
        if ui_callback:
            ui_callback(markdown)
        pending_text = ""

    # Stream input - may need to loop if there are interrupts
    # Use multimodal content format if images are attached
    if images:
        message_content = create_multimodal_content(final_input, images)
    else:
        message_content = final_input
    stream_input = {"messages": [{"role": "user", "content": message_content}]}

    try:
        while True:
            interrupt_occurred = False
            hitl_response: dict[str, HITLResponse] = {}
            suppress_resumed_output = False
            # Track all pending interrupts: {interrupt_id: request_data}
            pending_interrupts: dict[str, HITLRequest] = {}

            async for chunk in agent.astream(
                stream_input,
                stream_mode=["messages", "updates"],  # Dual-mode for HITL support
                subgraphs=True,
                config=config,
                durability="exit",
            ):
                # Unpack chunk - with subgraphs=True and dual-mode, it's (namespace, stream_mode, data)
                if not isinstance(chunk, tuple) or len(chunk) != 3:
                    continue

                _namespace, current_stream_mode, data = chunk

                # Handle UPDATES stream - for interrupts and todos
                if current_stream_mode == "updates":
                    if not isinstance(data, dict):
                        continue

                    # Check for interrupts - collect ALL pending interrupts
                    if "__interrupt__" in data:
                        interrupts: list[Interrupt] = data["__interrupt__"]
                        if interrupts:
                            for interrupt_obj in interrupts:
                                # Interrupt has required fields: value (HITLRequest) and id (str)
                                # Validate the HITLRequest using TypeAdapter
                                try:
                                    validated_request = _HITL_REQUEST_ADAPTER.validate_python(
                                        interrupt_obj.value
                                    )
                                    pending_interrupts[interrupt_obj.id] = validated_request
                                    interrupt_occurred = True
                                except ValidationError as e:
                                    if ui_callback:
                                        ui_callback(
                                            Text(
                                                f"[yellow]Warning: Invalid HITL request data: {e}[/yellow]",
                                                style="dim",
                                            )
                                        )
                                    raise

                    # Extract chunk_data from updates for todo checking
                    chunk_data = next(iter(data.values())) if data else None
                    if chunk_data and isinstance(chunk_data, dict):
                        # Check for todo updates
                        if "todos" in chunk_data:
                            new_todos = chunk_data["todos"]
                            if new_todos != current_todos:
                                current_todos = new_todos
                                # Stop spinner before rendering todos
                                if spinner_active:
                                    status.stop()
                                    spinner_active = False
                                if todo_callback:
                                    todo_callback(new_todos)

                # Handle MESSAGES stream - for content and tool calls
                elif current_stream_mode == "messages":
                    # Messages stream returns (message, metadata) tuples
                    if not isinstance(data, tuple) or len(data) != 2:
                        continue

                    message, _metadata = data

                    if isinstance(message, HumanMessage):
                        content = message.text
                        if content:
                            # Show brief notification when compaction completes
                            if content.startswith("[Previous conversation summary]"):
                                if ui_callback:
                                    savings = getattr(session_state, "_last_compaction_savings", 0)
                                    if savings > 0:
                                        # Format savings nicely (e.g., 15000 -> "15k")
                                        if savings >= 1000:
                                            savings_str = f"~{savings // 1000}k"
                                        else:
                                            savings_str = str(savings)
                                        ui_callback(
                                            Text(
                                                f"\n📦 Context compacted (saved {savings_str} tokens)\n",
                                                style="dim",
                                            )
                                        )
                                    else:
                                        ui_callback(Text("\n📦 Context compacted\n", style="dim"))
                                continue
                            flush_text_buffer(final=True)
                            if spinner_active:
                                status.stop()
                                spinner_active = False
                            if not has_responded:
                                has_responded = True
                            markdown = Markdown(content)
                            if ui_callback:
                                ui_callback(markdown)
                        continue

                    if isinstance(message, ToolMessage):
                        # Tool results are sent to the agent, not displayed to users
                        # Exception: show shell command errors to help with debugging
                        tool_name = getattr(message, "name", "")
                        tool_status = getattr(message, "status", "success")
                        tool_content = format_tool_message_content(message.content)
                        record = file_op_tracker.complete_with_message(message)

                        # Track schema-modifying tools for auto-reload
                        # Only trigger if tool succeeded (no error in response)
                        if tool_name in schema_modifying_tools:
                            content_str = str(tool_content) if tool_content else ""
                            if not content_str.lower().startswith("error"):
                                services_to_reload.add(schema_modifying_tools[tool_name])

                        # Reset spinner message after tool completes
                        if spinner_active:
                            status.update(f"[bold {COLORS['thinking']}]Thinking...")

                        if tool_name == "shell" and tool_status != "success":
                            flush_text_buffer(final=True)
                            if tool_content:
                                if spinner_active:
                                    status.stop()
                                    spinner_active = False
                                if ui_callback:
                                    ui_callback(Text(tool_content, style="red"))
                        elif tool_content and isinstance(tool_content, str):
                            stripped = tool_content.lstrip()
                            if stripped.lower().startswith("error"):
                                flush_text_buffer(final=True)
                                if spinner_active:
                                    status.stop()
                                    spinner_active = False
                                if ui_callback:
                                    ui_callback(Text(tool_content, style="red"))

                        if record:
                            flush_text_buffer(final=True)
                            if spinner_active:
                                status.stop()
                                spinner_active = False
                            if ui_callback:
                                for renderable in render_file_operation(record):
                                    ui_callback(renderable)
                            if not spinner_active:
                                status.start()
                                spinner_active = True

                        # For all other tools (http_request, etc.),
                        # results are hidden from user - agent will process and respond
                        continue

                    # Check if this is an AIMessageChunk
                    if not hasattr(message, "content_blocks"):
                        # Fallback for messages without content_blocks
                        continue

                    # Extract token usage if available
                    if token_tracker:
                        input_toks = 0
                        output_toks = 0

                        # Try usage_metadata first (LangChain standard)
                        if hasattr(message, "usage_metadata") and message.usage_metadata:
                            usage = message.usage_metadata
                            input_toks = usage.get("input_tokens", 0)
                            output_toks = usage.get("output_tokens", 0)

                        # Fallback: check response_metadata for OpenAI-compatible endpoints
                        if not (input_toks or output_toks):
                            if hasattr(message, "response_metadata") and message.response_metadata:
                                resp_meta = message.response_metadata
                                # Try common usage locations
                                usage = resp_meta.get("usage") or resp_meta.get("token_usage") or {}
                                # OpenAI format uses prompt_tokens/completion_tokens
                                input_toks = usage.get("input_tokens") or usage.get(
                                    "prompt_tokens", 0
                                )
                                output_toks = usage.get("output_tokens") or usage.get(
                                    "completion_tokens", 0
                                )

                        if input_toks or output_toks:
                            # Update token tracker immediately for real-time UI updates
                            token_tracker.add(
                                input_toks,
                                output_toks,
                                context_input=input_toks,
                                context_output=output_toks,
                            )
                            if token_callback:
                                token_callback(token_tracker.total_session_tokens)

                    # Process content blocks (this is the key fix!)
                    for block in message.content_blocks:
                        block_type = block.get("type")

                        # Handle text blocks
                        if block_type == "text":
                            text = block.get("text", "")
                            if text:
                                pending_text += text

                        # Handle reasoning blocks
                        elif block_type == "reasoning":
                            flush_text_buffer(final=True)
                            reasoning = block.get("reasoning", "")
                            if reasoning and spinner_active:
                                status.stop()
                                spinner_active = False
                                # Could display reasoning differently if desired
                                # For now, skip it or handle minimally

                        # Handle tool call chunks
                        # Some models (OpenAI, Anthropic) stream tool_call_chunks
                        # Others (Gemini) don't stream them and just return the full tool_call
                        elif block_type in ("tool_call_chunk", "tool_call"):
                            chunk_name = block.get("name")
                            chunk_args = block.get("args")
                            chunk_id = block.get("id")
                            chunk_index = block.get("index")

                            # Use index as stable buffer key; fall back to id if needed
                            buffer_key: str | int
                            if chunk_index is not None:
                                buffer_key = chunk_index
                            elif chunk_id is not None:
                                buffer_key = chunk_id
                            else:
                                buffer_key = f"unknown-{len(tool_call_buffers)}"

                            buffer = tool_call_buffers.setdefault(
                                buffer_key,
                                {"name": None, "id": None, "args": None, "args_parts": []},
                            )

                            if chunk_name:
                                buffer["name"] = chunk_name
                            if chunk_id:
                                buffer["id"] = chunk_id

                            if isinstance(chunk_args, dict):
                                buffer["args"] = chunk_args
                                buffer["args_parts"] = []
                            elif isinstance(chunk_args, str):
                                if chunk_args:
                                    parts: list[str] = buffer.setdefault("args_parts", [])
                                    if not parts or chunk_args != parts[-1]:
                                        parts.append(chunk_args)
                                    buffer["args"] = "".join(parts)
                            elif chunk_args is not None:
                                buffer["args"] = chunk_args

                            buffer_name = buffer.get("name")
                            buffer_id = buffer.get("id")
                            if buffer_name is None:
                                continue

                            parsed_args = buffer.get("args")
                            if isinstance(parsed_args, str):
                                if not parsed_args:
                                    continue
                                try:
                                    parsed_args = json.loads(parsed_args)
                                except json.JSONDecodeError:
                                    # Wait for more chunks to form valid JSON
                                    continue
                            elif parsed_args is None:
                                continue

                            # Ensure args are in dict form for formatter
                            if not isinstance(parsed_args, dict):
                                parsed_args = {"value": parsed_args}

                            flush_text_buffer(final=True)
                            if buffer_id is not None:
                                if buffer_id not in displayed_tool_ids:
                                    displayed_tool_ids.add(buffer_id)
                                    file_op_tracker.start_operation(
                                        buffer_name, parsed_args, buffer_id
                                    )
                                else:
                                    file_op_tracker.update_args(buffer_id, parsed_args)
                            tool_call_buffers.pop(buffer_key, None)
                            icon = tool_icons.get(buffer_name, "🔧")

                            if spinner_active:
                                status.stop()

                            if has_responded:
                                if ui_callback:
                                    ui_callback(Text(""))

                            display_str = format_tool_display(buffer_name, parsed_args)
                            if ui_callback:
                                ui_callback(
                                    Text(
                                        f"  {icon} {display_str}",
                                        style=f"dim {COLORS['tool']}",
                                    )
                                )

                            # Update task list panel when write_todos is called
                            if buffer_name == "write_todos":
                                new_todos = parsed_args.get("todos", [])
                                if todo_callback and new_todos:
                                    current_todos = new_todos
                                    todo_callback(new_todos)

                            # Restart spinner
                            status.start()
                            spinner_active = True

                    if getattr(message, "chunk_position", None) == "last":
                        flush_text_buffer(final=True)

            # After streaming loop - handle interrupt if it occurred
            flush_text_buffer(final=True)

            # Handle human-in-the-loop after stream completes
            if interrupt_occurred:
                any_rejected = False

                for interrupt_id, hitl_request in pending_interrupts.items():
                    # Check if auto-approve is enabled
                    if session_state.auto_approve:
                        # Auto-approve all commands without prompting
                        decisions = []
                        for action_request in hitl_request["action_requests"]:
                            # Show what's being auto-approved (brief, dim message)
                            if spinner_active:
                                status.stop()
                                spinner_active = False

                            description = action_request.get("description", "tool action")
                            if ui_callback:
                                ui_callback(Text("\n"))
                            if ui_callback:
                                ui_callback(Text.from_markup(f"  [dim]⚡ {description}[/dim]"))

                            decisions.append({"type": "approve"})

                        hitl_response[interrupt_id] = {"decisions": decisions}

                        # Restart spinner for continuation
                        if not spinner_active:
                            status.start()
                            spinner_active = True
                    else:
                        # Normal HITL flow - stop spinner and prompt user
                        if spinner_active:
                            status.stop()
                            spinner_active = False

                        # Handle human-in-the-loop approval
                        decisions = []
                        for action_index, action_request in enumerate(
                            hitl_request["action_requests"]
                        ):
                            decision = await prompt_for_tool_approval(
                                ui_callback,
                                approval_callback,
                            )

                            # Check if user wants to switch to auto-approve mode
                            if (
                                isinstance(decision, dict)
                                and decision.get("type") == "auto_approve_all"
                            ):
                                # Switch to auto-approve mode
                                session_state.auto_approve = True
                                # Notify UI to update auto-approve indicator
                                if auto_approve_callback:
                                    auto_approve_callback(True)

                                # Approve this action and all remaining actions in the batch
                                decisions.append({"type": "approve"})
                                for _remaining_action in hitl_request["action_requests"][
                                    action_index + 1 :
                                ]:
                                    decisions.append({"type": "approve"})
                                break
                            decisions.append(decision)

                            # Mark file operations as HIL-approved if user approved
                            if decision.get("type") == "approve":
                                tool_name = action_request.get("name")
                                if tool_name in {"write_file", "edit_file"}:
                                    file_op_tracker.mark_hitl_approved(
                                        tool_name, action_request.get("args", {})
                                    )

                        if any(decision.get("type") == "reject" for decision in decisions):
                            any_rejected = True

                        hitl_response[interrupt_id] = {"decisions": decisions}

                suppress_resumed_output = any_rejected

            if interrupt_occurred and hitl_response:
                if suppress_resumed_output:
                    if spinner_active:
                        status.stop()
                        spinner_active = False

                    if ui_callback:
                        ui_callback(
                            Text.from_markup("[yellow]Command rejected.[/yellow]", style="bold")
                        )
                    if ui_callback:
                        ui_callback(Text("Tell the agent what you'd like to do differently."))
                    if ui_callback:
                        ui_callback(Text("\n"))
                    return

                # Resume the agent with the human decision
                stream_input = Command(resume=hitl_response)
                # Continue the while loop to restream
            else:
                # No interrupt, break out of while loop
                break

    except asyncio.CancelledError:
        # Event loop cancelled the task (e.g. Ctrl+C during streaming) - clean up and return
        if spinner_active:
            status.stop()
        if ui_callback:
            ui_callback(Text.from_markup("\n[yellow]Interrupted by user[/yellow]"))
        if ui_callback:
            ui_callback(Text("Updating agent state...", style="dim"))

        try:
            await agent.aupdate_state(
                config=config,
                values={
                    "messages": [
                        HumanMessage(content="[The previous request was cancelled by the system]")
                    ]
                },
            )
            if ui_callback:
                ui_callback(Text("Ready for next command.\n", style="dim"))
        except Exception as e:
            if ui_callback:
                ui_callback(
                    Text.from_markup(f"[red]Warning: Failed to update agent state: {e}[/red]\n")
                )

        return

    except KeyboardInterrupt:
        # User pressed Ctrl+C - clean up and exit gracefully
        if spinner_active:
            status.stop()
        if ui_callback:
            ui_callback(Text.from_markup("\n[yellow]Interrupted by user[/yellow]"))
        if ui_callback:
            ui_callback(Text("Updating agent state...", style="dim"))

        # Inform the agent synchronously (in async context)
        try:
            await agent.aupdate_state(
                config=config,
                values={
                    "messages": [
                        HumanMessage(content="[User interrupted the previous request with Ctrl+C]")
                    ]
                },
            )
            if ui_callback:
                ui_callback(Text("Ready for next command.\n", style="dim"))
        except Exception as e:
            if ui_callback:
                ui_callback(
                    Text.from_markup(f"[red]Warning: Failed to update agent state: {e}[/red]\n")
                )

        return

    except Exception as e:
        # Handle API errors (authentication, rate limits, network issues, etc.)
        if spinner_active:
            status.stop()

        error_str = str(e)
        error_type = type(e).__name__

        # Provide user-friendly messages for common errors
        if "401" in error_str or "Unauthorized" in error_str or "AuthenticationError" in error_type:
            if ui_callback:
                ui_callback(Text.from_markup("\n[red]Authentication Error[/red]"))
                ui_callback(Text("Your API key is invalid or expired.", style="dim"))
                ui_callback(Text("Use /models to update your API key.\n", style="dim"))
        elif "429" in error_str or "RateLimitError" in error_type:
            if ui_callback:
                ui_callback(Text.from_markup("\n[red]Rate Limit Error[/red]"))
                ui_callback(
                    Text("Too many requests. Please wait a moment and try again.\n", style="dim")
                )
        elif "timeout" in error_str.lower() or "TimeoutError" in error_type:
            if ui_callback:
                ui_callback(Text.from_markup("\n[red]Timeout Error[/red]"))
                ui_callback(Text("The request timed out. Please try again.\n", style="dim"))
        elif "Connection" in error_str or "NetworkError" in error_type:
            if ui_callback:
                ui_callback(Text.from_markup("\n[red]Connection Error[/red]"))
                ui_callback(
                    Text(
                        "Could not connect to the API. Check your internet connection.\n",
                        style="dim",
                    )
                )
        else:
            # Generic error
            if ui_callback:
                ui_callback(Text.from_markup(f"\n[red]Error: {error_type}[/red]"))
                # Truncate very long error messages
                if len(error_str) > 200:
                    error_str = error_str[:197] + "..."
                ui_callback(Text(error_str, style="dim"))
                ui_callback(Text(""))

        # Update agent state to preserve context after API errors
        # This ensures the agent remembers what was being attempted if the user retries
        try:
            await agent.aupdate_state(
                config=config,
                values={
                    "messages": [
                        HumanMessage(
                            content=f"[The previous request failed with an API error: {error_type}. "
                            f"The user may ask to retry.]"
                        )
                    ]
                },
            )
        except Exception:
            pass  # Best effort - don't fail if state update also fails

        return

    if spinner_active:
        status.stop()

    if has_responded:
        if ui_callback:
            ui_callback(Text("\n"))

    # Auto-reload agent if schema-modifying tools were used successfully
    if services_to_reload:
        try:
            from sdrbot_cli.services import resync_service

            if ui_callback:
                ui_callback(
                    Text(
                        f"  ⟳ Schema modified, resyncing {', '.join(services_to_reload)}...",
                        style=f"dim {COLORS['tool']}",
                    )
                )

            # Resync each affected service
            for service in services_to_reload:
                await resync_service(service, verbose=False)

            # Reload agent with fresh tools
            await session_state.reload_agent()

            if ui_callback:
                ui_callback(
                    Text(
                        "  ✓ Tools refreshed with updated schema",
                        style=f"dim {COLORS['agent']}",
                    )
                )
        except Exception as e:
            if ui_callback:
                ui_callback(
                    Text(
                        f"  ⚠ Auto-reload failed: {e}. Run /sync manually.",
                        style="dim yellow",
                    )
                )
