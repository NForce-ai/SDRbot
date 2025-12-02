"""MCP server setup wizard."""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

from sdrbot_cli.config import COLORS, console
from sdrbot_cli.mcp.client import MCP_AVAILABLE, test_mcp_connection
from sdrbot_cli.mcp.config import (
    add_mcp_server,
    disable_mcp_server,
    enable_mcp_server,
    load_mcp_config,
    remove_mcp_server,
)

from .menu import CancelledError, show_choice_menu, show_menu


def get_mcp_status() -> str:
    """Get overall status string for MCP servers."""
    config = load_mcp_config()
    servers = config.get("servers", {})

    enabled_count = sum(1 for s in servers.values() if s.get("enabled", False))
    total_count = len(servers)

    if enabled_count > 0:
        return f"[green]✓ {enabled_count}/{total_count} enabled[/green]"
    elif total_count > 0:
        return f"[yellow]{total_count} configured[/yellow]"
    return "[dim]• None configured[/dim]"


async def run_mcp_wizard(return_to_setup: bool = False) -> str | None:
    """
    MCP Server management wizard.

    Args:
        return_to_setup: If True, show "← Back to Setup" option.
                        If False (from /mcp), show "Exit" instead.

    Returns:
        "setup" if user wants to go back to setup wizard,
        None otherwise
    """
    if not MCP_AVAILABLE:
        console.print("[yellow]MCP SDK not installed. To use MCP servers, install with:[/yellow]")
        console.print("[dim]  pip install mcp[/dim]")
        console.print()
        return "back" if return_to_setup else None

    try:
        return await _run_mcp_wizard_impl(return_to_setup)
    except CancelledError:
        return "back" if return_to_setup else None


async def _run_mcp_wizard_impl(return_to_setup: bool) -> str | None:
    """Implementation of MCP wizard."""
    while True:
        # Build menu options
        menu_items = [("add", "Add MCP Server", "")]

        # Load existing servers
        config = load_mcp_config()
        servers = config.get("servers", {})

        if servers:
            menu_items.append(("---", "──────────────", ""))

            for name, server_config in servers.items():
                enabled = server_config.get("enabled", False)
                tool_count = server_config.get("tool_count", "?")

                if enabled:
                    status = f"[green]✓ enabled ({tool_count} tools)[/green]"
                else:
                    status = "[dim]disabled[/dim]"

                menu_items.append((f"server:{name}", name, status))

        # Back/Exit option
        menu_items.append(("---", "──────────────", ""))
        if return_to_setup:
            menu_items.append(("back", "← Back to Setup", ""))
        else:
            menu_items.append(("exit", "Exit", ""))

        choice = await show_menu(menu_items, title="MCP Servers")

        if choice == "back":
            return "setup"
        elif choice == "exit" or choice is None:
            return None
        elif choice == "add":
            await _add_mcp_server()
        elif choice and choice.startswith("server:"):
            server_name = choice[7:]  # Remove "server:" prefix
            await _manage_mcp_server(server_name)


