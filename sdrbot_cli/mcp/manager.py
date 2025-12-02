"""MCP server manager for handling multiple connections."""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool

from sdrbot_cli.config import console

from .client import MCP_AVAILABLE, MCPServerConnection
from .config import load_mcp_config, update_server_tool_count
from .tools import create_langchain_tool


@dataclass
class MCPManager:
    """Manages all MCP server connections."""

    connections: dict[str, MCPServerConnection] = field(default_factory=dict)
    _started: bool = False

    async def connect_enabled_servers(self) -> int:
        """
        Connect to all enabled MCP servers.

        Returns:
            Number of successfully connected servers
        """
        if not MCP_AVAILABLE:
            return 0

        config = load_mcp_config()
        servers = config.get("servers", {})

        connected_count = 0

        for name, server_config in servers.items():
            if not server_config.get("enabled", False):
                continue

            conn = MCPServerConnection(name=name, config=server_config)

            console.print(f"[dim]Connecting to MCP server: {name}...[/dim]")

            if await conn.connect():
                self.connections[name] = conn
                tool_count = len(conn.tools)
                update_server_tool_count(name, tool_count)
                console.print(f"[green]✓ Connected to {name} ({tool_count} tools)[/green]")
                connected_count += 1
            else:
                console.print(f"[yellow]⚠ Failed to connect to {name}[/yellow]")

        self._started = True
        return connected_count

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name, conn in list(self.connections.items()):
            try:
                await conn.disconnect()
                console.print(f"[dim]Disconnected from MCP server: {name}[/dim]")
            except Exception as e:
                console.print(f"[yellow]Error disconnecting from {name}: {e}[/yellow]")

        self.connections.clear()
        self._started = False

    async def reconnect_server(self, name: str) -> bool:
        """
        Reconnect to a specific MCP server.

        Returns:
            True if successfully reconnected
        """
        # Disconnect if currently connected
        if name in self.connections:
            await self.connections[name].disconnect()
            del self.connections[name]

        # Load config and reconnect
        config = load_mcp_config()
        servers = config.get("servers", {})

        if name not in servers:
            return False

        server_config = servers[name]
        if not server_config.get("enabled", False):
            return False

        conn = MCPServerConnection(name=name, config=server_config)

        if await conn.connect():
            self.connections[name] = conn
            update_server_tool_count(name, len(conn.tools))
            return True

        return False

    def get_all_tools(self) -> list[BaseTool]:
        """
        Get LangChain tools for all connected servers.

        Returns:
            List of LangChain BaseTool instances
        """
        tools = []

        for name, conn in self.connections.items():
            for mcp_tool in conn.tools:
                tool = create_langchain_tool(name, mcp_tool, conn)
                tools.append(tool)

        return tools

    def get_server_tools(self, server_name: str) -> list[BaseTool]:
        """Get LangChain tools for a specific server."""
        if server_name not in self.connections:
            return []

        conn = self.connections[server_name]
        tools = []

        for mcp_tool in conn.tools:
            tool = create_langchain_tool(server_name, mcp_tool, conn)
            tools.append(tool)

        return tools

    def get_connected_servers(self) -> list[str]:
        """Get list of connected server names."""
        return list(self.connections.keys())

    def get_total_tool_count(self) -> int:
        """Get total number of tools across all connected servers."""
        return sum(len(conn.tools) for conn in self.connections.values())

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected."""
        return server_name in self.connections


# Global manager instance
_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """Get the global MCP manager instance."""
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager


async def initialize_mcp() -> MCPManager:
    """Initialize MCP and connect to enabled servers."""
    manager = get_mcp_manager()
    if not manager._started:
        await manager.connect_enabled_servers()
    return manager


async def shutdown_mcp() -> None:
    """Shutdown MCP and disconnect from all servers."""
    global _manager
    if _manager is not None:
        await _manager.disconnect_all()
        _manager = None


async def reinitialize_mcp() -> MCPManager:
    """Reinitialize MCP - disconnect and reconnect to enabled servers."""
    manager = get_mcp_manager()
    await manager.disconnect_all()
    await manager.connect_enabled_servers()
    return manager
