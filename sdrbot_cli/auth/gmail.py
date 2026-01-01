"""Gmail Authentication Manager using OAuth 2.0."""

import json
import os
import time
import urllib.parse
import webbrowser

import keyring
import requests

from sdrbot_cli.auth.oauth_server import wait_for_callback
from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_gmail"
TOKEN_KEY = "oauth_token"

CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback/gmail"

# Google OAuth endpoints
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Gmail API scope - full access
# https://developers.google.com/gmail/api/auth/scopes
SCOPES = [
    "https://mail.google.com/",  # Full access to Gmail
]

# Buffer time (in seconds) before token expiry to trigger proactive refresh
TOKEN_EXPIRY_BUFFER = 300  # 5 minutes


def is_configured() -> bool:
    """Check if Gmail OAuth credentials are configured."""
    return bool(CLIENT_ID and CLIENT_SECRET)


def get_auth_url() -> str:
    """Generate the Google OAuth URL."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # Request refresh token
        "prompt": "consent",  # Force consent to ensure refresh token is returned
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def login() -> dict | None:
    """Perform the full OAuth login flow."""
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            f"[{COLORS['tool']}]Gmail OAuth not configured. "
            f"Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET.[/{COLORS['tool']}]"
        )
        return None

    console.print(
        f"[{COLORS['primary']}]Initiating Gmail OAuth Authentication...[/{COLORS['primary']}]"
    )

    auth_url = get_auth_url()
    console.print(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    console.print(f"[{COLORS['dim']}]Waiting for callback...[/{COLORS['dim']}]")

    # Use shared OAuth server with timeout support
    code, _ = wait_for_callback(
        callback_path="/callback/gmail",
        port=8080,
        timeout=300.0,
    )

    if not code:
        console.print(
            f"[{COLORS['tool']}]OAuth flow timed out or was cancelled.[/{COLORS['tool']}]"
        )
        return None

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

    response = requests.post(TOKEN_URL, data=payload)
    response.raise_for_status()
    token_data = response.json()

    # Add expiry timestamp for proactive refresh
    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)

    # Save token
    save_token(token_data)
    console.print(
        f"[{COLORS['primary']}]Successfully authenticated with Gmail![/{COLORS['primary']}]"
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


def clear_credentials() -> None:
    """Clear stored Gmail credentials from keyring."""
    try:
        keyring.delete_password(SERVICE_NAME, TOKEN_KEY)
    except keyring.errors.PasswordDeleteError:
        pass  # Already cleared


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
        response = requests.post(TOKEN_URL, data=payload)
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


def get_access_token() -> str | None:
    """Get a valid access token, refreshing if necessary.

    Returns:
        Valid access token string, or None if not authenticated.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            f"[{COLORS['tool']}]Gmail integration disabled: GMAIL_CLIENT_ID/SECRET not found.[/{COLORS['tool']}]"
        )
        return None

    # Try to use stored OAuth token
    token_data = get_stored_token()

    if not token_data:
        console.print(
            f"[{COLORS['tool']}]No stored Gmail credentials found. Initiating login...[/{COLORS['tool']}]"
        )
        token_data = login()
        if not token_data:
            return None

    # Proactive refresh if token is expired or about to expire
    if _is_token_expired(token_data):
        console.print(f"[{COLORS['dim']}]Gmail token expired, refreshing...[/{COLORS['dim']}]")
        token_data = _refresh_token(token_data)
        if not token_data:
            console.print(
                f"[{COLORS['tool']}]Token refresh failed. Re-authenticating...[/{COLORS['tool']}]"
            )
            token_data = login()
            if not token_data:
                return None

    return token_data.get("access_token")


def get_headers() -> dict | None:
    """Get authorization headers for Gmail API requests.

    Returns:
        Dict with Authorization header, or None if not authenticated.
    """
    token = get_access_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}
