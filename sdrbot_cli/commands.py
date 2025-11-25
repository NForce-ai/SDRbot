"""Command handlers for slash commands and bash execution."""

import subprocess
import dotenv
from pathlib import Path
from rich.table import Table

from langgraph.checkpoint.memory import InMemorySaver

from .config import COLORS, DEEP_AGENTS_ASCII, console, settings
from .ui import TokenTracker, show_interactive_help
from .setup_wizard import run_setup_wizard, setup_service
import sdrbot_cli.auth.salesforce as sf_auth
import sdrbot_cli.auth.hubspot as hs_auth
import sdrbot_cli.auth.attio as attio_auth
import sdrbot_cli.auth.lusha as lusha_auth
import sdrbot_cli.auth.hunter as hunter_auth


def handle_command(command: str, agent, token_tracker: TokenTracker) -> str | bool:
    """
    Handle slash commands. 
    Returns:
    - 'exit': to exit the CLI
    - 'reload': to re-initialize the agent
    - True: if command handled
    - False: if not handled (pass to agent)
    """
    cmd_parts = command.strip().lstrip("/").split()
    cmd = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []

    if cmd in ["quit", "exit", "q"]:
        return "exit"
        
    if cmd == "services":
        if not args:
            # List status
            table = Table(title="Connected Services")
            table.add_column("Service", style="cyan")
            table.add_column("Status", style="green")
            
            services = [
                ("Salesforce", sf_auth.is_configured()),
                ("HubSpot", hs_auth.is_configured()),
                ("Attio", attio_auth.is_configured()),
                ("Lusha", lusha_auth.is_configured()),
                ("Hunter.io", hunter_auth.is_configured()),
                ("Tavily", settings.has_tavily),
            ]
            
            for name, active in services:
                status = "[green]Active[/green]" if active else "[dim]Not Configured[/dim]"
                table.add_row(name, status)
                
            console.print(table)
            console.print("[dim]Use /services enable <name> to configure a service.[/dim]\n")
            return True
            
        action = args[0].lower()
        if action == "enable" and len(args) > 1:
            service_name = args[1].lower()
            if setup_service(service_name, force=True):
                # Reload env and settings immediately
                dotenv.load_dotenv(Path.cwd() / ".env", override=True)
                settings.reload()
                console.print(f"[green]Enabled {service_name}! Reloading agent...[/green]\n")
                return "reload"
            return True
            
        console.print("[red]Usage: /services [enable <name>][/red]")
        return True

    if cmd == "clear":
        # Reset agent conversation state
        agent.checkpointer = InMemorySaver()

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

    if cmd == "reconfigure":
        run_setup_wizard(force=True)
        # Reload env and settings immediately
        dotenv.load_dotenv(Path.cwd() / ".env", override=True)
        settings.reload()
        console.print("[green]Configuration reloaded successfully![/green]\n")
        return True

    console.print()
    console.print(f"[yellow]Unknown command: /{cmd}[/yellow]")
    console.print("[dim]Type /help for available commands.[/dim]")
    console.print()
    return True

    return False


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
