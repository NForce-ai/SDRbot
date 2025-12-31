"""
Service Registry and Management.
"""

from datetime import UTC, datetime, timedelta

from langchain_core.tools import BaseTool

from sdrbot_cli.config import console

# All available services
SERVICES = [
    "salesforce",
    "hubspot",
    "pipedrive",
    "zohocrm",
    "attio",
    "twenty",
    "apollo",
    "hunter",
    "lusha",
    "tavily",
    "postgres",
    "mysql",
    "mongodb",
    "langsmith",
    "langfuse",
    "opik",
]

# Tracing services (provide callbacks, not tools)
TRACING_SERVICES = ["langsmith", "langfuse", "opik"]

# Services that require schema sync (have user-specific schemas)
SYNCABLE_SERVICES = ["hubspot", "salesforce", "attio", "twenty", "zohocrm", "pipedrive"]


def sync_service(service_name: str) -> dict:
    """Sync a service's schema and regenerate tools.

    Args:
        service_name: Name of the service to sync.

    Returns:
        Dict with "schema_hash" and "objects" keys.

    Raises:
        ValueError: If service is not syncable.
        ImportError: If sync module not found.
        Exception: If sync fails.
    """
    if service_name not in SYNCABLE_SERVICES:
        raise ValueError(f"{service_name} does not require sync")

    sync_module = __import__(f"sdrbot_cli.services.{service_name}.sync", fromlist=["sync_schema"])
    return sync_module.sync_schema()


def enable_service(service_name: str, sync: bool = True, verbose: bool = True) -> bool:
    """Enable a service and optionally sync its schema.

    This is the central function for enabling services. Called by:
    - Setup wizard after configuring credentials
    - /services enable command
    - Any other code that needs to enable a service

    Args:
        service_name: Name of the service to enable.
        sync: If True, sync schema for syncable services (default True).
        verbose: If True, print status messages (default True).

    Returns:
        True if service was enabled/synced successfully, False otherwise.
    """
    from sdrbot_cli.config import settings
    from sdrbot_cli.services.registry import clear_config_cache, load_config, save_config

    if service_name not in SERVICES:
        if verbose:
            console.print(f"[red]Unknown service: {service_name}[/red]")
        return False

    # Check for credentials
    if not settings.has_service_credentials(service_name):
        if verbose:
            console.print(f"[red]No credentials found for {service_name}[/red]")
        return False

    config = load_config()

    # Enable the service if not already enabled
    was_enabled = config.is_enabled(service_name)
    if not was_enabled:
        config.enable(service_name)
        if verbose:
            console.print(f"[green]✓ {service_name} enabled[/green]")

    # Sync if requested and this is a syncable service
    if sync and service_name in SYNCABLE_SERVICES:
        if verbose:
            console.print(f"[cyan]Syncing {service_name} schema...[/cyan]")
        try:
            result = sync_service(service_name)
            config.mark_synced(service_name, result["schema_hash"], result["objects"])
            if verbose:
                console.print(
                    f"[green]✓ Synced {len(result['objects'])} objects: {', '.join(result['objects'])}[/green]"
                )
        except Exception as e:
            if verbose:
                console.print(f"[red]Sync failed: {e}[/red]")
                console.print(f"[dim]You can sync later with /services sync {service_name}[/dim]")
            # Still save the enabled state even if sync failed
            save_config(config)
            clear_config_cache()
            return False
    elif verbose and not was_enabled and service_name not in SYNCABLE_SERVICES:
        console.print(f"[green]✓ {service_name} ready[/green]")

    save_config(config)
    clear_config_cache()
    return True


def disable_service(service_name: str, verbose: bool = True) -> bool:
    """Disable a service.

    Args:
        service_name: Name of the service to disable.
        verbose: If True, print status messages (default True).

    Returns:
        True if service was disabled, False if it wasn't enabled or doesn't exist.
    """
    from sdrbot_cli.services.registry import clear_config_cache, load_config, save_config

    if service_name not in SERVICES:
        if verbose:
            console.print(f"[red]Unknown service: {service_name}[/red]")
        return False

    config = load_config()

    if not config.is_enabled(service_name):
        if verbose:
            console.print(f"[yellow]{service_name} is not enabled[/yellow]")
        return False

    config.disable(service_name)
    save_config(config)
    clear_config_cache()

    if verbose:
        console.print(f"[yellow]✗ {service_name} disabled[/yellow]")

    return True


