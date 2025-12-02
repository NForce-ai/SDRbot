"""MCP client session management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sdrbot_cli.config import console

from .config import build_auth_headers, resolve_env_vars

# Import MCP SDK types - these will be available after adding the dependency
MCP_AVAILABLE = False
_ClientSession = None
_StdioServerParameters = None
_stdio_client = None
_sse_client = None
_streamablehttp_client = None

try:
    from mcp import ClientSession as _ClientSession
    from mcp import StdioServerParameters as _StdioServerParameters
    from mcp.client.sse import sse_client as _sse_client
    from mcp.client.stdio import stdio_client as _stdio_client

    MCP_AVAILABLE = True

    # Try to import streamable HTTP client (newer MCP versions)
    try:
        from mcp.client.streamable_http import streamablehttp_client as _streamablehttp_client
    except ImportError:
        pass
except ImportError:
    pass

if TYPE_CHECKING:
    from mcp import ClientSession


@dataclass
class MCPServerConnection:
    """Manages a single MCP server connection."""

    name: str
    config: dict[str, Any]
    session: ClientSession | None = None
    tools: list[Any] = field(default_factory=list)
    _context_stack: list[Any] = field(default_factory=list)

    async def connect(self) -> bool:
        """
        Start the server and establish connection.

        Returns:
            True if connection successful, False otherwise
        """
        if not MCP_AVAILABLE:
            console.print("[red]MCP SDK not installed. Run: pip install mcp[/red]")
            return False

        try:
            transport = self.config.get("transport", "stdio")

            if transport == "stdio":
                # Resolve environment variables
                env = resolve_env_vars(self.config.get("env", {}))
                # Merge with current environment, but remove VIRTUAL_ENV
                # to avoid conflicts with uv/other tools that detect virtualenvs
                full_env = {**os.environ, **env}
                full_env.pop("VIRTUAL_ENV", None)

                params = _StdioServerParameters(
                    command=self.config["command"],
                    args=self.config.get("args", []),
                    env=full_env,
                )

                # Enter stdio_client context
                # Suppress verbose logging from mcp-remote and similar tools
                devnull = open(os.devnull, "w")  # noqa: SIM115
                self._context_stack.append(devnull)  # Track for cleanup
                stdio_ctx = _stdio_client(params, errlog=devnull)
                streams = await stdio_ctx.__aenter__()
                self._context_stack.append(stdio_ctx)
                read_stream, write_stream = streams

            elif transport == "sse":
                # Build auth headers if configured
                auth_headers = build_auth_headers(self.config.get("auth"))

                # Enter sse_client context
                sse_ctx = _sse_client(self.config["url"], headers=auth_headers or None)
                streams = await sse_ctx.__aenter__()
                self._context_stack.append(sse_ctx)
                read_stream, write_stream = streams[0], streams[1]

            elif transport == "http":
                # Streamable HTTP transport (modern MCP)
                if _streamablehttp_client is None:
                    console.print(
                        "[red]Streamable HTTP client not available. "
                        "Update MCP SDK: pip install --upgrade mcp[/red]"
                    )
                    return False

                # Build auth headers if configured
                auth_headers = build_auth_headers(self.config.get("auth"))

                http_ctx = _streamablehttp_client(self.config["url"], headers=auth_headers or None)
                streams = await http_ctx.__aenter__()
                self._context_stack.append(http_ctx)
                # Returns (read_stream, write_stream, get_session_id)
                read_stream, write_stream = streams[0], streams[1]

            else:
                console.print(f"[red]Unknown transport: {transport}[/red]")
                return False

            # Create and initialize session
            self.session = _ClientSession(read_stream, write_stream)
            await self.session.__aenter__()
            self._context_stack.append(self.session)

            await self.session.initialize()

            # Fetch available tools
            result = await self.session.list_tools()
            self.tools = result.tools if hasattr(result, "tools") else []

            return True

        except Exception as e:
            console.print(f"[red]Failed to connect to {self.name}: {e}[/red]")
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Clean up connection."""
        import asyncio

        # Exit contexts in reverse order, but keep devnull open until the end
        devnull_ctx = None
        other_contexts = []

        for ctx in self._context_stack:
            if hasattr(ctx, "close") and not hasattr(ctx, "__aexit__"):
                devnull_ctx = ctx  # This is the devnull file handle
            else:
                other_contexts.append(ctx)

        # Close async contexts first (in reverse order), with timeout
        for ctx in reversed(other_contexts):
            try:
                if hasattr(ctx, "__aexit__"):
                    await asyncio.wait_for(
                        ctx.__aexit__(None, None, None),
                        timeout=2.0,
                    )
            except (TimeoutError, asyncio.CancelledError):
                # Subprocess didn't exit cleanly, that's ok
                pass
            except Exception:
                pass

        # Now close devnull last (so stderr stays suppressed during shutdown)
        if devnull_ctx:
            try:
                devnull_ctx.close()
            except Exception:
                pass

        self._context_stack.clear()
        self.session = None
        self.tools = []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Call a tool on this server.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result content
        """
        if not self.session:
            raise RuntimeError(f"Not connected to server {self.name}")

        result = await self.session.call_tool(tool_name, arguments)
        return result.content

    def get_tool_names(self) -> list[str]:
        """Get list of available tool names."""
        return [tool.name for tool in self.tools]


async def test_mcp_connection(config: dict[str, Any]) -> tuple[bool, int, str]:
    """
    Test connection to an MCP server.

    Args:
        config: Server configuration dict

    Returns:
        (success, tool_count, error_message)
    """
    if not MCP_AVAILABLE:
        return False, 0, "MCP SDK not installed. Run: pip install mcp"

    conn = MCPServerConnection(name="test", config=config)

    try:
        success = await conn.connect()
        if success:
            tool_count = len(conn.tools)
            await conn.disconnect()
            return True, tool_count, ""
        return False, 0, "Connection failed"
    except Exception as e:
        await conn.disconnect()
        return False, 0, str(e)
