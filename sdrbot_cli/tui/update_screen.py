"""Update notification modal screen."""

import sys
import webbrowser
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from sdrbot_cli.version import __version__

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


class UpdateModal(ModalScreen[None]):
    """Modal screen showing update instructions."""

    CSS_PATH = "setup_common.tcss"

    CSS = """
    UpdateModal {
        align: center middle;
    }

    #update-dialog {
        width: 60;
        height: auto;
        max-height: 20;
        background: $panel;
        border: heavy $accent;
        padding: 1 2;
    }

    #update-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    #update-versions {
        padding: 1 0;
    }

    #update-instructions {
        padding: 1 0;
    }

    #update-url {
        text-align: center;
        padding: 1 0;
        link-color: $accent;
        link-style: underline;
    }

    #update-buttons {
        align: center middle;
        padding-top: 1;
    }

    #update-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
    ]

    def __init__(self, latest_version: str, release_url: str) -> None:
        super().__init__()
        self.latest_version = latest_version
        self.release_url = release_url

    def compose(self) -> ComposeResult:
        with Container(id="update-dialog"):
            yield Static(f"🚀 Update Available: v{self.latest_version}", id="update-title")

            with Vertical(id="update-versions"):
                yield Static(f"[dim]Current version:[/] v{__version__}")
                yield Static(f"[dim]Latest version:[/]  v{self.latest_version}")

            # Show different instructions based on how the app is running
            if getattr(sys, "frozen", False):
                # Running as PyInstaller binary
                yield Static(
                    f"[@click=open_url]{self.release_url}[/]",
                    id="update-url",
                )
                yield Static(
                    "[dim]Download the latest binary for your platform.[/]",
                    id="update-instructions",
                )
            else:
                # Running from source
                yield Static(
                    "[dim]To update, run:[/]\n\n  [bold cyan]git pull[/]",
                    id="update-instructions",
                )

            with Container(id="update-buttons"):
                if getattr(sys, "frozen", False):
                    yield Button("Open Download Page", variant="primary", id="open-url")
                yield Button("Close", variant="success", id="close")

    def action_open_url(self) -> None:
        """Open the release URL in browser."""
        webbrowser.open(self.release_url)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "open-url":
            self.action_open_url()
        elif event.button.id == "close":
            self.dismiss()

    def action_close(self) -> None:
        """Close the modal."""
        self.dismiss()
