"""Twenty CRM Authentication Manager.

Twenty uses API key authentication with Bearer tokens.
Supports both cloud (api.twenty.com) and self-hosted instances.
"""

import os

import keyring
import requests
from rich.prompt import Prompt

from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_twenty"
TOKEN_KEY = "api_key"


def is_configured() -> bool:
    """Check if Twenty is configured (Env or Keyring)."""
    if os.getenv("TWENTY_API_KEY"):
        return True
    if keyring.get_password(SERVICE_NAME, TOKEN_KEY):
        return True
    return False


def get_api_key() -> str | None:
    """Get Twenty API Key from Env, Keyring, or Prompt.

    Returns:
        API key string or None if not available.
    """
    # 1. Check Environment
    api_key = os.getenv("TWENTY_API_KEY")
    if api_key:
        return api_key

    # 2. Check Keyring
    api_key = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    if api_key:
        return api_key

    # 3. Prompt User
    console.print(f"[{COLORS['tool']}]Twenty API Key not found.[/{COLORS['tool']}]")
    console.print(
        f"[{COLORS['dim']}]Create an API key at Settings > Developers > API Keys in your Twenty app[/{COLORS['dim']}]"
    )

    api_key = Prompt.ask("Enter your Twenty API Key", password=True)

    if api_key:
        keyring.set_password(SERVICE_NAME, TOKEN_KEY, api_key)
        return api_key

    return None


def get_base_url() -> str:
    """Get the Twenty API base URL.

    Returns:
        Base URL for the Twenty API (without trailing slash).
    """
    base_url = os.getenv("TWENTY_API_URL", "https://api.twenty.com")
    return base_url.rstrip("/")


def clear_credentials() -> None:
    """Clear stored Twenty credentials from keyring."""
    try:
        keyring.delete_password(SERVICE_NAME, TOKEN_KEY)
    except keyring.errors.PasswordDeleteError:
        pass  # Already deleted or never existed


class TwentyClient:
    """HTTP client for Twenty REST API.

    Provides a simple interface for making authenticated requests
    to Twenty's REST API.

    Example:
        client = TwentyClient()
        response = client.request("GET", "/people")
        people = response.get("data", [])
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        """Initialize Twenty client.

        Args:
            api_key: Optional API key (defaults to get_api_key()).
            base_url: Optional base URL (defaults to get_base_url()).
        """
        self.api_key = api_key or get_api_key()
        if not self.api_key:
            raise ValueError("Twenty API Key is required.")

        self.base_url = (base_url or get_base_url()).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def request(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> dict:
        """Make an authenticated request to the Twenty API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            endpoint: API endpoint path (e.g., "/people", "/companies/123").
            **kwargs: Additional arguments passed to requests (json, params, etc.).

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            Exception: If the API returns an error response.
        """
        # Ensure endpoint starts with /rest if not already
        if not endpoint.startswith("/rest"):
            endpoint = f"/rest{endpoint}"

        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)

        if not response.ok:
            try:
                error = response.json()
                error_msg = error.get("error", {}).get("message", str(error))
            except Exception:
                error_msg = response.text
            raise Exception(f"Twenty API Error ({response.status_code}): {error_msg}")

        # Handle empty responses (e.g., DELETE)
        if response.status_code == 204 or not response.text:
            return {}

        return response.json()

    def get(self, endpoint: str, **kwargs) -> dict:
        """Make a GET request."""
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> dict:
        """Make a POST request."""
        return self.request("POST", endpoint, **kwargs)

    def patch(self, endpoint: str, **kwargs) -> dict:
        """Make a PATCH request."""
        return self.request("PATCH", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> dict:
        """Make a DELETE request."""
        return self.request("DELETE", endpoint, **kwargs)
