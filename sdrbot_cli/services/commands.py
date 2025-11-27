"""CLI commands for service management.

This module provides the implementation for service-related commands:
- services list: Show all services and their status
- services enable <name>: Enable a service (auto-sync if syncable)
- services disable <name>: Disable a service
- services sync <name>: Re-sync a service's schema
- services status <name>: Show detailed status for a service
"""

from pathlib import Path

import dotenv
from rich.console import Console
from rich.table import Table

from sdrbot_cli.config import settings
from sdrbot_cli.services import SERVICES, SYNCABLE_SERVICES
from sdrbot_cli.services.registry import (
    load_config,
    save_config,
    clear_config_cache,
)

console = Console(highlight=False)


def handle_services_command(args: list[str]) -> str | bool:
    """Handle /services commands.

    Args:
        args: Command arguments (e.g., ["enable", "hubspot"])

    Returns:
        - "reload": Agent needs to be reloaded
        - True: Command was handled
        - False: Command was not handled
    """
    if not args:
        _list_services()
        return True

    action = args[0].lower()

    if action == "list":
        _list_services()
        return True

    if action == "enable" and len(args) > 1:
        service_name = args[1].lower()
        result = _enable_service(service_name)
        if result == "reload":
            return "reload"
        return True

    if action == "disable" and len(args) > 1:
        service_name = args[1].lower()
        _disable_service(service_name)
        return True

    if action == "sync" and len(args) > 1:
        service_name = args[1].lower()
        _sync_service(service_name)
        return True

    if action == "status" and len(args) > 1:
        service_name = args[1].lower()
        _show_status(service_name)
        return True

    if action == "update" and len(args) > 1:
        service_name = args[1].lower()
        return _update_service(service_name)

    # Show usage
    console.print()
    console.print("[yellow]Usage:[/yellow]")
    console.print("  /services              - List all services")
    console.print("  /services enable <name>  - Enable a service")
    console.print("  /services disable <name> - Disable a service")
    console.print("  /services update <name>  - Reconfigure service credentials")
    console.print("  /services sync <name>    - Re-sync service schema")
    console.print("  /services status <name>  - Show service details")
    console.print()
    console.print(f"[dim]Available services: {', '.join(SERVICES)}[/dim]")
    console.print()
    return True


def _update_service(service_name: str) -> str | bool:
    """Reconfigure a service.

    Args:
        service_name: Name of the service to update.
    """
    if service_name not in SERVICES:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        return True

    # Lazy import to avoid circular dependencies
    from sdrbot_cli.setup_wizard import setup_service
    
    # force=True ensures prompt even if keys exist
    if setup_service(service_name, force=True):
        console.print(f"[green]✓ {service_name} configuration updated[/green]")
        # Reload env vars
        dotenv.load_dotenv(Path.cwd() / ".env", override=True)
        settings.reload()
        return True
    
    return True


def _list_services() -> None:
    """List all services and their status."""
    config = load_config()

    table = Table(title="Services")
    table.add_column("Service", style="cyan")
    table.add_column("Enabled", justify="center")
    table.add_column("Credentials", justify="center")
    table.add_column("Synced", justify="center")
    table.add_column("Objects", style="dim")

    for name in SERVICES:
        state = config.services.get(name)
        has_creds = settings.has_service_credentials(name)
        is_syncable = name in SYNCABLE_SERVICES

        # Enabled status
        if state and state.enabled:
            enabled = "[green]✓[/green]"
        else:
            enabled = "[dim]✗[/dim]"

        # Credentials status
        if has_creds:
            creds = "[green]✓[/green]"
        else:
            creds = "[red]✗[/red]"

        # Sync status (only for syncable services)
        if not is_syncable:
            synced = "[dim]—[/dim]"
        elif state and state.synced_at:
            synced = "[green]✓[/green]"
        else:
            synced = "[yellow]pending[/yellow]"

        # Objects
        if state and state.objects:
            objects = ", ".join(state.objects[:5])
            if len(state.objects) > 5:
                objects += f" (+{len(state.objects) - 5})"
        else:
            objects = "—"

        table.add_row(name, enabled, creds, synced, objects)

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Use /services enable <name> to enable a service.[/dim]")
    console.print("[dim]Use /services status <name> for details.[/dim]")
    console.print()


def _enable_service(service_name: str) -> str | bool:
    """Enable a service, syncing if required.

    Args:
        service_name: Name of the service to enable.

    Returns:
        "reload" if agent needs to be reloaded, True otherwise.
    """
    if service_name not in SERVICES:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        console.print(f"[dim]Available services: {', '.join(SERVICES)}[/dim]")
        return True

    # Check for credentials
    if not settings.has_service_credentials(service_name):
        console.print(f"[red]No credentials found for {service_name}[/red]")
        console.print()
        console.print("Configure credentials using the setup wizard:")
        console.print("  /reconfigure")
        console.print()
        console.print("Or add to your .env file:")
        _show_credential_help(service_name)
        return True

    config = load_config()

    # Check if already enabled
    if config.is_enabled(service_name):
        console.print(f"[yellow]{service_name} is already enabled[/yellow]")

        # Offer to re-sync if syncable
        if service_name in SYNCABLE_SERVICES:
            console.print("[dim]Use /services sync to re-sync the schema.[/dim]")
        return True

    # Enable the service
    config.enable(service_name)

    # Auto-sync if this service requires it
    if service_name in SYNCABLE_SERVICES:
        console.print(f"[cyan]Syncing {service_name} schema...[/cyan]")
        try:
            result = _run_sync(service_name)
            config.mark_synced(service_name, result["schema_hash"], result["objects"])
            console.print(f"[green]✓ Synced {len(result['objects'])} objects: {', '.join(result['objects'])}[/green]")
        except Exception as e:
            console.print(f"[red]Sync failed: {e}[/red]")
            console.print("[yellow]Service enabled but tools may be limited.[/yellow]")

    save_config(config)
    clear_config_cache()

    console.print(f"[green]✓ {service_name} enabled![/green]")
    console.print("[dim]Reloading agent to load new tools...[/dim]")
    console.print()

    return "reload"


