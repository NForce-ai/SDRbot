"""Zoho CRM Authentication Manager."""

import json
import os
import time
import urllib.parse
import webbrowser

import keyring
import requests

from sdrbot_cli.auth.oauth_server import wait_for_callback
from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_zohocrm"
TOKEN_KEY = "oauth_token"

# Region-specific endpoints
ZOHO_REGIONS = {
    "us": {"accounts": "accounts.zoho.com", "api": "www.zohoapis.com"},
    "eu": {"accounts": "accounts.zoho.eu", "api": "www.zohoapis.eu"},
    "in": {"accounts": "accounts.zoho.in", "api": "www.zohoapis.in"},
    "au": {"accounts": "accounts.zoho.com.au", "api": "www.zohoapis.com.au"},
    "cn": {"accounts": "accounts.zoho.com.cn", "api": "www.zohoapis.com.cn"},
    "jp": {"accounts": "accounts.zoho.jp", "api": "www.zohoapis.jp"},
}

CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
REGION = os.getenv("ZOHO_REGION", "").lower()
REDIRECT_URI = "http://localhost:8080/callback/zohocrm"

# Scopes required for CRM operations and schema discovery
SCOPES = [
    "ZohoCRM.modules.ALL",
    "ZohoCRM.settings.ALL",
    "ZohoCRM.settings.fields.ALL",
    "ZohoCRM.settings.modules.ALL",
    "ZohoCRM.users.READ",
    "ZohoCRM.coql.READ",
    "ZohoSearch.securesearch.READ",  # Required for /actions/count endpoint
]

# Buffer time (in seconds) before token expiry to trigger proactive refresh
TOKEN_EXPIRY_BUFFER = 300  # 5 minutes


def is_configured() -> bool:
    """Check if Zoho CRM is configured (env vars)."""
    return bool(CLIENT_ID and CLIENT_SECRET and REGION)


def _get_region_config() -> dict | None:
    """Get the region configuration based on ZOHO_REGION env var."""
    if not REGION:
        return None
    return ZOHO_REGIONS.get(REGION)


def get_auth_url() -> str:
    """Generate the Zoho OAuth URL."""
    region_config = _get_region_config()
    if not region_config:
        raise ValueError(
            f"Invalid ZOHO_REGION: {REGION}. Must be one of: {', '.join(ZOHO_REGIONS.keys())}"
        )

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": ",".join(SCOPES),
        "redirect_uri": REDIRECT_URI,
        "access_type": "offline",
        "prompt": "consent",
    }
    accounts_url = f"https://{region_config['accounts']}/oauth/v2/auth"
    return f"{accounts_url}?{urllib.parse.urlencode(params)}"


def login() -> dict | None:
    """Perform the full OAuth login flow."""
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET environment variables must be set.")

    region_config = _get_region_config()
    if not region_config:
        raise ValueError(f"ZOHO_REGION must be set to one of: {', '.join(ZOHO_REGIONS.keys())}")

    console.print(
        f"[{COLORS['primary']}]Initiating Zoho CRM Authentication...[/{COLORS['primary']}]"
    )

    auth_url = get_auth_url()
    console.print(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    console.print(f"[{COLORS['dim']}]Waiting for callback...[/{COLORS['dim']}]")

    # Use shared OAuth server with timeout support
    code, extra_params = wait_for_callback(
        callback_path="/callback/zohocrm",
        port=8080,
        timeout=300.0,
    )

    if not code:
        console.print(
            f"[{COLORS['tool']}]OAuth flow timed out or was cancelled.[/{COLORS['tool']}]"
        )
        return None

    # Use accounts server from callback, or fall back to region config
    accounts_server = extra_params.get("accounts-server") or f"https://{region_config['accounts']}"
    if not accounts_server.startswith("https://"):
        accounts_server = f"https://{accounts_server}"

    console.print(
        f"[{COLORS['primary']}]Authorization code received! Exchanging for token...[/{COLORS['primary']}]"
    )

    # Exchange code for token
    token_url = f"{accounts_server}/oauth/v2/token"
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

    if "error" in token_data:
        raise ValueError(f"Token exchange failed: {token_data.get('error')}")

    # Add metadata for future use
    token_data["accounts_server"] = accounts_server
    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)

    # Save token
    save_token(token_data)
    console.print(
        f"[{COLORS['primary']}]Successfully authenticated with Zoho CRM![/{COLORS['primary']}]"
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
        # No expiry info, assume it might be expired
        return True
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

    accounts_server = token_data.get("accounts_server")
    if not accounts_server:
        region_config = _get_region_config()
        if not region_config:
            return None
        accounts_server = f"https://{region_config['accounts']}"

    try:
        token_url = f"{accounts_server}/oauth/v2/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token,
        }
        response = requests.post(token_url, data=payload)
        response.raise_for_status()
        new_token_data = response.json()

        if "error" in new_token_data:
            return None

        # Merge new data (refresh token may not be returned on refresh)
        token_data.update(new_token_data)
        token_data["expires_at"] = int(time.time()) + new_token_data.get("expires_in", 3600)
        save_token(token_data)

        return token_data
    except Exception as e:
        console.print(f"[{COLORS['tool']}]Token refresh failed: {e}[/{COLORS['tool']}]")
        return None


