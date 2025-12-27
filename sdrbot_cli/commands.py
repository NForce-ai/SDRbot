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
