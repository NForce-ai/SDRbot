"""MCP client session management."""

from __future__ import annotations

import contextlib
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
_streamable_http_client = None
_create_mcp_http_client = None
_OAuthClientProvider = None

try:
    from mcp import ClientSession as _ClientSession
    from mcp import StdioServerParameters as _StdioServerParameters
    from mcp.client.sse import sse_client as _sse_client
    from mcp.client.stdio import stdio_client as _stdio_client
    from mcp.client.streamable_http import streamable_http_client as _streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client as _create_mcp_http_client

    MCP_AVAILABLE = True
except ImportError:
    pass

try:
    from mcp.client.auth.oauth2 import OAuthClientProvider as _OAuthClientProvider
except ImportError:
    pass

if TYPE_CHECKING:
    from mcp import ClientSession


def _unwrap_error(exc: BaseException) -> str:
    """Unwrap ExceptionGroup/TaskGroup errors to show underlying cause."""
    # Python 3.11+ ExceptionGroup
    if hasattr(exc, "exceptions"):
        subs = getattr(exc, "exceptions", None)
        if subs:
            messages = []
            for sub in subs:
                msg = _unwrap_error(sub)
                if msg not in messages:
                    messages.append(msg)
            return "; ".join(messages) if messages else str(exc)

    # httpx.HTTPStatusError — include status code, URL, and response body
    if hasattr(exc, "response"):
        response = getattr(exc, "response", None)
        if response is not None:
            status = response.status_code
            reason = getattr(response, "reason_phrase", "")
            url = str(response.url) if hasattr(response, "url") else ""
            body = ""
            try:
                raw = response.read()
                body = raw.decode("utf-8", errors="replace")[:500]
            except Exception:
                try:
                    body = response.text[:500]
                except Exception:
                    pass
            if body:
                return f"HTTP {status} {reason} for {url}: {body}"
            return f"HTTP {status} {reason} for {url}"

    return str(exc)


@contextlib.asynccontextmanager
async def _streamable_http_no_get(
    url: str, http_client=None, terminate_on_close: bool = True
):
    """StreamableHTTP transport that skips the GET stream.

    Monkey-patches _is_initialized_notification to return False for the
    duration of this context, preventing the GET stream from starting.
    The patch is undone when the context exits.
    """
    from mcp.client.streamable_http import StreamableHTTPTransport

    _original = StreamableHTTPTransport._is_initialized_notification

    def _noop_is_init(self, message):
        return False

    StreamableHTTPTransport._is_initialized_notification = _noop_is_init

    try:
        async with _streamable_http_client(
            url,
            http_client=http_client,
            terminate_on_close=terminate_on_close,
        ) as streams:
            yield streams
    finally:
        StreamableHTTPTransport._is_initialized_notification = _original


@dataclass
class MCPServerConnection:
    """Manages a single MCP server connection."""

    name: str
    config: dict[str, Any]
    session: ClientSession | None = None
    tools: list[Any] = field(default_factory=list)
    _context_stack: list[Any] = field(default_factory=list)
    last_error: str = ""

    async def connect(self) -> bool:
        """
        Start the server and establish connection.

        Returns:
            True if connection successful, False otherwise
        """
        if not MCP_AVAILABLE:
            msg = "MCP SDK not installed. Run: pip install mcp"
            self.last_error = msg
            console.print(f"[red]{msg}[/red]")
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
                auth_config = self.config.get("auth", {})
                auth_type = auth_config.get("type", "none") if auth_config else "none"

                if auth_type == "oauth":
                    # Use MCP SDK's OAuthClientProvider for full OAuth 2.0 flow
                    if _OAuthClientProvider is None:
                        msg = "OAuth support requires mcp package with auth module"
                        self.last_error = msg
                        console.print(f"[red]{msg}[/red]")
                        return False

                    from .oauth import create_oauth_provider

                    scopes = auth_config.get("scopes")
                    client_metadata_url = auth_config.get("client_metadata_url")
                    oauth_provider = create_oauth_provider(
                        self.name, self.config["url"], scopes, client_metadata_url
                    )
                    sse_ctx = _sse_client(self.config["url"], auth=oauth_provider)
                else:
                    # Build static auth headers
                    auth_headers = build_auth_headers(auth_config)
                    sse_ctx = _sse_client(self.config["url"], headers=auth_headers or None)

                streams = await sse_ctx.__aenter__()
                self._context_stack.append(sse_ctx)
                read_stream, write_stream = streams[0], streams[1]

            elif transport == "http":
                auth_config = self.config.get("auth", {})
                auth_type = auth_config.get("type", "none") if auth_config else "none"

                if auth_type == "oauth":
                    if _OAuthClientProvider is None:
                        msg = "OAuth support requires mcp package with auth module"
                        self.last_error = msg
                        console.print(f"[red]{msg}[/red]")
                        return False

                    from .oauth import create_oauth_provider

                    scopes = auth_config.get("scopes")
                    client_metadata_url = auth_config.get("client_metadata_url")
                    oauth_provider = create_oauth_provider(
                        self.name, self.config["url"], scopes, client_metadata_url
                    )
                    http_client = _create_mcp_http_client(auth=oauth_provider)
                    http_ctx = _streamable_http_no_get(
                        self.config["url"], http_client=http_client
                    )
                else:
                    auth_headers = build_auth_headers(auth_config)
                    if auth_headers:
                        http_client = _create_mcp_http_client(headers=auth_headers)
                        http_ctx = _streamable_http_no_get(
                            self.config["url"], http_client=http_client
                        )
                    else:
                        http_ctx = _streamable_http_no_get(self.config["url"])

                streams = await http_ctx.__aenter__()
                self._context_stack.append(http_ctx)
                read_stream, write_stream, _ = streams

            else:
                msg = f"Unknown transport: {transport}"
                self.last_error = msg
                console.print(f"[red]{msg}[/red]")
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

        except BaseException as e:
            # Unwrap ExceptionGroup/TaskGroup errors to show the real cause
            msg = f"Failed to connect to {self.name}: {_unwrap_error(e)}"
            self.last_error = msg
            console.print(f"[red]{msg}[/red]")
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


async def test_mcp_connection(
    config: dict[str, Any], server_name: str = "test"
) -> tuple[bool, int, str]:
    """
    Test connection to an MCP server.

    Args:
        config: Server configuration dict
        server_name: Name for OAuth token storage (use real server name)

    Returns:
        (success, tool_count, error_message)
    """
    if not MCP_AVAILABLE:
        return False, 0, "MCP SDK not installed. Run: pip install mcp"

    conn = MCPServerConnection(name=server_name, config=config)

    try:
        success = await conn.connect()
        if success:
            tool_count = len(conn.tools)
            await conn.disconnect()
            return True, tool_count, ""
        return False, 0, conn.last_error or "Connection failed"
    except Exception as e:
        await conn.disconnect()
        return False, 0, str(e)
