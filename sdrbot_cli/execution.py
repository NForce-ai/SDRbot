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

from sdrbot_cli.config import COLORS, settings
from sdrbot_cli.file_ops import FileOpTracker
from sdrbot_cli.image_utils import ImageData, create_multimodal_content
from sdrbot_cli.input import parse_file_mentions
from sdrbot_cli.ui import (
    TokenTracker,
    format_tool_display,
    format_tool_message_content,
    render_file_operation,
)

# Token tracking for context compression
_current_tokens: int = 0


def set_current_tokens(tokens: int) -> None:
    """Set the current token count (called after each API response)."""
    global _current_tokens
    _current_tokens = tokens


def get_current_tokens() -> int:
    """Get the current token count."""
    return _current_tokens


def reset_current_tokens() -> None:
    """Reset the token count (called on compression or /clear)."""
    global _current_tokens
    _current_tokens = 0


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
        if ui_callback:
            ui_callback(
                Text.from_markup(
                    "  [blue]⚡ Auto-approve enabled for future actions.[/blue]", style="dim"
                )
            )
            ui_callback(Text("\n"))
        return {"type": "auto_approve_all"}
    else:  # reject
        if ui_callback:
            ui_callback(Text.from_markup("  [red]❌ Tool action rejected.[/red]", style="dim"))
            ui_callback(Text("\n"))
        return RejectDecision(type="reject", message="User rejected the command")


def _get_summarization_threshold(model) -> int | None:
    """Get the summarization threshold in tokens."""
    # Get model max tokens
    max_tokens = None
    if model and hasattr(model, "profile") and isinstance(model.profile, dict):
        max_tokens = model.profile.get("max_input_tokens")

    threshold_setting = settings.summarization_threshold

    if threshold_setting is None:
        if max_tokens:
            return int(max_tokens * 0.85)
        return 170_000  # Fallback

    try:
        value = float(threshold_setting)
        if 0 < value <= 1:
            # Fraction
            if max_tokens:
                return int(max_tokens * value)
            return int(170_000 * value / 0.85)
        elif value > 1:
            # Absolute
            return int(value)
    except ValueError:
        pass

    # Default
    if max_tokens:
        return int(max_tokens * 0.85)
    return 170_000


async def _maybe_summarize_and_reset(
    agent,
    session_state,
    config: dict,
    ui_callback: Callable | None,
    token_tracker: TokenTracker | None,
    token_callback: Callable | None,
) -> str | None:
    """Check if summarization is needed and reset checkpointer with summary.

    Returns the summary string to prepend to user input, or None if no compression needed.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    # Use token_tracker's value (what UI displays) for consistent threshold check
    current_tokens = token_tracker.current_context if token_tracker else get_current_tokens()
    threshold = _get_summarization_threshold(session_state.model)

    if threshold is None or current_tokens < threshold:
        return None

    # Get current messages from agent state
    try:
        state = await agent.aget_state(config)
        messages = state.values.get("messages", [])
    except Exception:
        return None

    if len(messages) <= 6:
        return None

    # Generate summary from all messages (we'll start fresh)
    # Format messages for summary
    formatted = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = " ".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in content
            )
        if content:
            formatted.append(f"{role}: {content[:500]}...")

    if not formatted:
        return None

    messages_text = "\n\n".join(formatted[-50:])

    summary_prompt = """Summarize the following conversation history, preserving:
1. Key decisions and outcomes
2. Important context and facts discovered
3. Current state of any ongoing tasks
4. Any errors or issues encountered

Be concise but comprehensive. This summary will replace the conversation history.

Conversation to summarize:
{messages}"""

    if ui_callback:
        ui_callback(Text("Compressing context...", style="dim italic"))

    try:
        # Generate summary using the model without streaming callbacks
        model = session_state.model
        if model:
            model_no_stream = model.with_config(callbacks=[])
            response = await model_no_stream.ainvoke(
                [HumanMessage(content=summary_prompt.format(messages=messages_text))]
            )
            summary = (
                response.content if isinstance(response.content, str) else str(response.content)
            )
        else:
            summary = "Previous conversation context (summarization unavailable)"
    except Exception as e:
        summary = f"Previous conversation (summary error: {e})"

    # Create new checkpointer and replace the old one - this clears all messages
    new_checkpointer = InMemorySaver()
    agent.checkpointer = new_checkpointer
    session_state.checkpointer = new_checkpointer

    # Reset token tracking
    reset_current_tokens()
    if token_tracker:
        token_tracker.reset()
        if token_callback:
            token_callback(token_tracker.current_context)

    if ui_callback:
        ui_callback(Text("Context compressed. Continuing with summary.", style="dim italic"))
        ui_callback(Text(""))

    return summary


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

    # Check if context compression is needed before processing
    summary = await _maybe_summarize_and_reset(
        agent, session_state, config, ui_callback, token_tracker, token_callback
    )

    # If we compressed, prepend summary context to user's input
    if summary:
        final_input = f"[Context from previous conversation]\n{summary}\n\n---\n\nUser's current request: {final_input}"

    has_responded = False
    captured_input_tokens = 0
    captured_output_tokens = 0
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
                # Extract just the text content from markup like "[bold cyan]Executing..."
                # Strip the markup tags for cleaner display
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
                            captured_input_tokens = max(captured_input_tokens, input_toks)
                            captured_output_tokens = max(captured_output_tokens, output_toks)
                            # Update current tokens for summarization middleware
                            set_current_tokens(captured_input_tokens)

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

                            # Restart spinner with context about which tool is executing
                            status.update(f"[bold {COLORS['thinking']}]Executing {display_str}...")
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
                                if ui_callback:
                                    ui_callback(Text("\n"))
                                if ui_callback:
                                    ui_callback(
                                        Text.from_markup(
                                            "[bold blue]✓ Auto-approve mode enabled[/bold blue]"
                                        )
                                    )
                                if ui_callback:
                                    ui_callback(
                                        Text.from_markup(
                                            "[dim]All future tool actions will be automatically approved.[/dim]"
                                        )
                                    )
                                if ui_callback:
                                    ui_callback(Text("\n"))

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

        return

    if spinner_active:
        status.stop()

    if has_responded:
        if ui_callback:
            ui_callback(Text("\n"))
        # Track token usage
        if token_tracker and (captured_input_tokens or captured_output_tokens):
            token_tracker.add(captured_input_tokens, captured_output_tokens)
            if token_callback:
                token_callback(token_tracker.current_context)
