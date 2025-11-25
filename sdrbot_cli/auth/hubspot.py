"""HubSpot Authentication Manager."""

import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
import webbrowser
import requests

import keyring
from hubspot import HubSpot

from sdrbot_cli.config import console, COLORS

SERVICE_NAME = "sdrbot_hubspot"
TOKEN_KEY = "oauth_token"

CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID")
CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback/hubspot"

# Scopes required for dynamic discovery and manipulation
# We request broad access to standard objects and schemas
SCOPES = [
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.companies.read",
    "crm.objects.companies.write",
    "crm.objects.deals.read",
    "crm.objects.deals.write",
    "crm.schemas.custom.read",
    # Add more as needed or make configurable
]


def is_configured() -> bool:
    """Check if HubSpot is configured (Env vars)."""
    # Check for PAT
    if os.getenv("HUBSPOT_ACCESS_TOKEN"):
        return True
    # Check for OAuth
    if CLIENT_ID and CLIENT_SECRET:
        return True
    return False


class OAuthHandler(BaseHTTPRequestHandler):
    """Handle the OAuth callback."""
    
    auth_code: Optional[str] = None

    def do_GET(self):
        """Handle the callback request."""
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/callback/hubspot":
            query_params = urllib.parse.parse_qs(parsed_path.query)
            if "code" in query_params:
                OAuthHandler.auth_code = query_params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Authorization Successful!</h1><p>You can close this window and return to the terminal.</p>")
            else:
                self.send_response(400)
                self.wfile.write(b"Authorization failed.")
        else:
            self.send_response(404)

    def log_message(self, format, *args):
        """Silence logs."""
        pass


def get_auth_url() -> str:
    """Generate the HubSpot OAuth URL."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    return f"https://app.hubspot.com/oauth/authorize?{urllib.parse.urlencode(params)}"


def login() -> Optional[dict]:
    """Perform the full OAuth login flow."""
    # CLIENT_ID and CLIENT_SECRET checks are now in get_client()

    console.print(f"[{COLORS['primary']}]Initiating HubSpot OAuth Authentication...[/{COLORS['primary']}]")
    
    auth_url = get_auth_url()
    console.print(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    # Start local server to catch callback
    server_address = ('', 8080)
    # Allow address reuse to avoid errors if restarting quickly
    HTTPServer.allow_reuse_address = True
    httpd = HTTPServer(server_address, OAuthHandler)
    
    console.print(f"[{COLORS['dim']}]Waiting for callback...[/{COLORS['dim']}]")
    # Reset code from any previous runs
    OAuthHandler.auth_code = None
    
    while OAuthHandler.auth_code is None:
        httpd.handle_request()

    code = OAuthHandler.auth_code
    console.print(f"[{COLORS['primary']}]Authorization code received! Exchanging for token...[/{COLORS['primary']}]")

    # Exchange code for token
    token_url = "https://api.hubapi.com/oauth/v1/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code
    }
    
    response = requests.post(token_url, data=payload)
    response.raise_for_status()
    token_data = response.json()
    
    # Save token
    save_token(token_data)
    console.print(f"[{COLORS['primary']}]Successfully authenticated with HubSpot via OAuth![/{COLORS['primary']}]")
    
    return token_data


def save_token(token_data: dict) -> None:
    """Save token data to keyring."""
    keyring.set_password(SERVICE_NAME, TOKEN_KEY, json.dumps(token_data))


def get_stored_token() -> Optional[dict]:
    """Retrieve token data from keyring."""
    data = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    if data:
        return json.loads(data)
    return None


def get_client() -> Optional[HubSpot]:
    
    # 1. Check for Personal Access Token (PAT)
    pat = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if pat:
        console.print(f"[{COLORS['primary']}]Using HubSpot Personal Access Token (PAT).[/]{COLORS['primary']}")
        return HubSpot(access_token=pat)

    # 2. Fallback to OAuth if Client ID/Secret are available
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print(
            f"[{COLORS['tool']}]HubSpot integration disabled: HUBSPOT_CLIENT_ID/SECRET not found and no HUBSPOT_ACCESS_TOKEN.",
            "Set HUBSPOT_CLIENT_ID/SECRET for OAuth or HUBSPOT_ACCESS_TOKEN for PAT.",
            f"[/{COLORS['tool']}]"
        )
        return None

    # Try to use stored OAuth token
    token_data = get_stored_token()
    
    if not token_data:
        console.print(f"[{COLORS['tool']}]No stored HubSpot OAuth credentials found. Initiating login...[/{COLORS['tool']}]")
        token_data = login()
        if not token_data: # login might return None if client_id/secret are missing
            return None

    client = HubSpot(access_token=token_data["access_token"])
    
    try:
        # Test connection by fetching a contact (limit 1) or some safe endpoint
        # The CRM Objects API is a good test.
        client.crm.contacts.basic_api.get_page(limit=1)
        return client
    except Exception as e:
        # Check if it's an auth error (401)
        is_auth_error = "401" in str(e) or "Unauthorized" in str(e)
        
        if is_auth_error:
            console.print(f"[{COLORS['dim']}]HubSpot session expired, attempting refresh...[/{COLORS['dim']}]")
            if "refresh_token" in token_data:
                 try:
                    token_url = "https://api.hubapi.com/oauth/v1/token"
                    payload = {
                        "grant_type": "refresh_token",
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "refresh_token": token_data["refresh_token"]
                    }
                    response = requests.post(token_url, data=payload)
                    response.raise_for_status()
                    new_token_data = response.json()
                    
                    token_data.update(new_token_data)
                    save_token(token_data)
                    
                    return HubSpot(access_token=token_data["access_token"])
                 except Exception as refresh_err:
                     console.print(f"[{COLORS['tool']}]Refresh failed: {refresh_err}. Re-authenticating.[/{COLORS['tool']}]")
        
        # Fallback to re-login if refresh failed or other error
        console.print(f"[{COLORS['tool']}]HubSpot client error: {e}. Attempting re-login.[/{COLORS['tool']}]")
        token_data = login()
        if token_data:
            return HubSpot(access_token=token_data["access_token"])
        return None
