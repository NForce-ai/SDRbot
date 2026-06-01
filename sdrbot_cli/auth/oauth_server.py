"""Shared OAuth callback server with timeout support."""

import threading
import urllib.parse
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer

# Global server instance for cleanup
_active_server: HTTPServer | None = None
_server_lock = threading.Lock()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Generic OAuth callback handler."""

    # Class-level storage for callback data
    callback_path: str = "/callback"
    auth_code: str | None = None
    error: str | None = None
    extra_params: dict = {}
    on_success_html: str = (
        "<h1>Authorization Successful!</h1>"
        "<p>You can close this window and return to the terminal.</p>"
    )

    def do_GET(self):
        """Handle the callback request."""
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == self.callback_path:
            query_params = urllib.parse.parse_qs(parsed_path.query)
            if "code" in query_params:
                OAuthCallbackHandler.auth_code = query_params["code"][0]
                # Store any extra params (like Zoho's location, accounts-server)
                OAuthCallbackHandler.extra_params = {
                    k: v[0] for k, v in query_params.items() if k != "code"
                }
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(self.on_success_html.encode())
            else:
                OAuthCallbackHandler.error = query_params.get("error", ["Unknown error"])[0]
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    f"<h1>Authorization Failed</h1><p>{OAuthCallbackHandler.error}</p>".encode()
                )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Silence logs."""
        pass


class TimeoutHTTPServer(HTTPServer):
    """HTTPServer with timeout support."""

    allow_reuse_address = True  # sets SO_REUSEADDR before bind (via server_bind)

    def __init__(self, server_address, RequestHandlerClass, timeout: float = 1.0):
        super().__init__(server_address, RequestHandlerClass)
        # Set socket timeout so handle_request() returns periodically
        self.socket.settimeout(timeout)

    def handle_timeout(self):
        """Called when timeout expires without a request."""
        pass


def reset_handler():
    """Reset the handler state for a new OAuth flow."""
    OAuthCallbackHandler.auth_code = None
    OAuthCallbackHandler.error = None
    OAuthCallbackHandler.extra_params = {}


def wait_for_callback(
    callback_path: str = "/callback",
    port: int = 8080,
    timeout: float = 300.0,  # 5 minutes default
    check_cancelled: Callable[[], bool] | None = None,
    on_ready: Callable[[], None] | None = None,
) -> tuple[str | None, dict]:
    """
    Start a local server and wait for an OAuth callback.

    Args:
        callback_path: The path to listen for (e.g., "/callback/zohocrm")
        port: Port to listen on
        timeout: Maximum time to wait in seconds
        check_cancelled: Optional callback to check if operation was cancelled
        on_ready: Optional callback invoked once the socket is bound and listening

    Returns:
        Tuple of (auth_code, extra_params) or (None, {}) if timed out/cancelled

    Raises:
        OSError: If port is already in use
    """
    global _active_server

    # Shutdown any existing server first
    shutdown_server()

    # Configure handler
    OAuthCallbackHandler.callback_path = callback_path
    reset_handler()

    # Create server with timeout
    server_address = ("", port)

    with _server_lock:
        try:
            # SO_REUSEADDR must be set before bind; subclass server_bind to do that.
            server = TimeoutHTTPServer(server_address, OAuthCallbackHandler, timeout=1.0)
            _active_server = server
        except OSError as e:
            if "Address already in use" in str(e):
                raise OSError(
                    f"Port {port} is already in use. "
                    "Please wait a moment and try again, or restart the application."
                ) from e
            raise

    # Notify caller that the socket is now bound and accepting connections.
    if on_ready:
        on_ready()

    try:
        elapsed = 0.0
        while elapsed < timeout:
            if check_cancelled and check_cancelled():
                return None, {}

            if OAuthCallbackHandler.auth_code is not None:
                return OAuthCallbackHandler.auth_code, OAuthCallbackHandler.extra_params

            if OAuthCallbackHandler.error is not None:
                raise ValueError(f"OAuth error: {OAuthCallbackHandler.error}")

            # Handle one request with timeout
            try:
                server.handle_request()
            except TimeoutError:
                pass  # Expected - just loop again
            elapsed += 1.0  # Approximate, based on socket timeout

        # Timeout reached
        return None, {}

    finally:
        shutdown_server()


def shutdown_server():
    """Shutdown the active OAuth server if running."""
    global _active_server

    with _server_lock:
        if _active_server is not None:
            try:
                # Just close the socket - don't call shutdown() as that's for serve_forever()
                _active_server.server_close()
            except Exception:
                pass
            _active_server = None
