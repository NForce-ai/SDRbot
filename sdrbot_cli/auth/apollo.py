"""Apollo.io Authentication Manager.

Simple API key authentication for Apollo.io enrichment and prospecting.
"""

import os

import keyring
import requests
from rich.prompt import Prompt

from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_apollo"
TOKEN_KEY = "api_key"

API_BASE_URL = "https://api.apollo.io/api/v1"


def is_configured() -> bool:
    """Check if Apollo is configured (Env or Keyring)."""
    if os.getenv("APOLLO_API_KEY"):
        return True
    if keyring.get_password(SERVICE_NAME, TOKEN_KEY):
        return True
    return False


def get_api_key() -> str | None:
    """Get Apollo API Key from Env, Keyring, or Prompt."""
    # 1. Check Environment
    api_key = os.getenv("APOLLO_API_KEY")
    if api_key:
        return api_key

    # 2. Check Keyring
    api_key = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    if api_key:
        return api_key

    # 3. Prompt User
    console.print(f"[{COLORS['tool']}]Apollo API Key not found.[/{COLORS['tool']}]")

    api_key = Prompt.ask("Enter your Apollo API Key", password=True)

    if api_key:
        keyring.set_password(SERVICE_NAME, TOKEN_KEY, api_key)
        return api_key

    return None


class ApolloClient:
    """Simple wrapper for Apollo.io API."""

    def __init__(self):
        self.api_key = get_api_key()
        self.base_url = API_BASE_URL
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update(
                {
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                }
            )

    def request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an authenticated request to Apollo API.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint (e.g., "/people/match").
            **kwargs: Additional arguments for requests.

        Returns:
            JSON response as dict.

        Raises:
            ValueError: If API key is missing.
            Exception: If API returns an error.
        """
        if not self.api_key:
            raise ValueError("Apollo API Key is missing. Please set APOLLO_API_KEY in .env")

        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)

        if not response.ok:
            try:
                error = response.json()
            except Exception:
                error = response.text
            raise Exception(f"Apollo API Error ({response.status_code}): {error}")

        return response.json()

    def get(self, endpoint: str, **kwargs) -> dict:
        """Make a GET request."""
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> dict:
        """Make a POST request."""
        return self.request("POST", endpoint, **kwargs)
