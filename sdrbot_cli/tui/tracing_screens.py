"""Tracing setup screens for Textual TUI."""

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from sdrbot_cli.services import disable_service, enable_service
from sdrbot_cli.services.registry import load_config
from sdrbot_cli.setup.env import reload_env_and_settings, save_env_vars
from sdrbot_cli.setup.tracing import TRACING_SERVICES

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


def get_tracing_service_status(service_name: str) -> tuple[bool, bool]:
    """
    Check tracing service status.

    Returns:
        (is_configured, is_enabled)
    """
    configured = False
    if service_name == "langsmith":
        configured = bool(os.getenv("LANGSMITH_API_KEY"))
    elif service_name == "langfuse":
        configured = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
    elif service_name == "opik":
        configured = bool(os.getenv("OPIK_API_KEY"))

    # Check enabled state from registry
    try:
        config = load_config()
        enabled = config.is_enabled(service_name)
    except Exception:
        enabled = False

    return configured, enabled


class TracingSetupScreen(Screen[bool | None]):
    """Screen for managing tracing services."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    TracingSetupScreen {
        align: center middle;
    }

    #tracing-container {
        width: 70;
    }

    #tracing-list {
        max-height: 8;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="tracing-container", classes="setup-dialog-wide"):
            yield Static("Tracing", classes="setup-title")
            yield Static(
                "Configure tracing and monitoring integrations.",
                classes="setup-hint",
            )
            yield ListView(id="tracing-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate the service list on mount."""
        self._refresh_service_list()

    def _refresh_service_list(self) -> None:
        """Refresh the service list with current status."""
        list_view = self.query_one("#tracing-list", ListView)
        list_view.clear()

        for service_code, service_label in TRACING_SERVICES:
            configured, enabled = get_tracing_service_status(service_code)

            if configured:
                if enabled:
                    status_text = "● Enabled"
                    status_class = "status-active"
                else:
                    status_text = "Disabled"
                    status_class = "status-configured"
            else:
                status_text = "Not configured"
                status_class = "status-missing"

            item = ListItem(
                Horizontal(
                    Static(service_label, classes="setup-list-item-label"),
                    Static(status_text, classes=f"setup-list-item-status {status_class}"),
                    classes="setup-list-item",
                ),
            )
            item.data = service_code
            list_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle service selection."""
        service_code = getattr(event.item, "data", None)
        if service_code:
            configured, _ = get_tracing_service_status(service_code)

            if configured:
                # Show manage screen
                self.app.push_screen(
                    ManageTracingScreen(service_code),
                    self._on_action_complete,
                )
            else:
                # Go directly to config screen
                self.app.push_screen(
                    ConfigureTracingScreen(service_code),
                    self._on_action_complete,
                )

    def _on_action_complete(self, result: bool | None) -> None:
        """Called when a sub-screen is dismissed."""
        self._refresh_service_list()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(None)

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.dismiss(None)


class ManageTracingScreen(ModalScreen[bool]):
    """Modal screen for managing an already-configured tracing service."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ManageTracingScreen {
        align: center middle;
    }

    #manage-list {
        max-height: 6;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, service_code: str) -> None:
        super().__init__()
        self.service_code = service_code
        self.service_label = next(
            (label for code, label in TRACING_SERVICES if code == service_code),
            service_code.capitalize(),
        )

    def compose(self) -> ComposeResult:
        with Container(id="manage-dialog", classes="setup-dialog"):
            yield Static(f"Manage {self.service_label}", classes="setup-title")
            yield ListView(id="manage-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate actions list."""
        list_view = self.query_one("#manage-list", ListView)

        _, enabled = get_tracing_service_status(self.service_code)

        if enabled:
            disable_item = ListItem(Static("Disable"))
            disable_item.data = "disable"
            list_view.append(disable_item)
        else:
            enable_item = ListItem(Static("Enable"))
            enable_item.data = "enable"
            list_view.append(enable_item)

        reconfig_item = ListItem(Static("Reconfigure"))
        reconfig_item.data = "reconfigure"
        list_view.append(reconfig_item)

        list_view.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle action selection."""
        action = getattr(event.item, "data", None)

        if action == "enable":
            enable_service(self.service_code, verbose=False)
            self.notify(f"Enabled {self.service_label}", severity="information")
            self.dismiss(True)
        elif action == "disable":
            disable_service(self.service_code, verbose=False)
            self.notify(f"Disabled {self.service_label}", severity="warning")
            self.dismiss(True)
        elif action == "reconfigure":
            self.app.push_screen(
                ConfigureTracingScreen(self.service_code),
                self._on_config_complete,
            )

    def _on_config_complete(self, result: bool) -> None:
        """Called when config screen completes."""
        if result:
            self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class ConfigureTracingScreen(ModalScreen[bool]):
    """Modal screen for configuring a tracing service."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ConfigureTracingScreen {
        align: center middle;
    }

    #config-dialog {
        width: 70;
        height: auto;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, service_code: str) -> None:
        super().__init__()
        self.service_code = service_code
        self.service_label = next(
            (label for code, label in TRACING_SERVICES if code == service_code),
            service_code.capitalize(),
        )

    def compose(self) -> ComposeResult:
        with Container(id="config-dialog", classes="setup-dialog-wide"):
            yield Static(f"Configure {self.service_label}", classes="setup-title")

            if self.service_code == "langsmith":
                with Vertical(classes="setup-field"):
                    yield Label("LangSmith API Key:", classes="setup-field-label")
                    yield Input(
                        placeholder="lsv2_pt_...",
                        password=True,
                        id="langsmith-api-key",
                        classes="setup-field-input",
                    )

            elif self.service_code == "langfuse":
                with Vertical(classes="setup-field"):
                    yield Label("Langfuse Public Key:", classes="setup-field-label")
                    yield Input(
                        placeholder="pk-...",
                        id="langfuse-public-key",
                        classes="setup-field-input",
                    )

                with Vertical(classes="setup-field"):
                    yield Label("Langfuse Secret Key:", classes="setup-field-label")
                    yield Input(
                        placeholder="sk-...",
                        password=True,
                        id="langfuse-secret-key",
                        classes="setup-field-input",
                    )

                with Vertical(classes="setup-field"):
                    yield Label(
                        "Langfuse Host (optional, for self-hosted):", classes="setup-field-label"
                    )
                    yield Input(
                        placeholder="https://cloud.langfuse.com",
                        id="langfuse-host",
                        classes="setup-field-input",
                    )

            elif self.service_code == "opik":
                with Vertical(classes="setup-field"):
                    yield Label("Opik API Key:", classes="setup-field-label")
                    yield Input(
                        placeholder="Your Opik API key",
                        password=True,
                        id="opik-api-key",
                        classes="setup-field-input",
                    )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Save", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the first input and pre-fill existing values."""
        if self.service_code == "langsmith":
            input_widget = self.query_one("#langsmith-api-key", Input)
            existing = os.getenv("LANGSMITH_API_KEY", "")
            if existing:
                input_widget.value = existing
            input_widget.focus()

        elif self.service_code == "langfuse":
            public_input = self.query_one("#langfuse-public-key", Input)
            secret_input = self.query_one("#langfuse-secret-key", Input)
            host_input = self.query_one("#langfuse-host", Input)

            existing_public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
            existing_secret = os.getenv("LANGFUSE_SECRET_KEY", "")
            existing_host = os.getenv("LANGFUSE_HOST", "")

            if existing_public:
                public_input.value = existing_public
            if existing_secret:
                secret_input.value = existing_secret
            if existing_host:
                host_input.value = existing_host

            public_input.focus()

        elif self.service_code == "opik":
            input_widget = self.query_one("#opik-api-key", Input)
            existing = os.getenv("OPIK_API_KEY", "")
            if existing:
                input_widget.value = existing
            input_widget.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save the configuration."""
        error_label = self.query_one("#error-message", Static)
        env_vars = {}

        if self.service_code == "langsmith":
            api_key = self.query_one("#langsmith-api-key", Input).value.strip()
            if not api_key:
                error_label.update("API key is required")
                return
            env_vars["LANGSMITH_API_KEY"] = api_key

        elif self.service_code == "langfuse":
            public_key = self.query_one("#langfuse-public-key", Input).value.strip()
            secret_key = self.query_one("#langfuse-secret-key", Input).value.strip()
            host = self.query_one("#langfuse-host", Input).value.strip()

            if not public_key:
                error_label.update("Public key is required")
                return
            if not secret_key:
                error_label.update("Secret key is required")
                return

            env_vars["LANGFUSE_PUBLIC_KEY"] = public_key
            env_vars["LANGFUSE_SECRET_KEY"] = secret_key
            if host:
                env_vars["LANGFUSE_HOST"] = host

        elif self.service_code == "opik":
            api_key = self.query_one("#opik-api-key", Input).value.strip()
            if not api_key:
                error_label.update("API key is required")
                return
            env_vars["OPIK_API_KEY"] = api_key

        # Save to .env
        save_env_vars(env_vars)
        reload_env_and_settings()

        # Enable the service
        enable_service(self.service_code, verbose=False)

        self.notify(f"Configured {self.service_label}", severity="information")
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)
