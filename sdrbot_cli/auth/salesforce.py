"""Salesforce Authentication Manager."""

import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
import webbrowser

import keyring
from simple_salesforce import Salesforce

from sdrbot_cli.config import console, COLORS

SERVICE_NAME = "sdrbot_salesforce"
TOKEN_KEY = "oauth_token"

# Default to standard Salesforce login, can be overridden for sandboxes
SF_LOGIN_URL = os.getenv("SF_LOGIN_URL", "https://login.salesforce.com")
CLIENT_ID = os.getenv("SF_CLIENT_ID")
CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback/salesforce"


def is_configured() -> bool:
    """Check if Salesforce is configured (Env vars)."""
    return bool(CLIENT_ID and CLIENT_SECRET)


class OAuthHandler(BaseHTTPRequestHandler):
    """Handle the OAuth callback."""
    
    auth_code: Optional[str] = None

    def do_GET(self):
        """Handle the callback request."""
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/callback/salesforce":
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
    """Generate the Salesforce OAuth URL."""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "prompt": "login consent",
    }
    return f"{SF_LOGIN_URL}/services/oauth2/authorize?{urllib.parse.urlencode(params)}"


def login() -> dict:
    """Perform the full OAuth login flow."""
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("SF_CLIENT_ID and SF_CLIENT_SECRET environment variables must be set.")

    console.print(f"[{COLORS['primary']}]Initiating Salesforce Authentication...[/{COLORS['primary']}]")
    
    auth_url = get_auth_url()
    console.print(f"Opening browser to: {auth_url}")
    webbrowser.open(auth_url)

    # Start local server to catch callback
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, OAuthHandler)
    
    console.print(f"[{COLORS['dim']}]Waiting for callback...[/{COLORS['dim']}]")
    while OAuthHandler.auth_code is None:
        httpd.handle_request()

    code = OAuthHandler.auth_code
    console.print(f"[{COLORS['primary']}]Authorization code received! Exchanging for token...[/{COLORS['primary']}]")

    # Exchange code for token - utilizing simple_salesforce internal method or manual request?
    # Manual request is safer to control the exact flow
    import requests
    token_url = f"{SF_LOGIN_URL}/services/oauth2/token"
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
    console.print(f"[{COLORS['primary']}]Successfully authenticated with Salesforce![/{COLORS['primary']}]")
    
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


def get_client() -> Salesforce:
    """Get an authenticated Salesforce client, handling refresh if needed."""
    token_data = get_stored_token()
    
    if not token_data:
        console.print(f"[{COLORS['tool']}]No stored Salesforce credentials found. Login required.[/{COLORS['tool']}]")
        token_data = login()

    try:
        # Attempt to create client with existing token
        sf = Salesforce(
            instance_url=token_data["instance_url"],
            session_id=token_data["access_token"]
        )
        # Test connection
        sf.query("SELECT Id FROM User LIMIT 1")
        return sf
    except Exception:
        console.print(f"[{COLORS['dim']}]Session expired, attempting refresh...[/{COLORS['dim']}]")
        # If that fails, try to refresh
        if "refresh_token" in token_data:
             try:
                import requests
                token_url = f"{SF_LOGIN_URL}/services/oauth2/token"
                payload = {
                    "grant_type": "refresh_token",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "refresh_token": token_data["refresh_token"]
                }
                response = requests.post(token_url, data=payload)
                response.raise_for_status()
                new_token_data = response.json()
                
                # Merge new data (some endpoints don't return refresh token on refresh)
                token_data.update(new_token_data)
                save_token(token_data)
                
                return Salesforce(
                    instance_url=token_data["instance_url"],
                    session_id=token_data["access_token"]
                )
             except Exception as e:
                 console.print(f"[{COLORS['tool']}]Refresh failed: {e}. Re-authenticating.[/{COLORS['tool']}]")
                 
        # If no refresh token or refresh failed, full login
        token_data = login()
        return Salesforce(
            instance_url=token_data["instance_url"],
            session_id=token_data["access_token"]
        )