def resync_service(service_name: str, verbose: bool = True) -> bool:
    """Re-sync an already enabled service's schema.

    Args:
        service_name: Name of the service to sync.
        verbose: If True, print status messages (default True).

    Returns:
        True if sync succeeded, False otherwise.
    """
    from sdrbot_cli.config import settings
    from sdrbot_cli.services.registry import clear_config_cache, load_config, save_config

    if service_name not in SERVICES:
        if verbose:
            console.print(f"[red]Unknown service: {service_name}[/red]")
        return False

    if service_name not in SYNCABLE_SERVICES:
        if verbose:
            console.print(f"[yellow]{service_name} does not require sync[/yellow]")
            console.print(
                "[dim]This service has static tools that don't depend on your schema.[/dim]"
            )
        return False

    config = load_config()

    if not config.is_enabled(service_name):
        if verbose:
            console.print(f"[red]{service_name} is not enabled[/red]")
            console.print(f"[dim]Use /services enable {service_name} first.[/dim]")
        return False

    if not settings.has_service_credentials(service_name):
        if verbose:
            console.print(f"[red]No credentials found for {service_name}[/red]")
        return False

    if verbose:
        console.print(f"[cyan]Syncing {service_name} schema...[/cyan]")

    try:
        result = sync_service(service_name)

        old_hash = config.get_state(service_name).schema_hash
        if old_hash and old_hash == result["schema_hash"]:
            if verbose:
                console.print("[yellow]Schema unchanged since last sync[/yellow]")
        else:
            if verbose:
                console.print("[green]✓ Schema updated[/green]")

        config.mark_synced(service_name, result["schema_hash"], result["objects"])
        save_config(config)
        clear_config_cache()

        if verbose:
            console.print(
                f"[green]✓ Synced {len(result['objects'])} objects: {', '.join(result['objects'])}[/green]"
            )

        return True

    except Exception as e:
        if verbose:
            console.print(f"[red]Sync failed: {e}[/red]")
        return False


def sync_enabled_services_if_needed(verbose: bool = True) -> None:
    """Sync any enabled services that haven't been synced yet.

    Called at startup to ensure tools are generated for enabled services.

    Args:
        verbose: If True, print status messages (default True).
    """
    from sdrbot_cli.config import settings
    from sdrbot_cli.services.registry import clear_config_cache, load_config, save_config

    config = load_config()
    synced_any = False

    for service_name in SYNCABLE_SERVICES:
        state = config.get_state(service_name)

        # Skip if not enabled
        if not state.enabled:
            continue

        should_sync = False
        reason = None

        # Check if never synced
        if not state.synced_at:
            should_sync = True
            reason = "initial sync"
        else:
            # Check if generated file exists
            generated_file = settings.ensure_generated_dir() / f"{service_name}_tools.py"
            if not generated_file.exists():
                should_sync = True
                reason = "tools file missing"

            # Check if expired (24h)
            try:
                last_sync = datetime.fromisoformat(state.synced_at)
                if datetime.now(UTC) - last_sync > timedelta(hours=24):
                    should_sync = True
                    reason = "schema cache expired (>24h)"
            except ValueError:
                should_sync = True  # Invalid format, re-sync
                reason = "invalid timestamp"

        if not should_sync:
            continue

        if verbose and state.synced_at:
            console.print(f"[yellow]⚠ {service_name}: {reason} - re-syncing...[/yellow]")

        # Skip if no credentials
        if not settings.has_service_credentials(service_name):
            if verbose:
                console.print(
                    f"[yellow]⚠ {service_name} enabled but missing credentials - skipping sync[/yellow]"
                )
            continue

        # Need to sync
        if verbose:
            console.print(f"[cyan]Syncing {service_name} schema...[/cyan]")
        try:
            result = sync_service(service_name)
            config.mark_synced(service_name, result["schema_hash"], result["objects"])
            if verbose:
                console.print(
                    f"[green]✓ Synced {len(result['objects'])} objects: {', '.join(result['objects'])}[/green]"
                )
            synced_any = True
        except Exception as e:
            if verbose:
                console.print(f"[red]Failed to sync {service_name}: {e}[/red]")

    if synced_any:
        save_config(config)
        clear_config_cache()
        if verbose:
            console.print()


def get_enabled_tools() -> list[BaseTool]:
    """Get all tools from enabled services.

    Filters tools based on current scope setting:
    - Standard: only standard tools
    - Extended: standard + extended tools
    - Privileged: all tools

    Returns:
        List of LangChain tools from all enabled services.
    """
    from sdrbot_cli.services.registry import get_tool_scope_setting, load_config
    from sdrbot_cli.tools import is_tool_allowed

    config = load_config()
    tools = []
    current_scope = get_tool_scope_setting()

    for service_name in SERVICES:
        if not config.is_enabled(service_name):
            continue

        # Tracing services provide callbacks, not tools
        if service_name in TRACING_SERVICES:
            continue

        # Import service module and get its tools
        try:
            service_module = __import__(
                f"sdrbot_cli.services.{service_name}", fromlist=["get_tools"]
            )
            if hasattr(service_module, "get_tools"):
                service_tools = service_module.get_tools()
                # Filter tools based on current scope
                service_tools = [t for t in service_tools if is_tool_allowed(t, current_scope)]
                tools.extend(service_tools)
        except ImportError as e:
            # Log warning but continue
            import sys

            print(f"Warning: Could not load {service_name}: {e}", file=sys.stderr)

    return tools


__all__ = [
    "SERVICES",
    "SYNCABLE_SERVICES",
    "TRACING_SERVICES",
    "enable_service",
    "disable_service",
    "sync_service",
    "resync_service",
    "sync_enabled_services_if_needed",
    "get_enabled_tools",
]
