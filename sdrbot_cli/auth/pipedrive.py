"""Pipedrive Authentication Manager.

Supports both API Token and OAuth 2.0 authentication methods.
"""

import json
import os
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import keyring
import requests

from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_pipedrive"
TOKEN_KEY = "oauth_token"

# OAuth endpoints
OAUTH_AUTHORIZE_URL = "https://oauth.pipedrive.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://oauth.pipedrive.com/oauth/token"
API_BASE_URL = "https://api.pipedrive.com/v1"

CLIENT_ID = os.getenv("PIPEDRIVE_CLIENT_ID")
CLIENT_SECRET = os.getenv("PIPEDRIVE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback/pipedrive"

# Scopes for OAuth - request full access to CRM data
SCOPES = [
    "deals:full",
    "contacts:full",  # Covers persons and organizations
    "activities:full",
    "products:full",
    "leads:full",
    "admin",  # For pipelines, users, etc.
]

# Buffer time (in seconds) before token expiry to trigger proactive refresh
TOKEN_EXPIRY_BUFFER = 300  # 5 minutes


def is_configured() -> bool:
    """Check if Pipedrive is configured (Env vars)."""
    # Check for API Token
    if os.getenv("PIPEDRIVE_API_TOKEN"):
        return True
    # Check for OAuth
    if CLIENT_ID and CLIENT_SECRET:
        return True
    return False


class OAuthHandler(BaseHTTPRequestHandler):
    """Handle the OAuth callback."""

    auth_code: str | None = None

    def do_GET(self):
        """Handle the callback request."""
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/callback/pipedrive":
            query_params = urllib.parse.parse_qs(parsed_path.query)
            if "code" in query_params:
                OAuthHandler.auth_code = query_params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h1>Authorization Successful!</h1><p>You can close this window and return to the terminal.</p>"
                )
            else:
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                error = query_params.get("error", ["Unknown error"])[0]
                self.wfile.write(f"<h1>Authorization Failed</h1><p>{error}</p>".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Silence logs."""
        pass


def get_auth_url() -> str:
    """Generate the Pipedrive OAuth URL."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": "sdrbot",  # Optional state for CSRF protection
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def login() -> dict | None:
    """Perform the full OAuth login flow."""
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            f"[{COLORS['tool']}]Pipedrive OAuth requires PIPEDRIVE_CLIENT_ID and PIPEDRIVE_CLIENT_SECRET.[/{COLORS['tool']}]"
        )
        return None

    console.print(
        f"[{COLORS['primary']}]Initiating Pipedrive OAuth Authentication...[/{COLORS['primary']}]"
    )

    auth_url = get_auth_url()
    console.print(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    # Start local server to catch callback
    server_address = ("", 8080)
    HTTPServer.allow_reuse_address = True
    httpd = HTTPServer(server_address, OAuthHandler)

    console.print(f"[{COLORS['dim']}]Waiting for callback...[/{COLORS['dim']}]")
    OAuthHandler.auth_code = None

    while OAuthHandler.auth_code is None:
        httpd.handle_request()

    code = OAuthHandler.auth_code
    console.print(
        f"[{COLORS['primary']}]Authorization code received! Exchanging for token...[/{COLORS['primary']}]"
    )

    # Exchange code for token
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }

    response = requests.post(OAUTH_TOKEN_URL, data=payload)
    response.raise_for_status()
    token_data = response.json()

    # Add expiry timestamp for proactive refresh
    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)

    # Save token
    save_token(token_data)
    console.print(
        f"[{COLORS['primary']}]Successfully authenticated with Pipedrive via OAuth![/{COLORS['primary']}]"
    )

    return token_data


def save_token(token_data: dict) -> None:
    """Save token data to keyring."""
    keyring.set_password(SERVICE_NAME, TOKEN_KEY, json.dumps(token_data))


def get_stored_token() -> dict | None:
    """Retrieve token data from keyring."""
    data = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    if data:
        return json.loads(data)
    return None


def _is_token_expired(token_data: dict, buffer_seconds: int = TOKEN_EXPIRY_BUFFER) -> bool:
    """Check if the access token is expired or will expire soon.

    Args:
        token_data: Token data dictionary containing expires_at.
        buffer_seconds: Seconds before actual expiry to consider token expired.

    Returns:
        True if token is expired or will expire within buffer_seconds.
    """
    expires_at = token_data.get("expires_at")
    if not expires_at:
        # No expiry info, assume valid (legacy tokens without expires_at)
        return False
    return time.time() >= (expires_at - buffer_seconds)


def _refresh_token(token_data: dict) -> dict | None:
    """Refresh the access token using the refresh token.

    Args:
        token_data: Current token data with refresh_token.

    Returns:
        Updated token data, or None if refresh failed.
    """
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None

    try:
        payload = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        }
        response = requests.post(OAUTH_TOKEN_URL, data=payload)
        response.raise_for_status()
        new_token_data = response.json()

        # Merge new data (refresh token may not be returned on refresh)
        token_data.update(new_token_data)
        token_data["expires_at"] = int(time.time()) + new_token_data.get("expires_in", 3600)
        save_token(token_data)

        return token_data
    except Exception as e:
        console.print(f"[{COLORS['tool']}]Token refresh failed: {e}[/{COLORS['tool']}]")
        return None


