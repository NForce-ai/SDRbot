"""Loading/initializing screen for Textual TUI."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import LoadingIndicator, Static


class LoadingScreen(ModalScreen[None]):
    """Modal screen showing loading/initialization progress."""

    CSS = """
    LoadingScreen {
        align: center middle;
    }

    #loading-container {
        width: 50;
        height: auto;
        border: heavy $accent;
        background: $panel;
        padding: 1 2;
    }

    #loading-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    #loading-indicator {
        width: 100%;
        height: 3;
    }

    #loading-message {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
        height: auto;
    }
    """

    def __init__(self, title: str = "Initializing", message: str = "") -> None:
        super().__init__()
        self.title_text = title
        self.message_text = message

    def compose(self) -> ComposeResult:
        with Container(id="loading-container"):
            yield Static(self.title_text, id="loading-title")
            yield LoadingIndicator(id="loading-indicator")
            yield Static(self.message_text, id="loading-message")

    def update_message(self, message: str) -> None:
        """Update the loading message."""
        self.query_one("#loading-message", Static).update(message)

    def update_title(self, title: str) -> None:
        """Update the loading title."""
        self.query_one("#loading-title", Static).update(title)