def get_client() -> dict | None:
    """Get authenticated Zoho CRM client configuration.

    Unlike HubSpot/Salesforce which return SDK clients, this returns
    a dict with api_domain and access_token for making REST calls.

    Returns:
        Dict with 'api_domain' and 'access_token', or None if auth fails.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            f"[{COLORS['tool']}]Zoho CRM integration disabled: ZOHO_CLIENT_ID/SECRET not found.[/{COLORS['tool']}]"
        )
        return None

    if not REGION or REGION not in ZOHO_REGIONS:
        console.print(
            f"[{COLORS['tool']}]Zoho CRM integration disabled: ZOHO_REGION must be set to one of: {', '.join(ZOHO_REGIONS.keys())}[/{COLORS['tool']}]"
        )
        return None

    token_data = get_stored_token()

    # No stored token - need to login
    if not token_data:
        console.print(
            f"[{COLORS['tool']}]No stored Zoho CRM credentials found. Initiating login...[/{COLORS['tool']}]"
        )
        token_data = login()
        if not token_data:
            return None

    # Proactive refresh if token is expired or about to expire
    if _is_token_expired(token_data):
        console.print(f"[{COLORS['dim']}]Zoho CRM token expired, refreshing...[/{COLORS['dim']}]")
        token_data = _refresh_token(token_data)
        if not token_data:
            console.print(
                f"[{COLORS['tool']}]Token refresh failed. Re-authenticating...[/{COLORS['tool']}]"
            )
            token_data = login()
            if not token_data:
                return None

    # Return client config for REST calls
    api_domain = token_data.get("api_domain")
    if not api_domain:
        # Fall back to region-based API domain
        region_config = _get_region_config()
        api_domain = f"https://{region_config['api']}"

    return {
        "api_domain": api_domain,
        "access_token": token_data["access_token"],
    }


class ZohoClient:
    """Simple REST client for Zoho CRM API."""

    def __init__(self, api_domain: str, access_token: str):
        self.api_domain = api_domain.rstrip("/")
        self.access_token = access_token
        self.base_url = f"{self.api_domain}/crm/v7"

    def _headers(self) -> dict:
        return {"Authorization": f"Zoho-oauthtoken {self.access_token}"}

    def request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an authenticated request to the Zoho CRM API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            endpoint: API endpoint (e.g., "/Leads" or "/settings/modules").
            **kwargs: Additional arguments passed to requests.

        Returns:
            JSON response as dict.

        Raises:
            requests.HTTPError: If the request fails.
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json() if response.text else {}

    def get(self, endpoint: str, **kwargs) -> dict:
        """Make a GET request."""
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> dict:
        """Make a POST request."""
        return self.request("POST", endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs) -> dict:
        """Make a PUT request."""
        return self.request("PUT", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> dict:
        """Make a DELETE request."""
        return self.request("DELETE", endpoint, **kwargs)


def get_zoho_client() -> ZohoClient | None:
    """Get an authenticated ZohoClient instance.

    Returns:
        ZohoClient instance, or None if authentication fails.
    """
    client_config = get_client()
    if not client_config:
        return None
    return ZohoClient(client_config["api_domain"], client_config["access_token"])
