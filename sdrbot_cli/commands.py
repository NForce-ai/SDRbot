"""Command handlers for slash commands and bash execution."""

import subprocess
from pathlib import Path

import dotenv
from langgraph.checkpoint.memory import InMemorySaver

from .config import COLORS, DEEP_AGENTS_ASCII, SessionState, console, settings
from .services import SYNCABLE_SERVICES, resync_service
from .setup_wizard import run_setup_wizard
from .ui import TokenTracker, show_interactive_help


async def handle_command(
    command: str, session_state: SessionState, token_tracker: TokenTracker
) -> str | bool:
    """
    Handle slash commands.
    Returns:
    - 'exit': to exit the CLI
    - True: if command handled
    - False: if not handled (pass to agent)
    """
    cmd_parts = command.strip().lstrip("/").split()
    cmd = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []

    if cmd in ["quit", "exit", "q"]:
        return "exit"

    if cmd == "sync":
        if args:
            # Sync specific service
            service_name = args[0]
            if service_name not in SYNCABLE_SERVICES:
                console.print(f"[red]Service '{service_name}' does not support syncing.[/red]")
                console.print(f"[dim]Syncable services: {', '.join(SYNCABLE_SERVICES)}[/dim]")
                return True
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
        return True

    if cmd == "clear":
        # Reset agent conversation state
        if session_state.agent:
            session_state.agent.checkpointer = InMemorySaver()

        # Reset token tracking to baseline
        token_tracker.reset()

        # Clear screen and show fresh UI
        console.clear()
        console.print(DEEP_AGENTS_ASCII, style=f"bold {COLORS['primary']}")
        console.print()
        console.print(
            "... Fresh start! Screen cleared and conversation reset.", style=COLORS["agent"]
        )
        console.print()
        return True

    if cmd == "help":
        show_interactive_help()
        return True

    if cmd == "tokens":
        token_tracker.display_session()
        return True

    if cmd == "setup":
        await run_setup_wizard(force=True, allow_exit=False)
        # Reload env and settings immediately
        dotenv.load_dotenv(Path.cwd() / ".env", override=True)
        settings.reload()
        # Reload agent to pick up any new services
        session_state.reload_agent()
        return True

    console.print()
    console.print(f"[yellow]Unknown command: /{cmd}[/yellow]")
    console.print("[dim]Type /help for available commands.[/dim]")
    console.print()
    return True


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
