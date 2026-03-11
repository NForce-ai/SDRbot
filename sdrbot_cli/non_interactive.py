"""Non-interactive (headless) execution mode for SDRbot.

Runs a single prompt to completion without the TUI, collecting output
to stdout.  Useful for cron jobs, CI/CD pipelines, and scripted workflows.

Usage examples::

    sdrbot -n -p "Enrich all leads added today"
    echo "Run data quality check" | sdrbot -n
    sdrbot -n -p "List top 10 deals" --output-format json
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from rich.console import Console

from sdrbot_cli.config import (
    SessionState,
    create_model,
    is_command_allowed,
)


async def run_non_interactive(
    prompt: str,
    *,
    assistant_id: str = "agent",
    output_format: str = "text",
    max_turns: int = 50,
    auto_approve: bool = False,
) -> dict[str, Any]:
    """Execute *prompt* without a TUI and return structured output.

    Parameters
    ----------
    prompt:
        The user instruction to execute.
    assistant_id:
        Agent identity (matches ``--agent`` CLI flag).
    output_format:
        ``"text"`` (default) or ``"json"``.
    max_turns:
        Safety limit on agent turns to prevent runaway loops.
    auto_approve:
        If ``True``, approve **all** HITL prompts automatically.
        If ``False``, only allow-listed shell commands are auto-approved;
        anything else causes the run to abort with an error.

    Returns
    -------
    dict with keys:
        ``output`` (str) — collected agent text output
        ``status`` (str) — ``"success"`` or ``"error"``
        ``error``  (str | None) — error message if status is ``"error"``
        ``turns``  (int) — number of agent turns consumed
    """
    from sdrbot_cli.agent import create_agent_with_config

    console = Console(stderr=True, highlight=False)

    # Build model
    try:
        model = create_model()
    except SystemExit:
        return {
            "output": "",
            "status": "error",
            "error": "No API key configured.",
            "turns": 0,
        }

    # Create agent
    session_state = SessionState(assistant_id=assistant_id, auto_approve=auto_approve)
    agent, backend, tool_count, skill_count, checkpointer, baseline_tokens = (
        create_agent_with_config(
            model=model,
            assistant_id=assistant_id,
            tools=[],
            session_state=session_state,
        )
    )

    thread_id = str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 1000,
    }

    # Collect output
    output_parts: list[str] = []
    turns = 0
    status = "success"
    error_msg: str | None = None

    try:
        input_msg = {"messages": [{"role": "user", "content": prompt}]}

        for turn in range(max_turns):
            turns = turn + 1
            result = await asyncio.to_thread(lambda: agent.invoke(input_msg, config))

            # Extract text from the last AI message
            messages = result.get("messages", [])
            for msg in reversed(messages):
                content = getattr(msg, "content", "")
                if content and getattr(msg, "type", "") == "ai":
                    if isinstance(content, list):
                        text_parts = [
                            c.get("text", "") if isinstance(c, dict) else str(c) for c in content
                        ]
                        output_parts.append("".join(text_parts))
                    else:
                        output_parts.append(str(content))
                    break

            # Check for pending interrupts (HITL)
            state = agent.get_state(config)
            if not state.next:
                # Agent completed normally
                break

            # There are pending interrupts — handle them
            if auto_approve:
                # Approve everything
                agent.invoke(None, config)
                continue

            # Check if pending tools are allow-listed
            # If not, abort
            pending_tasks = state.tasks or []
            all_allowed = True
            for task in pending_tasks:
                interrupts = getattr(task, "interrupts", [])
                for interrupt in interrupts:
                    action_requests = getattr(interrupt, "value", {})
                    if isinstance(action_requests, dict):
                        action_requests = action_requests.get("action_requests", [])
                    if isinstance(action_requests, list):
                        for ar in action_requests:
                            tool_name = ar.get("name", "") if isinstance(ar, dict) else ""
                            cmd = ""
                            if isinstance(ar, dict):
                                cmd = (ar.get("args") or {}).get("command", "")
                            if tool_name in ("shell", "execute") and is_command_allowed(cmd):
                                continue
                            all_allowed = False
                            break

            if not all_allowed:
                status = "error"
                error_msg = (
                    "Agent requested a tool that requires approval but "
                    "non-interactive mode cannot prompt. Use --auto-approve "
                    "to approve all actions."
                )
                break

            # All pending are allowed — approve and continue
            agent.invoke(None, config)

        else:
            status = "error"
            error_msg = f"Reached maximum turns ({max_turns})."

    except Exception as exc:
        status = "error"
        error_msg = str(exc)

    result_dict: dict[str, Any] = {
        "output": "\n".join(output_parts),
        "status": status,
        "error": error_msg,
        "turns": turns,
    }

    # Emit output
    if output_format == "json":
        print(json.dumps(result_dict, indent=2))
    else:
        if output_parts:
            print("\n".join(output_parts))
        if error_msg:
            console.print(f"[red]Error:[/red] {error_msg}", style="bold")

    return result_dict
