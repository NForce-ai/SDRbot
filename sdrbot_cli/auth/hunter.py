"""Hunter.io Authentication Manager."""

import os

import keyring
import requests
from rich.prompt import Prompt

from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_hunter"
TOKEN_KEY = "api_key"


def is_configured() -> bool:
    """Check if Hunter is configured (Env or Keyring)."""
    if os.getenv("HUNTER_API_KEY"):
        return True
    if keyring.get_password(SERVICE_NAME, TOKEN_KEY):
        return True
    return False


def get_api_key() -> str | None:
    """Get Hunter API Key from Env, Keyring, or Prompt."""
    # 1. Check Environment
    api_key = os.getenv("HUNTER_API_KEY")
    if api_key:
        return api_key

    # 2. Check Keyring
    api_key = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    if api_key:
        return api_key

    # 3. Prompt User
    console.print(f"[{COLORS['tool']}]Hunter API Key not found.[/{COLORS['tool']}]")

    api_key = Prompt.ask("Enter your Hunter.io API Key", password=True)

    if api_key:
        keyring.set_password(SERVICE_NAME, TOKEN_KEY, api_key)
        return api_key

    return None


class HunterClient:
    """Simple wrapper for Hunter.io API."""

    def __init__(self):
        self.api_key = get_api_key()
        if not self.api_key:
            # Don't raise immediately, let the tool handle the error so agent can recover
            pass

        self.base_url = "https://api.hunter.io/v2"
        self.session = requests.Session()
        # Hunter uses query param 'api_key' for auth

    def request(self, method: str, endpoint: str, **kwargs):
        if not self.api_key:
            raise ValueError("Hunter API Key is missing. Please set HUNTER_API_KEY in .env")

        url = f"{self.base_url}{endpoint}"

        # Inject API key into params
        params = kwargs.get("params", {})
        params["api_key"] = self.api_key
        kwargs["params"] = params

        response = self.session.request(method, url, **kwargs)

        if not response.ok:
            try:
                error = response.json()
            except Exception:
                error = response.text
            raise Exception(f"Hunter API Error ({response.status_code}): {error}")

        return response.json()
