"""Lusha Authentication Manager."""

import os
from typing import Optional
import requests
import keyring
from rich.prompt import Prompt

from sdrbot_cli.config import console, COLORS

SERVICE_NAME = "sdrbot_lusha"
TOKEN_KEY = "api_key"

def get_api_key() -> Optional[str]:
    """Get Lusha API Key from Env, Keyring, or Prompt."""
    # 1. Check Environment
    api_key = os.getenv("LUSHA_API_KEY")
    if api_key:
        return api_key
        
    # 2. Check Keyring
    api_key = keyring.get_password(SERVICE_NAME, TOKEN_KEY)
    if api_key:
        return api_key
        
    # 3. Prompt User
    console.print(f"[{COLORS['tool']}]Lusha API Key not found.[/{COLORS['tool']}]")
    
    api_key = Prompt.ask("Enter your Lusha API Key", password=True)
    
    if api_key:
        keyring.set_password(SERVICE_NAME, TOKEN_KEY, api_key)
        return api_key
        
    return None

class LushaClient:
    """Simple wrapper for Lusha API."""
    
    def __init__(self):
        self.api_key = get_api_key()
        if not self.api_key:
            # Don't raise immediately, let the tool handle the error so agent can recover
            pass
            
        self.base_url = "https://api.lusha.com"
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({
                "api_key": self.api_key,
                "Content-Type": "application/json"
            })

    def request(self, method: str, endpoint: str, **kwargs):
        if not self.api_key:
             raise ValueError("Lusha API Key is missing. Please set LUSHA_API_KEY in .env")

        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        
        if not response.ok:
            try:
                error = response.json()
            except:
                error = response.text
            raise Exception(f"Lusha API Error ({response.status_code}): {error}")
            
        return response.json()