def _disable_service(service_name: str) -> None:
    """Disable a service.

    Args:
        service_name: Name of the service to disable.
    """
    if service_name not in SERVICES:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        return

    config = load_config()

    if not config.is_enabled(service_name):
        console.print(f"[yellow]{service_name} is not enabled[/yellow]")
        return

    config.disable(service_name)
    save_config(config)
    clear_config_cache()

    console.print(f"[yellow]✗ {service_name} disabled[/yellow]")
    console.print("[dim]Restart the agent to unload tools.[/dim]")
    console.print()


def _sync_service(service_name: str) -> None:
    """Sync a service's schema and regenerate tools.

    Args:
        service_name: Name of the service to sync.
    """
    if service_name not in SERVICES:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        return

    if service_name not in SYNCABLE_SERVICES:
        console.print(f"[yellow]{service_name} does not require sync[/yellow]")
        console.print("[dim]This service has static tools that don't depend on your schema.[/dim]")
        return

    config = load_config()

    if not config.is_enabled(service_name):
        console.print(f"[red]{service_name} is not enabled[/red]")
        console.print(f"[dim]Use /services enable {service_name} first.[/dim]")
        return

    # Check credentials
    if not settings.has_service_credentials(service_name):
        console.print(f"[red]No credentials found for {service_name}[/red]")
        return

    console.print(f"[cyan]Syncing {service_name} schema...[/cyan]")

    try:
        result = _run_sync(service_name)

        old_hash = config.get_state(service_name).schema_hash
        if old_hash and old_hash == result["schema_hash"]:
            console.print("[yellow]Schema unchanged since last sync[/yellow]")
        else:
            console.print(f"[green]✓ Schema updated[/green]")

        config.mark_synced(service_name, result["schema_hash"], result["objects"])
        save_config(config)
        clear_config_cache()

        console.print(f"[green]✓ Synced {len(result['objects'])} objects: {', '.join(result['objects'])}[/green]")
        console.print("[dim]Restart the agent to load updated tools.[/dim]")
        console.print()

    except Exception as e:
        console.print(f"[red]Sync failed: {e}[/red]")
        console.print()


def _show_status(service_name: str) -> None:
    """Show detailed status for a service.

    Args:
        service_name: Name of the service to show.
    """
    if service_name not in SERVICES:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        return

    config = load_config()
    state = config.get_state(service_name)
    has_creds = settings.has_service_credentials(service_name)
    is_syncable = service_name in SYNCABLE_SERVICES

    console.print()
    console.print(f"[bold cyan]{service_name.upper()}[/bold cyan]")
    console.print()

    # Basic status
    console.print(f"  Enabled:     {'[green]Yes[/green]' if state.enabled else '[dim]No[/dim]'}")
    console.print(f"  Credentials: {'[green]Configured[/green]' if has_creds else '[red]Missing[/red]'}")
    console.print(f"  Syncable:    {'Yes' if is_syncable else 'No (static tools only)'}")

    # Sync status
    if is_syncable:
        if state.synced_at:
            console.print(f"  Last Synced: {state.synced_at[:19].replace('T', ' ')}")
            console.print(f"  Schema Hash: {state.schema_hash}")
        else:
            console.print("  Last Synced: [yellow]Never[/yellow]")

    # Objects
    if state.objects:
        console.print(f"  Objects:     {', '.join(state.objects)}")

    # Settings
    if state.settings:
        console.print("  Settings:")
        for key, value in state.settings.items():
            console.print(f"    {key}: {value}")

    console.print()

    # Show helpful actions
    if not has_creds:
        console.print("[dim]→ Configure credentials with /reconfigure[/dim]")
    elif not state.enabled:
        console.print(f"[dim]→ Enable with /services enable {service_name}[/dim]")
    elif is_syncable and not state.synced_at:
        console.print(f"[dim]→ Sync schema with /services sync {service_name}[/dim]")

    console.print()


def _run_sync(service_name: str) -> dict:
    """Run the sync function for a service.

    Args:
        service_name: Name of the service to sync.

    Returns:
        Dict with "schema_hash" and "objects" keys.

    Raises:
        ImportError: If sync module not found.
        Exception: If sync fails.
    """
    # Import and run the service-specific sync
    sync_module = __import__(
        f"sdrbot_cli.services.{service_name}.sync",
        fromlist=["sync_schema"]
    )
    return sync_module.sync_schema()


def _show_credential_help(service_name: str) -> None:
    """Show credential configuration help for a service.

    Args:
        service_name: Name of the service.
    """
    help_text = {
        "hubspot": """
  HUBSPOT_ACCESS_TOKEN=your_pat_here
  # Or for OAuth:
  # HUBSPOT_CLIENT_ID=...
  # HUBSPOT_CLIENT_SECRET=...""",
        "salesforce": """
  SF_CLIENT_ID=your_client_id
  SF_CLIENT_SECRET=your_client_secret""",
        "attio": """
  ATTIO_API_KEY=your_api_key""",
        "lusha": """
  LUSHA_API_KEY=your_api_key""",
        "hunter": """
  HUNTER_API_KEY=your_api_key""",
    }

    if service_name in help_text:
        console.print(f"[dim]{help_text[service_name]}[/dim]")