async def _add_mcp_server() -> None:
    """Wizard flow for adding a new MCP server."""
    console.print(f"\n[{COLORS['primary']}]Add MCP Server[/{COLORS['primary']}]")
    console.print(f"[{COLORS['dim']}](Press ESC to cancel)[/{COLORS['dim']}]\n")

    # Create key bindings for ESC
    bindings = KeyBindings()

    @bindings.add("escape")
    def _(event):
        event.app.exit(exception=CancelledError())

    @bindings.add("c-c")
    def _(event):
        event.app.exit(exception=CancelledError())

    session: PromptSession = PromptSession(key_bindings=bindings)

    try:
        # Get server name
        name = await session.prompt_async("Server name (e.g., 'github', 'filesystem'): ")
        name = name.strip()

        if not name:
            console.print("[red]Server name is required[/red]")
            return

        # Check for duplicate
        config = load_mcp_config()
        if name in config.get("servers", {}):
            console.print(f"[red]Server '{name}' already exists[/red]")
            return

        # Choose transport
        transport = await show_choice_menu(
            [
                ("stdio", "stdio - Run as subprocess (npx, uvx, python, etc.)"),
                ("http", "HTTP - Streamable HTTP (modern, recommended)"),
                ("sse", "SSE - Server-Sent Events (legacy)"),
            ],
            title="Transport type",
        )

        if transport == "stdio":
            # Get command
            command = await session.prompt_async("Command (e.g., 'npx', 'uvx', 'python'): ")
            command = command.strip()

            if not command:
                console.print("[red]Command is required[/red]")
                return

            # Get arguments
            args_str = await session.prompt_async(
                "Arguments (space-separated, e.g., '-y @modelcontextprotocol/server-github'): "
            )
            args = args_str.split() if args_str.strip() else []

            # Ask about environment variables
            env = {}
            if await _confirm("Add environment variables?"):
                console.print(
                    f"[{COLORS['dim']}]Enter env vars as KEY=VALUE, one per line. "
                    "Use ${{VAR}} to reference existing env vars. Empty line to finish.[/{COLORS['dim']}]"
                )
                while True:
                    env_line = await session.prompt_async("  ENV: ")
                    if not env_line.strip():
                        break
                    if "=" in env_line:
                        key, value = env_line.split("=", 1)
                        env[key.strip()] = value.strip()

            server_config = {
                "enabled": True,
                "transport": "stdio",
                "command": command,
                "args": args,
                "env": env,
            }

        else:  # HTTP or SSE
            url = await session.prompt_async("Server URL (e.g., 'http://localhost:8080/mcp'): ")
            url = url.strip()

            if not url:
                console.print("[red]URL is required[/red]")
                return

            # Ask about authentication
            auth_type = await show_choice_menu(
                [
                    ("none", "None - No authentication"),
                    ("bearer", "Bearer Token - Authorization: Bearer <token>"),
                    ("apikey", "API Key - X-API-Key: <key>"),
                    ("custom", "Custom Headers - Define your own headers"),
                ],
                title="Authentication",
            )

            auth_config: dict = {"type": auth_type}

            if auth_type == "bearer":
                console.print(
                    f"[{COLORS['dim']}]Use ${{VAR_NAME}} to reference environment variables[/{COLORS['dim']}]"
                )
                token = await session.prompt_async("Bearer token: ", is_password=True)
                token = token.strip()
                if token:
                    auth_config["token"] = token

            elif auth_type == "apikey":
                console.print(
                    f"[{COLORS['dim']}]Use ${{VAR_NAME}} to reference environment variables[/{COLORS['dim']}]"
                )
                api_key = await session.prompt_async("API Key: ", is_password=True)
                api_key = api_key.strip()
                if api_key:
                    auth_config["api_key"] = api_key

            elif auth_type == "custom":
                console.print(
                    f"[{COLORS['dim']}]Enter headers as KEY=VALUE, one per line. "
                    "Use ${{VAR}} to reference env vars. Empty line to finish.[/{COLORS['dim']}]"
                )
                headers = {}
                while True:
                    header_line = await session.prompt_async("  Header: ")
                    if not header_line.strip():
                        break
                    if "=" in header_line:
                        key, value = header_line.split("=", 1)
                        headers[key.strip()] = value.strip()
                if headers:
                    auth_config["headers"] = headers

            server_config = {
                "enabled": True,
                "transport": transport,  # "http" or "sse"
                "url": url,
                "auth": auth_config,
            }

        # Test connection
        console.print(f"\n[{COLORS['dim']}]Testing connection...[/{COLORS['dim']}]")

        success, tool_count, error = await test_mcp_connection(server_config)

        if success:
            console.print(f"[green]✓ Connected! Found {tool_count} tools[/green]")

            # Save configuration
            if transport == "stdio":
                add_mcp_server(
                    name=name,
                    transport="stdio",
                    command=server_config["command"],
                    args=server_config["args"],
                    env=server_config["env"],
                    enabled=True,
                )
            else:
                add_mcp_server(
                    name=name,
                    transport=transport,  # "http" or "sse"
                    url=server_config["url"],
                    auth=server_config.get("auth"),
                    enabled=True,
                )

            # Update tool count in config
            from sdrbot_cli.mcp.config import update_server_tool_count

            update_server_tool_count(name, tool_count)

            console.print(f"[green]✓ Added MCP server: {name}[/green]\n")
        else:
            console.print(f"[red]✗ Connection failed: {error}[/red]")

            if await _confirm("Save configuration anyway?"):
                if transport == "stdio":
                    add_mcp_server(
                        name=name,
                        transport="stdio",
                        command=server_config["command"],
                        args=server_config["args"],
                        env=server_config["env"],
                        enabled=False,  # Disabled since connection failed
                    )
                else:
                    add_mcp_server(
                        name=name,
                        transport=transport,  # "http" or "sse"
                        url=server_config["url"],
                        auth=server_config.get("auth"),
                        enabled=False,
                    )
                console.print(
                    f"[yellow]Saved {name} (disabled). Enable after fixing configuration.[/yellow]\n"
                )

    except CancelledError:
        console.print(f"\n[{COLORS['dim']}]Cancelled.[/{COLORS['dim']}]\n")


