"""Attio Authentication Manager."""

import os

import keyring
import requests
from rich.prompt import Prompt

from sdrbot_cli.config import COLORS, console

SERVICE_NAME = "sdrbot_attio"
TOKEN_KEY = "api_key"


def is_configured() -> bool:
    """Check if Attio is configured (Env or Keyring)."""
    if os.getenv("ATTIO_API_KEY"):
        return True
    if keyring.get_password(SERVICE_NAME, TOKEN_KEY):
        return True
    return False


def get_api_key() -> str | None:
    """Get Attio API Key from Env, Keyring, or Prompt."""
    # 1. Check Environment
    api_key = os.getenv("ATTIO_API_KEY")
    if api_key:
        return api_key

    # 2. Check Keyring
    api_key = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    if api_key:
        return api_key

    # 3. Prompt User
    console.print(f"[{COLORS['tool']}]Attio API Key not found.[/{COLORS['tool']}]")
    console.print(
        f"[{COLORS['dim']}]Please create a token at https://app.attio.com/settings/integrations/api-tokens[/{COLORS['dim']}]"
    )

    api_key = Prompt.ask("Enter your Attio API Key", password=True)

    if api_key:
        keyring.set_password(SERVICE_NAME, TOKEN_KEY, api_key)
        return api_key

    return None


class AttioClient:
    """Simple wrapper for Attio v2 API."""

    def __init__(self):
        self.api_key = get_api_key()
        if not self.api_key:
            raise ValueError("Attio API Key is required.")

        self.base_url = "https://api.attio.com/v2"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def request(self, method: str, endpoint: str, **kwargs):
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)

        if not response.ok:
            try:
                error = response.json()
            except Exception:
                error = response.text
            raise Exception(f"Attio API Error ({response.status_code}): {error}")

        return response.json()
