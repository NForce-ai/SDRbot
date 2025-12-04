"""Main setup wizard screen for Textual TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, ListItem, ListView, Static

from sdrbot_cli.config import load_model_config
from sdrbot_cli.mcp.client import MCP_AVAILABLE
from sdrbot_cli.mcp.config import load_mcp_config
from sdrbot_cli.services.registry import load_config
from sdrbot_cli.setup.services import SERVICE_CATEGORIES
from sdrbot_cli.setup.tracing import TRACING_SERVICES

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


def get_model_status() -> tuple[str, str]:
    """Get status string and CSS class for models section."""
    config = load_model_config()
    if config and config.get("provider"):
        provider = config.get("provider", "unknown")
        model = config.get("model_name", "")
        if model:
            return (f"✓ {provider}: {model}", "status-active")
        return (f"✓ {provider}", "status-active")
    return ("• None enabled", "status-missing")


def get_services_status() -> tuple[str, str]:
    """Get status string and CSS class for services section."""
    config = load_config()
    enabled_count = 0

    # Only count services that are in SERVICE_CATEGORIES (not tracing services)
    for category in SERVICE_CATEGORIES.values():
        for service_code, _ in category["services"]:
            if config.is_enabled(service_code):
                enabled_count += 1

    if enabled_count > 0:
        return (f"✓ {enabled_count} enabled", "status-active")
    return ("• None enabled", "status-missing")


def get_mcp_status() -> tuple[str, str]:
    """Get status string and CSS class for MCP section."""
    if not MCP_AVAILABLE:
        return ("• SDK not installed", "status-missing")

    config = load_mcp_config()
    servers = config.get("servers", {})
    enabled_count = sum(1 for s in servers.values() if s.get("enabled", False))

    if enabled_count > 0:
        return (f"✓ {enabled_count} enabled", "status-active")
    elif servers:
        return (f"• {len(servers)} disabled", "status-configured")
    return ("• None enabled", "status-missing")


def get_tracing_status() -> tuple[str, str]:
    """Get status string and CSS class for tracing section."""
    config = load_config()
    enabled_count = 0

    for service_code, _ in TRACING_SERVICES:
        if config.is_enabled(service_code):
            enabled_count += 1

    if enabled_count > 0:
        return (f"✓ {enabled_count} enabled", "status-active")
    return ("• None enabled", "status-missing")


class SetupWizardScreen(Screen[bool | None]):
    """Main setup wizard screen with navigation to all setup sections."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    SetupWizardScreen {
        align: center middle;
    }

    #setup-container {
        width: 70;
    }

    #setup-list {
        max-height: 10;
    }

    #setup-error {
        text-align: center;
        height: auto;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def __init__(self, first_time: bool = False, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.first_time = first_time

    def compose(self) -> ComposeResult:
        with Container(id="setup-container", classes="setup-dialog-wide"):
            yield Static("Setup Wizard", classes="setup-title")
            yield Static(
                "Configure your LLM provider, services, and tools.",
                classes="setup-hint",
            )
            yield ListView(id="setup-list", classes="setup-list")
            esc_action = "Quit" if self.first_time else "Back"
            yield Static(f"↑↓ Navigate • Enter Select • Esc {esc_action}", classes="setup-hint")
            yield Static("", id="setup-error", classes="setup-error")
            with Horizontal(classes="setup-buttons"):
                yield Button("Done", variant="success", id="btn-done", classes="setup-btn")
                if self.first_time:
                    yield Button("Quit", variant="error", id="btn-quit", classes="setup-btn")
                else:
                    yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate the setup menu on mount."""
        self._refresh_menu()

    def _refresh_menu(self) -> None:
        """Refresh the menu with current status."""
        # Clear any previous error message
        self.query_one("#setup-error", Static).update("")

        list_view = self.query_one("#setup-list", ListView)
        list_view.clear()

        # Get status for each section (text, css_class)
        model_status = get_model_status()
        services_status = get_services_status()
        mcp_status = get_mcp_status()
        tracing_status = get_tracing_status()

        menu_items = [
            ("models", "Models", model_status),
            ("services", "Services", services_status),
            ("mcp", "MCP Servers", mcp_status),
            ("tracing", "Tracing", tracing_status),
        ]

        for item_id, label, (status_text, status_class) in menu_items:
            item = ListItem(
                Horizontal(
                    Static(label, classes="setup-list-item-label"),
                    Static(status_text, classes=f"setup-list-item-status {status_class}"),
                    classes="setup-list-item",
                ),
            )
            item.data = item_id
            list_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle menu item selection."""
        item_id = getattr(event.item, "data", None)

        if item_id == "models":
            from sdrbot_cli.tui.setup_screens import ModelsSetupScreen

            self.app.push_screen(ModelsSetupScreen(), self._on_section_complete)

        elif item_id == "services":
            from sdrbot_cli.tui.services_screens import ServicesSetupScreen

            self.app.push_screen(ServicesSetupScreen(), self._on_section_complete)

        elif item_id == "mcp":
            from sdrbot_cli.tui.mcp_screens import MCPSetupScreen

            self.app.push_screen(MCPSetupScreen(), self._on_section_complete)

        elif item_id == "tracing":
            from sdrbot_cli.tui.tracing_screens import TracingSetupScreen

            self.app.push_screen(TracingSetupScreen(), self._on_section_complete)

    def _on_section_complete(self, result: bool | None = None) -> None:
        """Called when a section screen is dismissed."""
        self._refresh_menu()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-done":
            self._finish_setup()
        elif event.button.id == "btn-back":
            self.dismiss(None)
        elif event.button.id == "btn-quit":
            self.app.exit()

    def _finish_setup(self) -> None:
        """Validate and finish setup."""
        error_label = self.query_one("#setup-error", Static)

        # Check that an LLM provider is configured
        config = load_model_config()
        if not config or not config.get("provider"):
            error_label.update(
                "[bold red]LLM provider required. Configure Models first.[/bold red]"
            )
            return

        error_label.update("")
        self.dismiss(True)

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        if self.first_time:
            # During first-time setup, Escape exits the app
            self.app.exit()
        else:
            self.dismiss(None)
