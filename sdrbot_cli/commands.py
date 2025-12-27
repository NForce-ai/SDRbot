"""Command handlers for slash commands and bash execution."""

import subprocess
from pathlib import Path

import dotenv
from langgraph.checkpoint.memory import InMemorySaver
from rich.console import RenderableType
from rich.text import Text

from .config import COLORS, SessionState, console, settings
from .services import SYNCABLE_SERVICES, resync_service
from .setup import run_setup_wizard
from .setup.mcp import run_mcp_wizard
from .setup.models import setup_models
from .setup.services import setup_services
from .ui import TokenTracker, show_interactive_help

# Default summarization settings
DEFAULT_TRIGGER_FRACTION = 0.85
DEFAULT_KEEP_FRACTION = 0.10
FALLBACK_TRIGGER_TOKENS = 170_000
FALLBACK_KEEP_MESSAGES = 6


def _get_model_max_tokens(session_state: SessionState) -> int | None:
    """Try to get max input tokens from the model's profile."""
    try:
        model = session_state.model
        if model is None:
            return None
        if hasattr(model, "profile") and isinstance(model.profile, dict):
            return model.profile.get("max_input_tokens")
    except Exception:
        pass
    return None


def _parse_threshold(value: str | None, max_tokens: int | None) -> tuple[int, str]:
    """Parse threshold value and return (threshold_at, display_string).

    Args:
        value: SUMMARIZATION_THRESHOLD env var value
        max_tokens: Model's max input tokens (if available)

    Returns:
        Tuple of (threshold_at_tokens, display_label)
    """
    if value is None:
        if max_tokens:
            trigger_at = int(max_tokens * DEFAULT_TRIGGER_FRACTION)
            return trigger_at, f"{trigger_at:,} tokens (85%)"
        return FALLBACK_TRIGGER_TOKENS, f"{FALLBACK_TRIGGER_TOKENS:,} tokens (fallback)"

    try:
        num = float(value)
        if 0 < num <= 1:
            # Fraction-based
            if max_tokens:
                trigger_at = int(max_tokens * num)
                pct = int(num * 100)
                return trigger_at, f"{trigger_at:,} tokens ({pct}%)"
            # No max_tokens but fraction specified - use fallback scaled
            trigger_at = int(FALLBACK_TRIGGER_TOKENS * num / DEFAULT_TRIGGER_FRACTION)
            return trigger_at, f"{trigger_at:,} tokens (fallback)"
        elif num > 1:
            # Absolute token count
            trigger_at = int(num)
            if max_tokens:
                pct = int((trigger_at / max_tokens) * 100)
                return trigger_at, f"{trigger_at:,} tokens ({pct}%)"
            return trigger_at, f"{trigger_at:,} tokens"
    except ValueError:
        pass

    # Invalid value, use defaults
    if max_tokens:
        trigger_at = int(max_tokens * DEFAULT_TRIGGER_FRACTION)
        return trigger_at, f"{trigger_at:,} tokens (85%)"
    return FALLBACK_TRIGGER_TOKENS, f"{FALLBACK_TRIGGER_TOKENS:,} tokens (fallback)"


def display_context_usage(token_tracker: TokenTracker, session_state: SessionState) -> list[Text]:
    """Display context usage and summarization status."""
    output_lines = []
    output_lines.append(Text("\nContext Usage:", style=f"bold {COLORS['primary']}"))

    current = token_tracker.current_context
    max_tokens = _get_model_max_tokens(session_state)
    trigger_at, trigger_label = _parse_threshold(settings.summarization_threshold, max_tokens)

    output_lines.append(Text(f"  Current: {current:,} tokens", style=COLORS["dim"]))

    if max_tokens:
        keep_tokens = int(max_tokens * DEFAULT_KEEP_FRACTION)
        output_lines.append(Text(f"  Model max: {max_tokens:,} tokens", style=COLORS["dim"]))
        output_lines.append(Text(f"  Summarization at: {trigger_label}", style=COLORS["dim"]))
        keep_info = f"Keeps ~{keep_tokens:,} tokens (10%) after summarization"
    else:
        output_lines.append(Text(f"  Summarization at: {trigger_label}", style=COLORS["dim"]))
        keep_info = f"Keeps last {FALLBACK_KEEP_MESSAGES} messages after summarization"

    remaining = max(0, trigger_at - current)
    usage_pct = (current / trigger_at) * 100 if trigger_at > 0 else 0

    # Progress bar
    bar_width = 30
    filled = min(bar_width, int((current / trigger_at) * bar_width)) if trigger_at > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)

    # Color based on usage
    if current >= trigger_at:
        bar_style = "red"
        status = "Summarization will trigger on next message"
    elif usage_pct >= 90:
        bar_style = "yellow"
        status = f"~{remaining:,} tokens until summarization"
    else:
        bar_style = "green"
        status = f"~{remaining:,} tokens until summarization"

    output_lines.append(Text(f"  [{bar}] {usage_pct:.1f}%", style=bar_style))
    output_lines.append(Text(f"  {status}", style=COLORS["dim"]))
    output_lines.append(Text(f"  {keep_info}", style=COLORS["dim"]))

    output_lines.append(Text(""))
    return output_lines


