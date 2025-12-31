"""Main setup wizard for SDRbot configuration."""

import sys

from dotenv import load_dotenv

from sdrbot_cli.config import COLORS, console, load_model_config
from sdrbot_cli.services.registry import get_tool_scope_setting, set_tool_scope
from sdrbot_cli.tools import SCOPE_EXTENDED, SCOPE_PRIVILEGED, SCOPE_STANDARD

from .mcp import get_mcp_status, run_mcp_wizard
from .menu import CancelledError, show_menu
from .models import get_model_status, setup_models
from .services import get_services_status
from .tracing import get_tracing_status, setup_tracing


def get_tool_scope_status() -> str:
    """Get status string for tool scope."""
    scope = get_tool_scope_setting()
    if scope == SCOPE_PRIVILEGED:
        return "[yellow]! Privileged[/yellow]"
    elif scope == SCOPE_EXTENDED:
        return "[cyan]• Extended[/cyan]"
    return "[dim]• Standard[/dim]"


async def select_tool_scope() -> None:
    """Select tool scope for this session."""
    current = get_tool_scope_setting()

    console.print("\n[bold]Tool Scope[/bold]")
    console.print(f"[{COLORS['dim']}]Controls which tools are available:[/{COLORS['dim']}]")
    console.print(f"[{COLORS['dim']}]  • Standard: Core CRM tools only[/{COLORS['dim']}]")
    console.print(
        f"[{COLORS['dim']}]  • Extended: Standard + custom objects and advanced tools[/{COLORS['dim']}]"
    )
    console.print(
        f"[{COLORS['dim']}]  • Privileged: All tools including admin/schema management[/{COLORS['dim']}]"
    )
    console.print(f"[{COLORS['dim']}]Current: {current.capitalize()}[/{COLORS['dim']}]")
    console.print()

    selected = await show_menu(
        [
            (SCOPE_STANDARD, "Standard", "Core CRM tools"),
            (SCOPE_EXTENDED, "Extended", "Standard + custom objects"),
            (SCOPE_PRIVILEGED, "Privileged", "All tools (admin)"),
            ("cancel", "Cancel", ""),
        ],
        title="Select Scope",
    )

    if selected != "cancel":
        set_tool_scope(selected)
        console.print(f"\n[green]✓ Tool scope set to {selected.capitalize()}[/green]")


async def run_setup_wizard(force: bool = False, allow_exit: bool = True) -> None:
    """
    Main setup wizard with navigation tree.

    Guides the user through setting up:
    - Models (LLM providers)
    - Services (CRMs, Prospecting, Databases)
    - MCP Servers (external tool servers)
    - Tracing (LangSmith, Langfuse, Opik)

    Args:
        force: If True, run the wizard even if credentials already exist.
        allow_exit: If True, include an "Exit" option in the menu.
    """
    # Check if we already have what we need
    model_config = load_model_config()
    has_model_json = model_config and model_config.get("provider")

    # Skip wizard if already configured (unless forced)
    if has_model_json and not force:
        return

    console.print(f"\n[{COLORS['primary']}][bold]SDRbot Setup Wizard[/bold][/{COLORS['primary']}]")
    console.print(
        f"[{COLORS['dim']}]Configure your LLM provider, services, and external tools.[/{COLORS['dim']}]"
    )
    console.print(
        f"[{COLORS['dim']}]Values will be saved to your working folder's .env file.[/{COLORS['dim']}]\n"
    )

    try:
        await _run_wizard_loop(allow_exit)
    except CancelledError:
        if allow_exit:
            console.print(
                f"[{COLORS['dim']}]Setup cancelled. Exiting application.[/{COLORS['dim']}]"
            )
            sys.exit(0)
        else:
            console.print(f"[{COLORS['dim']}]Exiting setup wizard.[/{COLORS['dim']}]")


async def _run_wizard_loop(allow_exit: bool) -> None:
    """Main wizard navigation loop."""
    while True:
        # Refresh env vars in case they changed
        load_dotenv(override=True)

        # Get status for each section
        _, _, model_status = get_model_status()
        services_status = get_services_status()
        mcp_status = get_mcp_status()
        tracing_status = get_tracing_status()
        tool_scope_status = get_tool_scope_status()

        # Build menu items
        menu_items = [
            ("models", "Models", model_status),
            ("services", "Services", services_status),
            ("mcp", "MCP Servers", mcp_status),
            ("tracing", "Tracing", tracing_status),
            ("---", "──────────────", ""),
            ("tool_scope", "Tool Scope", tool_scope_status),
            ("---", "──────────────", ""),
            ("done", "Done / Continue", ""),
        ]

        if allow_exit:
            menu_items.append(("exit", "Exit", ""))

        # Show menu
        selected = await show_menu(menu_items, title="Setup Wizard")

        if selected == "exit":
            console.print(f"[{COLORS['dim']}]Exiting...[/{COLORS['dim']}]")
            sys.exit(0)

        if selected is None:
            # ESC pressed
            if allow_exit:
                console.print(
                    f"[{COLORS['dim']}]Setup cancelled. Exiting application.[/{COLORS['dim']}]"
                )
                sys.exit(0)
            else:
                console.print(f"[{COLORS['dim']}]Exiting setup wizard.[/{COLORS['dim']}]")
                return

        if selected == "done":
            # Validate that an LLM provider is configured
            current_config = load_model_config()
            has_llm = current_config and current_config.get("provider")

            if not has_llm:
                console.print("\n[red][bold]LLM Provider Required[/bold][/red]")
                console.print(
                    "[red]You must configure at least one LLM provider before continuing.[/red]"
                )
                console.print(
                    f"[{COLORS['dim']}]Select 'Models' from the menu to configure one.[/{COLORS['dim']}]\n"
                )
                continue

            break

        # Navigate to subsection
        if selected == "models":
            await setup_models()

        elif selected == "services":
            from .services import setup_services

            await setup_services()

        elif selected == "mcp":
            await run_mcp_wizard(return_to_setup=True)
            # Returns "setup" if user clicked back, we just continue the loop

        elif selected == "tracing":
            await setup_tracing()

        elif selected == "tool_scope":
            await select_tool_scope()

    console.print(f"\n[{COLORS['primary']}][bold]Setup Complete![/bold][/]")
    console.print(f"[{COLORS['dim']}]You can now run SDRbot.[/{COLORS['dim']}]\n")
