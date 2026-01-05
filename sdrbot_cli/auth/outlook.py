"""Outlook Authentication Manager using Microsoft OAuth 2.0.

Uses Microsoft Graph API for email operations.
"""

import json
import os
import time
import urllib.parse
import webbrowser

import keyring
import requests

from sdrbot_cli.auth.oauth_server import wait_for_callback
from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_outlook"
TOKEN_KEY = "oauth_token"

CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback/outlook"

# Microsoft Identity Platform endpoints (common = multi-tenant)
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Microsoft Graph API scopes for mail
# https://learn.microsoft.com/en-us/graph/permissions-reference#mail-permissions
SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",  # Read and write mail
    "https://graph.microsoft.com/Mail.Send",  # Send mail
    "https://graph.microsoft.com/User.Read",  # Read user profile
    "offline_access",  # Required for refresh tokens
]

# Buffer time (in seconds) before token expiry to trigger proactive refresh
TOKEN_EXPIRY_BUFFER = 300  # 5 minutes


def is_configured() -> bool:
    """Check if Outlook OAuth credentials are configured."""
    return bool(CLIENT_ID and CLIENT_SECRET)


def get_auth_url() -> str:
    """Generate the Microsoft OAuth URL."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "response_mode": "query",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def login() -> dict | None:
    """Perform the full OAuth login flow."""
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            f"[{COLORS['tool']}]Outlook OAuth not configured. "
            f"Set OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET.[/{COLORS['tool']}]"
        )
        return None

    console.print(
        f"[{COLORS['primary']}]Initiating Outlook OAuth Authentication...[/{COLORS['primary']}]"
    )

    auth_url = get_auth_url()
    console.print(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    console.print(f"[{COLORS['dim']}]Waiting for callback...[/{COLORS['dim']}]")

    # Use shared OAuth server with timeout support
    code, _ = wait_for_callback(
        callback_path="/callback/outlook",
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
        "scope": " ".join(SCOPES),
    }

    response = requests.post(TOKEN_URL, data=payload)
    response.raise_for_status()
    token_data = response.json()

    # Add expiry timestamp for proactive refresh
    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)

    # Save token
    save_token(token_data)
    console.print(
        f"[{COLORS['primary']}]Successfully authenticated with Outlook![/{COLORS['primary']}]"
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
    """Clear stored Outlook credentials from keyring."""
    try:
        keyring.delete_password(SERVICE_NAME, TOKEN_KEY)
    except keyring.errors.PasswordDeleteError:
        pass  # Already cleared


def _is_token_expired(token_data: dict, buffer_seconds: int = TOKEN_EXPIRY_BUFFER) -> bool:
    """Check if the access token is expired or will expire soon."""
    expires_at = token_data.get("expires_at")
    if not expires_at:
        return False
    return time.time() >= (expires_at - buffer_seconds)


def _refresh_token(token_data: dict) -> dict | None:
    """Refresh the access token using the refresh token."""
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None

    try:
        payload = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
            "scope": " ".join(SCOPES),
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
    """Get a valid access token, refreshing if necessary."""
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            f"[{COLORS['tool']}]Outlook integration disabled: "
            f"OUTLOOK_CLIENT_ID/SECRET not found.[/{COLORS['tool']}]"
        )
        return None

    token_data = get_stored_token()

    if not token_data:
        console.print(
            f"[{COLORS['tool']}]No stored Outlook credentials found. "
            f"Initiating login...[/{COLORS['tool']}]"
        )
        token_data = login()
        if not token_data:
            return None

    # Proactive refresh if token is expired or about to expire
    if _is_token_expired(token_data):
        console.print(f"[{COLORS['dim']}]Outlook token expired, refreshing...[/{COLORS['dim']}]")
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
    """Get authorization headers for Microsoft Graph API requests."""
    token = get_access_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}
