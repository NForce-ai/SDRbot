"""Help/User Guide modal screen for Textual TUI."""

import sys
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


class HelpScreen(ModalScreen[None]):
    """Modal screen displaying the user guide."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-container {
        width: 70;
        height: auto;
        max-height: 80%;
    }

    #help-content {
        height: 18;
        padding: 0 1;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }

    #help-hint {
        margin-top: 1;
    }

    .help-section-title {
        text-style: bold;
        color: $primary;
    }

    .help-item {
        padding-left: 2;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-container", classes="setup-dialog-wide"):
            yield Static("User Guide", classes="setup-title")

            with VerticalScroll(id="help-content"):
                # Commands section
                yield Static("Commands", classes="help-section-title")
                yield Static("  /setup      Configure models and services", classes="help-item")
                yield Static("  /agents     Manage agent profiles", classes="help-item")
                yield Static("  /skills     Manage agent skills", classes="help-item")
                yield Static("  /services   Manage CRM integrations", classes="help-item")
                yield Static("  /mcp        Manage MCP servers", classes="help-item")
                yield Static("  /tools      View all loaded tools", classes="help-item")
                yield Static("  /sync       Re-sync service schemas", classes="help-item")
                yield Static("  /tokens     View token usage stats", classes="help-item")
                yield Static("  /models     Configure LLM provider", classes="help-item")
                yield Static("  /tracing    Configure tracing", classes="help-item")
                yield Static("  /exit       Exit SDRbot", classes="help-item")
                yield Static("")

                # Keyboard shortcuts section
                yield Static("Keyboard Shortcuts", classes="help-section-title")
                if sys.platform == "darwin":
                    yield Static("  Enter         Submit message", classes="help-item")
                    yield Static("  ⌃+J          New line in input", classes="help-item")
                    yield Static("  ⌘+C          Copy", classes="help-item")
                    yield Static("  ⌘+V          Paste", classes="help-item")
                    yield Static("  ⌃+A          Toggle auto-approve", classes="help-item")
                    yield Static("  ⌃+S          Open setup menu", classes="help-item")
                    yield Static("  ⌃+T          Cycle tool scope", classes="help-item")
                    yield Static("  ⌃+C          Interrupt agent", classes="help-item")
                else:
                    yield Static("  Enter         Submit message", classes="help-item")
                    yield Static("  Ctrl+J        New line in input", classes="help-item")
                    yield Static("  Ctrl+Shift+C  Copy", classes="help-item")
                    yield Static("  Ctrl+Shift+V  Paste", classes="help-item")
                    yield Static("  Ctrl+A        Toggle auto-approve", classes="help-item")
                    yield Static("  Ctrl+S        Open setup menu", classes="help-item")
                    yield Static("  Ctrl+T        Cycle tool scope", classes="help-item")
                    yield Static("  Ctrl+C        Interrupt agent", classes="help-item")
                yield Static("")

                # Tool Scope section
                yield Static("Tool Scope", classes="help-section-title")
                yield Static(
                    "  Standard: Core CRM tools (contacts, companies, deals)",
                    classes="help-item",
                )
                yield Static(
                    "  Extended: Standard + custom objects and advanced tools",
                    classes="help-item",
                )
                yield Static(
                    "  Privileged: All tools including admin/schema management",
                    classes="help-item",
                )
                yield Static(
                    "  Cycle with Ctrl+T. Current scope shown in header.",
                    classes="help-item",
                )
                yield Static("")

                # Auto-approve section
                yield Static("Auto-approve Mode", classes="help-section-title")
                yield Static(
                    "  When enabled, tools run without confirmation.",
                    classes="help-item",
                )
                yield Static(
                    "  Toggle with Ctrl+A or start with --auto-approve",
                    classes="help-item",
                )

            yield Static("↑↓ Scroll • Esc Close", id="help-hint", classes="setup-hint")
            with Container(classes="setup-buttons"):
                yield Button("Close", variant="default", id="btn-close", classes="setup-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-close":
            self.dismiss(None)

    def action_close(self) -> None:
        """Close the help screen."""
        self.dismiss(None)
