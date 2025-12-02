"""Main setup wizard for SDRbot configuration."""

import sys

from dotenv import load_dotenv

from sdrbot_cli.config import COLORS, console, load_model_config

from .integrations import get_integrations_status
from .mcp import get_mcp_status, run_mcp_wizard
from .menu import CancelledError, show_menu
from .models import get_model_status, setup_models
from .observability import get_observability_status, setup_observability


async def run_setup_wizard(force: bool = False, allow_exit: bool = True) -> None:
    """
    Main setup wizard with navigation tree.

    Guides the user through setting up:
    - Models (LLM providers)
    - Integrations (CRMs, Prospecting, Databases)
    - MCP Servers (external tool servers)
    - Observability (LangSmith, Langfuse, Opik)

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
        f"[{COLORS['dim']}]Configure your LLM provider, integrations, and external tools.[/{COLORS['dim']}]"
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
        integrations_status = get_integrations_status()
        mcp_status = get_mcp_status()
        observability_status = get_observability_status()

        # Build menu items
        menu_items = [
            ("models", "Models", model_status),
            ("integrations", "Integrations", integrations_status),
            ("mcp", "MCP Servers", mcp_status),
            ("observability", "Observability", observability_status),
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

        elif selected == "integrations":
            from .integrations import setup_integrations

            await setup_integrations()

        elif selected == "mcp":
            await run_mcp_wizard(return_to_setup=True)
            # Returns "setup" if user clicked back, we just continue the loop

        elif selected == "observability":
            await setup_observability()

    console.print(f"\n[{COLORS['primary']}][bold]Setup Complete![/bold][/]")
    console.print(f"[{COLORS['dim']}]You can now run SDRbot.[/{COLORS['dim']}]\n")
