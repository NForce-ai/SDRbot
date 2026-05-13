"""Google Drive Authentication Manager using OAuth 2.0."""

import json
import os
import time
import urllib.parse
import webbrowser

import keyring
import requests

from sdrbot_cli.auth.oauth_server import wait_for_callback
from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_google_drive"
TOKEN_KEY = "oauth_token"

CLIENT_ID = os.getenv("GOOGLE_DRIVE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback/google_drive"

# Google OAuth endpoints
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Google Drive API scopes
# https://developers.google.com/drive/api/guides/api-specific-auth
SCOPES = [
    "https://www.googleapis.com/auth/drive",  # Full access to Google Drive
]

# Buffer time (in seconds) before token expiry to trigger proactive refresh
TOKEN_EXPIRY_BUFFER = 300  # 5 minutes


def is_configured() -> bool:
    """Check if Google Drive OAuth credentials are configured."""
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
            f"[{COLORS['tool']}]Google Drive OAuth not configured. "
            f"Set GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET.[/{COLORS['tool']}]"
        )
        return None

    console.print(
        f"[{COLORS['primary']}]Initiating Google Drive OAuth Authentication...[/{COLORS['primary']}]"
    )

    auth_url = get_auth_url()
    console.print(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    console.print(f"[{COLORS['dim']}]Waiting for callback...[/{COLORS['dim']}]")

    code, _ = wait_for_callback(
        callback_path="/callback/google_drive",
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

    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)

    save_token(token_data)
    console.print(
        f"[{COLORS['primary']}]Successfully authenticated with Google Drive![/{COLORS['primary']}]"
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
    """Clear stored Google Drive credentials from keyring."""
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
        }
        response = requests.post(TOKEN_URL, data=payload)
        response.raise_for_status()
        new_token_data = response.json()

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
            f"[{COLORS['tool']}]Google Drive integration disabled: "
            f"GOOGLE_DRIVE_CLIENT_ID/SECRET not found.[/{COLORS['tool']}]"
        )
        return None

    token_data = get_stored_token()

    if not token_data:
        console.print(
            f"[{COLORS['tool']}]No stored Google Drive credentials found. "
            f"Initiating login...[/{COLORS['tool']}]"
        )
        token_data = login()
        if not token_data:
            return None

    if _is_token_expired(token_data):
        console.print(
            f"[{COLORS['dim']}]Google Drive token expired, refreshing...[/{COLORS['dim']}]"
        )
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
    """Get authorization headers for Google Drive API requests."""
    token = get_access_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}