class PipedriveClient:
    """Simple Pipedrive REST client wrapper."""

    def __init__(self, api_token: str | None = None, access_token: str | None = None):
        """Initialize client with either API token or OAuth access token.

        Args:
            api_token: Pipedrive API token (from settings).
            access_token: OAuth access token.
        """
        self.api_token = api_token
        self.access_token = access_token
        self.base_url = API_BASE_URL

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an authenticated request to Pipedrive API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            endpoint: API endpoint (e.g., "/deals").
            **kwargs: Additional arguments for requests.

        Returns:
            JSON response as dict.
        """
        url = f"{self.base_url}{endpoint}"

        # Set up authentication
        headers = kwargs.pop("headers", {})

        if self.api_token:
            # API token goes in query params
            params = kwargs.pop("params", {})
            params["api_token"] = self.api_token
            kwargs["params"] = params
        elif self.access_token:
            # OAuth token goes in Authorization header
            headers["Authorization"] = f"Bearer {self.access_token}"

        headers["Content-Type"] = "application/json"
        kwargs["headers"] = headers

        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get(self, endpoint: str, **kwargs) -> dict:
        """Make a GET request."""
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> dict:
        """Make a POST request."""
        return self._request("POST", endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs) -> dict:
        """Make a PUT request."""
        return self._request("PUT", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> dict:
        """Make a DELETE request."""
        return self._request("DELETE", endpoint, **kwargs)


def get_pipedrive_client() -> PipedriveClient | None:
    """Get an authenticated Pipedrive client.

    Checks for API token first, then falls back to OAuth.

    Returns:
        Authenticated PipedriveClient, or None if auth fails.
    """
    # 1. Check for API Token (simplest method)
    api_token = os.getenv("PIPEDRIVE_API_TOKEN")
    if api_token:
        console.print(f"[{COLORS['primary']}]Using Pipedrive API Token.[/{COLORS['primary']}]")
        client = PipedriveClient(api_token=api_token)
        # Test the connection
        try:
            client.get("/users/me")
            return client
        except Exception as e:
            console.print(f"[{COLORS['tool']}]Pipedrive API token invalid: {e}[/{COLORS['tool']}]")
            return None

    # 2. Fall back to OAuth
    # Re-read env vars in case they changed
    client_id = os.getenv("PIPEDRIVE_CLIENT_ID")
    client_secret = os.getenv("PIPEDRIVE_CLIENT_SECRET")

    if not client_id or not client_secret:
        console.print(
            f"[{COLORS['tool']}]Pipedrive integration disabled: No PIPEDRIVE_API_TOKEN or PIPEDRIVE_CLIENT_ID/SECRET found.[/{COLORS['tool']}]"
        )
        return None

    # Update module-level vars
    global CLIENT_ID, CLIENT_SECRET
    CLIENT_ID = client_id
    CLIENT_SECRET = client_secret

    # Try to use stored OAuth token
    token_data = get_stored_token()

    if not token_data:
        console.print(
            f"[{COLORS['tool']}]No stored Pipedrive OAuth credentials found. Initiating login...[/{COLORS['tool']}]"
        )
        token_data = login()
        if not token_data:
            return None

    # Proactive refresh if token is expired or about to expire
    if _is_token_expired(token_data):
        console.print(f"[{COLORS['dim']}]Pipedrive token expired, refreshing...[/{COLORS['dim']}]")
        token_data = _refresh_token(token_data)
        if not token_data:
            console.print(
                f"[{COLORS['tool']}]Token refresh failed. Re-authenticating...[/{COLORS['tool']}]"
            )
            token_data = login()
            if not token_data:
                return None

    client = PipedriveClient(access_token=token_data["access_token"])

    # Test the connection
    try:
        client.get("/users/me")
        return client
    except Exception as e:
        # Check if it's an auth error
        is_auth_error = "401" in str(e) or "Unauthorized" in str(e)

        if is_auth_error:
            console.print(
                f"[{COLORS['dim']}]Pipedrive session invalid, attempting refresh...[/{COLORS['dim']}]"
            )
            token_data = _refresh_token(token_data) if token_data else None
            if token_data:
                return PipedriveClient(access_token=token_data["access_token"])

            # Refresh failed, re-login
            console.print(
                f"[{COLORS['tool']}]Refresh failed. Re-authenticating...[/{COLORS['tool']}]"
            )
            token_data = login()
            if token_data:
                return PipedriveClient(access_token=token_data["access_token"])
            return None

        console.print(f"[{COLORS['tool']}]Pipedrive client error: {e}[/{COLORS['tool']}]")
        return None