async def _manage_mcp_server(name: str) -> None:
    """Submenu for managing an existing MCP server."""
    config = load_mcp_config()
    server_config = config.get("servers", {}).get(name)

    if not server_config:
        console.print(f"[red]Server '{name}' not found[/red]")
        return

    while True:
        enabled = server_config.get("enabled", False)
        tool_count = server_config.get("tool_count", "?")
        transport = server_config.get("transport", "unknown")

        # Build info string
        if transport == "stdio":
            cmd = server_config.get("command", "")
            args = " ".join(server_config.get("args", []))
            info = f"{cmd} {args}"[:40]
        else:
            info = server_config.get("url", "")[:40]

        console.print(f"\n[{COLORS['primary']}]{name}[/{COLORS['primary']}]")
        console.print(f"[{COLORS['dim']}]Transport: {transport}[/{COLORS['dim']}]")
        console.print(f"[{COLORS['dim']}]Command/URL: {info}[/{COLORS['dim']}]")
        console.print(f"[{COLORS['dim']}]Tools: {tool_count}[/{COLORS['dim']}]\n")

        menu_items = []

        if enabled:
            menu_items.append(("disable", "Disable", ""))
        else:
            menu_items.append(("enable", "Enable", ""))

        menu_items.extend(
            [
                ("test", "Test Connection", ""),
                ("view_tools", f"View Tools ({tool_count})", ""),
                ("remove", "Remove Server", "[red]![/red]"),
                ("---", "──────────────", ""),
                ("back", "← Back", ""),
            ]
        )

        choice = await show_menu(menu_items, title=f"Manage {name}")

        if choice == "back" or choice is None:
            return

        elif choice == "enable":
            enable_mcp_server(name)
            console.print(f"[green]✓ Enabled {name}[/green]")
            # Refresh config
            config = load_mcp_config()
            server_config = config.get("servers", {}).get(name, {})

        elif choice == "disable":
            disable_mcp_server(name)
            console.print(f"[yellow]Disabled {name}[/yellow]")
            # Refresh config
            config = load_mcp_config()
            server_config = config.get("servers", {}).get(name, {})

        elif choice == "test":
            console.print(f"\n[{COLORS['dim']}]Testing connection...[/{COLORS['dim']}]")
            success, new_tool_count, error = await test_mcp_connection(server_config)

            if success:
                console.print(f"[green]✓ Connected! Found {new_tool_count} tools[/green]")
                from sdrbot_cli.mcp.config import update_server_tool_count

                update_server_tool_count(name, new_tool_count)
                # Refresh config
                config = load_mcp_config()
                server_config = config.get("servers", {}).get(name, {})
            else:
                console.print(f"[red]✗ Connection failed: {error}[/red]")

        elif choice == "view_tools":
            await _view_server_tools(name, server_config)

        elif choice == "remove":
            if await _confirm(f"Remove server '{name}'?"):
                remove_mcp_server(name)
                console.print(f"[green]✓ Removed {name}[/green]")
                return


async def _view_server_tools(name: str, server_config: dict) -> None:
    """View tools available from an MCP server."""
    console.print(f"\n[{COLORS['dim']}]Connecting to view tools...[/{COLORS['dim']}]")

    from sdrbot_cli.mcp.client import MCPServerConnection

    conn = MCPServerConnection(name=name, config=server_config)

    try:
        if await conn.connect():
            console.print(f"\n[{COLORS['primary']}]Tools from {name}:[/{COLORS['primary']}]\n")

            for tool in conn.tools:
                desc = tool.description or "No description"
                # Truncate long descriptions
                if len(desc) > 60:
                    desc = desc[:57] + "..."
                console.print(f"  [cyan]{tool.name}[/cyan]")
                console.print(f"    [dim]{desc}[/dim]")

            await conn.disconnect()
        else:
            console.print("[red]Failed to connect[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")

    # Wait for user to acknowledge
    console.print(f"\n[{COLORS['dim']}]Press Enter to continue...[/{COLORS['dim']}]")
    input()


async def _confirm(message: str) -> bool:
    """Simple yes/no confirmation."""
    from rich.prompt import Confirm

    return Confirm.ask(f"[{COLORS['primary']}]{message}[/]", default=False)