async def handle_command(
    command: str, session_state: SessionState, token_tracker: TokenTracker
) -> str | list[RenderableType] | None:
    """
    Handle slash commands.
    Returns:
    - 'exit': to exit the CLI
    - list[RenderableType] or str: output to display
    - None: if not handled (pass to agent) - Wait, logic says False if not handled.
      Let's stick to returning None if not handled.
    """
    cmd_parts = command.strip().lstrip("/").split()
    cmd = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []

    if cmd in ["quit", "exit", "q"]:
        return "exit"

    if cmd == "sync":
        # Check TUI mode - sync might print to console, we should capture it or ensure it's TUI safe
        # resync_service uses console.print.
        # For now, let's allow it but warn it might output to stdout (which might break TUI layout or be hidden)
        # Ideally we'd redirect stdout to a string buffer.

        output_lines = []
        output_lines.append(Text("Syncing enabled services...", style=COLORS["primary"]))

        # We can't easily capture console.print from resync_service without refactoring it.
        # For the TUI overhaul, let's just trigger it and hope for the best or disable it.
        # It's better to disable complex console-printing commands in TUI for this iteration.

        if session_state.is_tui:
            return Text(
                "Command '/sync' is not yet fully supported in TUI mode. Please use the terminal.",
                style="yellow",
            )

        if args:
            # Sync specific service
            service_name = args[0]
            if service_name not in SYNCABLE_SERVICES:
                console.print(f"[red]Service '{service_name}' does not support syncing.[/red]")
                console.print(f"[dim]Syncable services: {', '.join(SYNCABLE_SERVICES)}[/dim]")
                return "Sync failed (invalid service)"
            resync_service(service_name, verbose=True)
        else:
            # Sync all enabled syncable services
            from sdrbot_cli.services.registry import load_config

            config = load_config()
            synced_any = False

            console.print(f"[{COLORS['primary']}]Syncing enabled services...[/{COLORS['primary']}]")

            for service in SYNCABLE_SERVICES:
                if config.is_enabled(service):
                    resync_service(service, verbose=True)
                    synced_any = True

            if not synced_any:
                console.print("[dim]No enabled services require syncing.[/dim]")
        # Reload agent to pick up newly generated tools
        await session_state.reload_agent()
        return "Services synced."

    if cmd == "clear":
        # Reset agent conversation state
        new_checkpointer = InMemorySaver()
        if session_state.agent:
            session_state.agent.checkpointer = new_checkpointer
        session_state.checkpointer = new_checkpointer

        # Reset token tracking to baseline
        token_tracker.reset()

        # Return clear message
        return [
            Text("Conversation cleared.", style=COLORS["primary"]),
            Text("... Fresh start! Memory reset.", style=COLORS["agent"]),
        ]

    if cmd == "help":
        return show_interactive_help()

    if cmd == "tokens":
        return token_tracker.display_session()

    if cmd == "context":
        return display_context_usage(token_tracker, session_state)

    # Setup commands - DISABLE IN TUI
    if session_state.is_tui and cmd in ["setup", "mcp", "models", "services"]:
        return Text(
            f"Command '/{cmd}' requires interactive setup. Please run 'sdrbot setup' or 'sdrbot {cmd}' from the terminal.",
            style="yellow",
        )

    if cmd == "setup":
        await run_setup_wizard(force=True, allow_exit=False)
        dotenv.load_dotenv(Path.cwd() / ".env", override=True)
        settings.reload()
        await session_state.reload_agent()
        return "Setup complete."

    if cmd == "mcp":
        await run_mcp_wizard(return_to_setup=False)
        dotenv.load_dotenv(Path.cwd() / ".env", override=True)
        settings.reload()
        await session_state.reload_agent()
        return "MCP configuration complete."

    if cmd == "models":
        await setup_models()
        dotenv.load_dotenv(Path.cwd() / ".env", override=True)
        settings.reload()
        await session_state.reload_agent()
        return "Models configuration complete."

    if cmd == "services":
        await setup_services()
        dotenv.load_dotenv(Path.cwd() / ".env", override=True)
        settings.reload()
        await session_state.reload_agent()
        return "Services configuration complete."

    return [
        Text(f"Unknown command: /{cmd}", style="yellow"),
        Text("Type /help for available commands.", style="dim"),
    ]


def execute_bash_command(command: str) -> bool:
    """Execute a bash command and display output. Returns True if handled."""
    cmd = command.strip().lstrip("!")

    if not cmd:
        return True

    try:
        console.print()
        console.print(f"[dim]$ {cmd}[/dim]")

        # Execute the command
        result = subprocess.run(
            cmd, check=False, shell=True, capture_output=True, text=True, timeout=30, cwd=Path.cwd()
        )

        # Display output
        if result.stdout:
            console.print(result.stdout, style=COLORS["dim"], markup=False)
        if result.stderr:
            console.print(result.stderr, style="red", markup=False)

        # Show return code if non-zero
        if result.returncode != 0:
            console.print(f"[dim]Exit code: {result.returncode}[/dim]")

        console.print()
        return True

    except subprocess.TimeoutExpired:
        console.print("[red]Command timed out after 30 seconds[/red]")
        console.print()
        return True
    except Exception as e:
        console.print(f"[red]Error executing command: {e}[/red]")
        console.print()
        return True
