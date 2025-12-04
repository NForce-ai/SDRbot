"""MCP server manager for handling multiple connections."""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool

from .client import MCP_AVAILABLE, MCPServerConnection
from .config import load_mcp_config, update_server_tool_count
from .tools import create_langchain_tool


@dataclass
class MCPManager:
    """Manages all MCP server connections."""

    connections: dict[str, MCPServerConnection] = field(default_factory=dict)
    _started: bool = False

    async def connect_enabled_servers(self) -> tuple[int, list[str]]:
        """
        Connect to all enabled MCP servers.

        Returns:
            Tuple of (number of successfully connected servers, list of failed server names)
        """
        if not MCP_AVAILABLE:
            return 0, []

        from .config import disable_mcp_server

        config = load_mcp_config()
        servers = config.get("servers", {})

        connected_count = 0
        failed_servers: list[str] = []

        for name, server_config in servers.items():
            if not server_config.get("enabled", False):
                continue

            conn = MCPServerConnection(name=name, config=server_config)

            if await conn.connect():
                self.connections[name] = conn
                tool_count = len(conn.tools)
                update_server_tool_count(name, tool_count)
                connected_count += 1
            else:
                # Disable the server since it failed to connect
                disable_mcp_server(name)
                failed_servers.append(name)

        self._started = True
        return connected_count, failed_servers

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for _name, conn in list(self.connections.items()):
            try:
                await conn.disconnect()
            except Exception:
                pass  # Ignore disconnect errors on shutdown

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


async def initialize_mcp() -> tuple[MCPManager, list[str]]:
    """Initialize MCP and connect to enabled servers.

    Returns:
        Tuple of (manager, list of failed server names)
    """
    manager = get_mcp_manager()
    failed_servers: list[str] = []
    if not manager._started:
        _, failed_servers = await manager.connect_enabled_servers()
    return manager, failed_servers


async def shutdown_mcp() -> None:
    """Shutdown MCP and disconnect from all servers."""
    global _manager
    if _manager is not None:
        await _manager.disconnect_all()
        _manager = None


async def reinitialize_mcp() -> tuple[MCPManager, list[str]]:
    """Reinitialize MCP - disconnect and reconnect to enabled servers.

    Returns:
        Tuple of (manager, list of failed server names)
    """
    manager = get_mcp_manager()
    await manager.disconnect_all()
    _, failed_servers = await manager.connect_enabled_servers()
    return manager, failed_servers
