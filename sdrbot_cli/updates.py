import os
import sys

import requests
from packaging.version import parse as parse_version
from rich.console import Console

from sdrbot_cli.version import __version__

console = Console()

GITHUB_REPO = "NForce-ai/SDRbot"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_for_updates() -> tuple[str, str] | tuple[None, None]:
    """Check for updates on GitHub.

    Returns:
        Tuple of (latest_version, release_url) or (None, None) if no update or error.
    """
    # Test mode: set SDRBOT_TEST_UPDATE=1.0.0 to fake an available update
    test_version = os.environ.get("SDRBOT_TEST_UPDATE")
    if test_version:
        return test_version, f"https://github.com/{GITHUB_REPO}/releases/tag/v{test_version}"

    try:
        response = requests.get(LATEST_RELEASE_URL, timeout=2)
        if response.status_code == 200:
            data = response.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            if latest_tag and parse_version(latest_tag) > parse_version(__version__):
                return latest_tag, data.get("html_url")
    except Exception:
        # Fail silently on network errors or parsing issues
        pass
    return None, None


def print_update_banner_if_needed():
    """Check for updates and print banner if available."""
    # Run in a separate thread to not block CLI startup if possible,
    # but since we want to print it at a specific time (startup),
    # we might just want to wait briefly or handle it async.
    # For simplicity in this CLI, we'll do a synchronous check with short timeout.

    latest_version, release_url = check_for_updates()
    if latest_version:
        console.print()
        console.print(
            f"[bold yellow]🚀 Update available: v{latest_version}[/bold yellow] (Current: v{__version__})"
        )

        # Detect if running as binary (PyInstaller)
        if getattr(sys, "frozen", False):
            console.print(f"[dim]Download the new binary from: {release_url}[/dim]")
        else:
            console.print("[dim]Run 'git pull' to update source.[/dim]")
        console.print()
