"""HubSpot Authentication Manager."""

import json
import os
import time
import urllib.parse
import webbrowser

import keyring
import requests
from hubspot import HubSpot

from sdrbot_cli.auth.oauth_server import wait_for_callback
from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_hubspot"
TOKEN_KEY = "oauth_token"

CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID")
CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback/hubspot"

# Scopes required for dynamic discovery and manipulation
# We request broad access to standard objects and schemas
SCOPES = [
    # Core CRM objects
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.companies.read",
    "crm.objects.companies.write",
    "crm.objects.deals.read",
    "crm.objects.deals.write",
    # Additional objects
    "tickets",  # For tickets read/write
    "e-commerce",  # For line_items, products, quotes
    # Schema and configuration
    "crm.schemas.contacts.read",
    "crm.schemas.companies.read",
    "crm.schemas.deals.read",
    "crm.schemas.custom.read",
]

# Buffer time (in seconds) before token expiry to trigger proactive refresh
TOKEN_EXPIRY_BUFFER = 300  # 5 minutes


def is_configured() -> bool:
    """Check if HubSpot is configured (Env vars)."""
    # Check for PAT
    if os.getenv("HUBSPOT_ACCESS_TOKEN"):
        return True
    # Check for OAuth
    if CLIENT_ID and CLIENT_SECRET:
        return True
    return False


def get_auth_url() -> str:
    """Generate the HubSpot OAuth URL."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    return f"https://app.hubspot.com/oauth/authorize?{urllib.parse.urlencode(params)}"


def login() -> dict | None:
    """Perform the full OAuth login flow."""
    # CLIENT_ID and CLIENT_SECRET checks are now in get_client()

    console.print(
        f"[{COLORS['primary']}]Initiating HubSpot OAuth Authentication...[/{COLORS['primary']}]"
    )

    auth_url = get_auth_url()
    console.print(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    console.print(f"[{COLORS['dim']}]Waiting for callback...[/{COLORS['dim']}]")

    # Use shared OAuth server with timeout support
    code, _ = wait_for_callback(
        callback_path="/callback/hubspot",
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
    token_url = "https://api.hubapi.com/oauth/v1/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }

    response = requests.post(token_url, data=payload)
    response.raise_for_status()
    token_data = response.json()

    # Add expiry timestamp for proactive refresh
    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)

    # Save token
    save_token(token_data)
    console.print(
        f"[{COLORS['primary']}]Successfully authenticated with HubSpot via OAuth![/{COLORS['primary']}]"
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
        token_url = "https://api.hubapi.com/oauth/v1/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        }
        response = requests.post(token_url, data=payload)
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


def get_client() -> HubSpot | None:
    # 1. Check for Personal Access Token (PAT)
    pat = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if pat:
        console.print(
            f"[{COLORS['primary']}]Using HubSpot Personal Access Token (PAT).[/{COLORS['primary']}]"
        )
        return HubSpot(access_token=pat)

    # 2. Fallback to OAuth if Client ID/Secret are available
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            f"[{COLORS['tool']}]HubSpot integration disabled: HUBSPOT_CLIENT_ID/SECRET not found and no HUBSPOT_ACCESS_TOKEN.",
            "Set HUBSPOT_CLIENT_ID/SECRET for OAuth or HUBSPOT_ACCESS_TOKEN for PAT.",
            f"[/{COLORS['tool']}]",
        )
        return None

    # Try to use stored OAuth token
    token_data = get_stored_token()

    if not token_data:
        console.print(
            f"[{COLORS['tool']}]No stored HubSpot OAuth credentials found. Initiating login...[/{COLORS['tool']}]"
        )
        token_data = login()
        if not token_data:  # login might return None if client_id/secret are missing
            return None

    # Proactive refresh if token is expired or about to expire
    if _is_token_expired(token_data):
        console.print(f"[{COLORS['dim']}]HubSpot token expired, refreshing...[/{COLORS['dim']}]")
        token_data = _refresh_token(token_data)
        if not token_data:
            console.print(
                f"[{COLORS['tool']}]Token refresh failed. Re-authenticating...[/{COLORS['tool']}]"
            )
            token_data = login()
            if not token_data:
                return None

    client = HubSpot(access_token=token_data["access_token"])

    try:
        # Test connection by fetching a contact (limit 1) or some safe endpoint
        # The CRM Objects API is a good test.
        client.crm.contacts.basic_api.get_page(limit=1)
        return client
    except Exception as e:
        # Check if it's an auth error (401) - fallback for edge cases
        is_auth_error = "401" in str(e) or "Unauthorized" in str(e)

        if is_auth_error:
            console.print(
                f"[{COLORS['dim']}]HubSpot session invalid, attempting refresh...[/{COLORS['dim']}]"
            )
            token_data = _refresh_token(token_data) if token_data else None
            if token_data:
                return HubSpot(access_token=token_data["access_token"])

            # Refresh failed, re-login
            console.print(
                f"[{COLORS['tool']}]Refresh failed. Re-authenticating...[/{COLORS['tool']}]"
            )
            token_data = login()
            if token_data:
                return HubSpot(access_token=token_data["access_token"])
            return None

        # Non-auth error, re-raise
        console.print(f"[{COLORS['tool']}]HubSpot client error: {e}[/{COLORS['tool']}]")
        return None
