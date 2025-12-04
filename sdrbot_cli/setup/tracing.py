"""Tracing services setup for the setup wizard."""

import os

from sdrbot_cli.config import COLORS, console
from sdrbot_cli.services import disable_service, enable_service
from sdrbot_cli.services.registry import load_config

from .env import get_or_prompt, reload_env_and_settings, save_env_vars
from .menu import CancelledError, show_menu

# Tracing services
TRACING_SERVICES = [
    ("langsmith", "LangSmith"),
    ("langfuse", "Langfuse"),
    ("opik", "Opik"),
]


def get_tracing_service_status(service_name: str) -> tuple[bool, bool]:
    """
    Check tracing service status.

    Returns:
        (is_configured, is_enabled)
    """
    configured = False
    if service_name == "langsmith":
        configured = bool(os.getenv("LANGSMITH_API_KEY"))
    elif service_name == "langfuse":
        configured = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
    elif service_name == "opik":
        configured = bool(os.getenv("OPIK_API_KEY"))

    # Check enabled state from registry
    try:
        config = load_config()
        enabled = config.is_enabled(service_name)
    except Exception:
        enabled = False

    return configured, enabled


def get_tracing_status() -> str:
    """Get overall status string for tracing."""
    config = load_config()
    enabled_count = 0

    for service_code, _ in TRACING_SERVICES:
        if config.is_enabled(service_code):
            enabled_count += 1

    if enabled_count > 0:
        return f"[green]✓ {enabled_count} enabled[/green]"
    return "[dim]• None configured[/dim]"


async def setup_tracing() -> str | None:
    """
    Run the Tracing setup wizard.

    Returns:
        "back" to return to main menu, None if exited
    """
    try:
        return await _setup_tracing_impl()
    except CancelledError:
        console.print(f"\n[{COLORS['dim']}]Configuration cancelled.[/{COLORS['dim']}]")
        return "back"


async def _setup_tracing_impl() -> str | None:
    """Implementation of tracing setup."""
    while True:
        menu_items = []

        for service_code, service_label in TRACING_SERVICES:
            configured, enabled = get_tracing_service_status(service_code)

            if configured:
                if enabled:
                    status = "[green]✓ Enabled[/green]"
                else:
                    status = "[yellow]• Disabled[/yellow]"
            else:
                status = "[dim]• Not Configured[/dim]"

            menu_items.append((service_code, service_label, status))

        menu_items.append(("---", "──────────────", ""))
        menu_items.append(("back", "← Back", ""))

        selected = await show_menu(menu_items, title="Tracing")

        if selected == "back" or selected is None:
            return "back"

        # Configure selected service
        await _configure_tracing_service(selected)


async def _configure_tracing_service(service_name: str) -> None:
    """Configure a specific tracing service."""
    configured, enabled = get_tracing_service_status(service_name)

    if not configured:
        # Not configured -> configure directly
        await _setup_tracing_service(service_name, force=True)
    else:
        # Configured -> offer toggle and reconfigure
        action_items = []
        if enabled:
            action_items.append(("disable", "Disable Service", ""))
        else:
            action_items.append(("enable", "Enable Service", ""))
        action_items.append(("reconfigure", "Reconfigure Credentials", ""))
        action_items.append(("back", "Back", ""))

        action = await show_menu(action_items, title=f"Manage {service_name.capitalize()}")

        if action == "reconfigure":
            await _setup_tracing_service(service_name, force=True)
        elif action == "enable":
            enable_service(service_name, verbose=True)
        elif action == "disable":
            disable_service(service_name, verbose=True)


async def _setup_tracing_service(service_name: str, force: bool = False) -> bool:
    """Setup a specific tracing service."""
    env_vars = {}

    if service_name == "langsmith":
        console.print(f"[{COLORS['primary']}]--- LangSmith Configuration ---[/{COLORS['primary']}]")
        api_key = await get_or_prompt(
            "LANGSMITH_API_KEY", "LangSmith API Key", is_secret=True, required=True, force=force
        )
        if api_key:
            env_vars["LANGSMITH_API_KEY"] = api_key

    elif service_name == "langfuse":
        console.print(f"[{COLORS['primary']}]--- Langfuse Configuration ---[/{COLORS['primary']}]")
        public_key = await get_or_prompt(
            "LANGFUSE_PUBLIC_KEY", "Langfuse Public Key", required=True, force=force
        )
        secret_key = await get_or_prompt(
            "LANGFUSE_SECRET_KEY", "Langfuse Secret Key", is_secret=True, required=True, force=force
        )
        host = await get_or_prompt(
            "LANGFUSE_HOST",
            "Langfuse Host (optional, for self-hosted)",
            required=False,
            force=force,
        )
        if public_key:
            env_vars["LANGFUSE_PUBLIC_KEY"] = public_key
        if secret_key:
            env_vars["LANGFUSE_SECRET_KEY"] = secret_key
        if host:
            env_vars["LANGFUSE_HOST"] = host

    elif service_name == "opik":
        console.print(f"[{COLORS['primary']}]--- Opik Configuration ---[/{COLORS['primary']}]")
        api_key = await get_or_prompt(
            "OPIK_API_KEY", "Opik API Key", is_secret=True, required=True, force=force
        )
        if api_key:
            env_vars["OPIK_API_KEY"] = api_key

    else:
        console.print(f"[red]Unknown tracing service: {service_name}[/red]")
        return False

    if env_vars:
        save_env_vars(env_vars)
        reload_env_and_settings()
        enable_service(service_name, verbose=True)
        return True

    return False
