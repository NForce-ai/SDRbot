"""MCP OAuth 2.0 integration using the MCP SDK's OAuthClientProvider."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import webbrowser
from pathlib import Path
from typing import Any

from sdrbot_cli.config import get_config_dir

logger = logging.getLogger(__name__)

# Guard MCP SDK imports - the SDK may not be installed
try:
    from mcp.client.auth.oauth2 import OAuthClientProvider
    from mcp.shared.auth import (
        OAuthClientInformationFull,
        OAuthClientMetadata,
        OAuthToken,
    )

    _OAUTH_AVAILABLE = True
except ImportError:
    _OAUTH_AVAILABLE = False
    OAuthClientProvider = None  # type: ignore
    OAuthClientInformationFull = None  # type: ignore
    OAuthClientMetadata = None  # type: ignore
    OAuthToken = None  # type: ignore


def get_oauth_token_path(server_name: str) -> Path:
    """Get the path for a server's OAuth token storage file."""
    return get_config_dir() / "mcp_oauth" / f"{server_name}.json"


class FileTokenStorage:
    """Stores OAuth tokens and client info on disk per server."""

    def __init__(self, server_name: str) -> None:
        self.server_name = server_name
        self._path = get_oauth_token_path(server_name)

    async def get_tokens(self):
        data = self._read()
        if not data or "tokens" not in data:
            return None
        if _OAUTH_AVAILABLE:
            try:
                return OAuthToken.model_validate(data["tokens"])
            except Exception:
                return None
        return None

    async def set_tokens(self, tokens) -> None:
        data = self._read() or {}
        if _OAUTH_AVAILABLE:
            data["tokens"] = tokens.model_dump(mode="json")
        else:
            data["tokens"] = tokens
        self._write(data)

    async def get_client_info(self):
        data = self._read()
        if not data or "client_info" not in data:
            return None
        if _OAUTH_AVAILABLE:
            try:
                return OAuthClientInformationFull.model_validate(data["client_info"])
            except Exception:
                return None
        return None

    async def set_client_info(self, client_info) -> None:
        data = self._read() or {}
        if _OAUTH_AVAILABLE:
            data["client_info"] = client_info.model_dump(mode="json")
        else:
            data["client_info"] = client_info
        self._write(data)

    def _read(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2))

    def delete(self) -> None:
        """Remove stored tokens for this server."""
        if self._path.exists():
            self._path.unlink()


# Shared state between _open_browser and _wait_for_callback.
# The MCP SDK calls redirect_handler (browser open) BEFORE callback_handler,
# so we must start the local server in the redirect step to avoid a race where
# the browser receives the auth code and hits localhost:8080 before the server
# is listening.
_callback_future: "asyncio.Future[tuple[str | None, dict]] | None" = None


async def _open_browser(url: str) -> None:
    """Redirect handler: start callback server, then open the authorization URL.

    The server thread signals `_server_ready` once the socket is bound, so the
    browser only opens after localhost:8080 is definitely listening.
    """
    from sdrbot_cli.auth.oauth_server import reset_handler, wait_for_callback

    global _callback_future

    logger.info(f"Opening browser for OAuth: {url}")

    loop = asyncio.get_running_loop()
    _callback_future = loop.create_future()
    _server_ready = threading.Event()
    _server_start_error: list[Exception] = []  # mutable container for thread→async communication

    reset_handler()

    def _run_server():
        try:
            result = wait_for_callback(
                callback_path="/callback",
                port=8080,
                timeout=300.0,
                on_ready=_server_ready.set,  # called directly in this thread — thread-safe
            )
            loop.call_soon_threadsafe(_callback_future.set_result, result)
        except Exception as exc:
            _server_start_error.append(exc)
            _server_ready.set()  # unblock the waiter even on failure
            loop.call_soon_threadsafe(_callback_future.set_exception, exc)

    threading.Thread(target=_run_server, daemon=True).start()

    # Wait until the socket is confirmed bound (or fails), then check before opening browser.
    await loop.run_in_executor(None, lambda: _server_ready.wait(timeout=5.0))

    if _server_start_error:
        raise _server_start_error[0]

    opened = webbrowser.open(url)
    if not opened:
        logger.warning(
            "Failed to open browser automatically. "
            f"Please open this URL manually:\n{url}"
        )
        from sdrbot_cli.config import console

        console.print(
            f"\n[yellow]Could not open browser automatically.[/yellow]\n"
            f"[bold]Please open this URL in your browser:[/bold]\n"
            f"[cyan]{url}[/cyan]\n"
        )


async def _wait_for_callback() -> tuple[str, str | None]:
    """Callback handler: await the result from the server started in _open_browser.

    Returns (auth_code, state) tuple.
    """
    global _callback_future

    if _callback_future is None:
        raise RuntimeError("Callback server not started — redirect_handler must be called first")

    auth_code, extra = await _callback_future
    _callback_future = None

    if auth_code is None:
        raise RuntimeError("OAuth authorization timed out or was cancelled")
    state = extra.get("state") if extra else None
    return auth_code, state


def create_oauth_provider(
    server_name: str,
    server_url: str,
    scopes: str | None = None,
    client_metadata_url: str | None = None,
):
    """Create an OAuthClientProvider for an MCP server.

    Args:
        server_name: Unique name for token storage.
        server_url: The MCP server URL.
        scopes: Optional OAuth scopes (space-separated).
        client_metadata_url: Optional URL-based client ID (CIMD).

    Returns:
        Configured OAuthClientProvider.

    Raises:
        ImportError: If the MCP SDK with auth support is not installed.
    """
    if not _OAUTH_AVAILABLE:
        raise ImportError(
            "OAuth support requires mcp package with auth module. "
            "Install with: pip install mcp"
        )

    storage = FileTokenStorage(server_name)

    client_metadata = OAuthClientMetadata(
        redirect_uris=["http://localhost:8080/callback"],
        client_name=f"SDRbot ({server_name})",
        scope=scopes,
    )

    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=_open_browser,
        callback_handler=_wait_for_callback,
        timeout=300.0,
        client_metadata_url=client_metadata_url,
    )


def clear_oauth_tokens(server_name: str) -> None:
    """Delete stored OAuth tokens for a server."""
    storage = FileTokenStorage(server_name)
    storage.delete()
