"""Services setup screens for Textual TUI."""

import importlib
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from sdrbot_cli.auth.oauth_server import shutdown_server as shutdown_oauth_server
from sdrbot_cli.services import disable_service, enable_service
from sdrbot_cli.services.registry import load_config
from sdrbot_cli.setup.env import reload_env_and_settings, save_env_vars
from sdrbot_cli.setup.services import SERVICE_CATEGORIES, get_service_status

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


class OAuthFlowScreen(ModalScreen[bool]):
    """Modal screen that runs an OAuth flow with visual feedback."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    OAuthFlowScreen {
        align: center middle;
    }

    #oauth-dialog {
        width: 60;
        height: auto;
        border: heavy $warning;
        background: $panel;
        padding: 1 2 2 2;
    }

    #oauth-status {
        text-align: center;
        padding: 1 0;
        height: auto;
    }

    #oauth-instructions {
        color: $text-muted;
        text-align: center;
        padding: 1 0;
        height: auto;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        service_label: str,
        service_code: str,
        auth_module: str,
    ) -> None:
        super().__init__()
        self.service_label = service_label
        self.service_code = service_code
        self.auth_module = auth_module
        self._cancelled = False

    def compose(self) -> ComposeResult:
        with Container(id="oauth-dialog"):
            yield Static(f"{self.service_label} Authentication", classes="setup-title")
            yield Static("Preparing authentication...", id="oauth-status")
            yield Static(
                "A browser window will open.\nComplete the login there, then return here.",
                id="oauth-instructions",
            )
            yield Static("Press Esc to cancel and skip authentication", classes="setup-hint")
            with Horizontal(classes="setup-buttons"):
                yield Button("Skip", variant="default", id="btn-skip", classes="setup-btn")

    async def on_mount(self) -> None:
        """Start the OAuth flow."""
        self.run_worker(self._run_oauth_flow(), exclusive=True)

    async def _run_oauth_flow(self) -> None:
        """Run the OAuth flow in a worker thread."""
        import asyncio

        status = self.query_one("#oauth-status", Static)

        try:
            status.update("Opening browser...")

            # Import and reload the auth module
            auth = importlib.import_module(self.auth_module)
            importlib.reload(auth)

            # Run the blocking login() in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, auth.login)

            if not self._cancelled:
                self.dismiss(True)

        except Exception as e:
            if not self._cancelled:
                status.update(f"Authentication failed: {e}")
                instructions = self.query_one("#oauth-instructions", Static)
                instructions.update("You can authenticate later when using this service.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-skip":
            self._cancelled = True
            shutdown_oauth_server()
            self.dismiss(False)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self._cancelled = True
        shutdown_oauth_server()
        self.dismiss(False)


class ServicesSetupScreen(Screen[bool | None]):
    """Screen for selecting and configuring services by category."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ServicesSetupScreen {
        align: center middle;
    }

    #services-container {
        width: 70;
    }

    #categories-list {
        max-height: 10;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="services-container", classes="setup-dialog-wide"):
            yield Static("Services Setup", classes="setup-title")
            yield ListView(id="categories-list", classes="setup-list")
            yield Static("↑↓ Navigate • Enter Select • Esc Back", classes="setup-hint")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate the category list on mount."""
        self._refresh_category_list()

    def _refresh_category_list(self) -> None:
        """Refresh the category list with current status."""
        list_view = self.query_one("#categories-list", ListView)
        list_view.clear()

        config = load_config()

        for cat_code, cat_info in SERVICE_CATEGORIES.items():
            # Count enabled services in this category
            enabled_count = 0
            total_count = len(cat_info["services"])
            for service_code, _ in cat_info["services"]:
                if config.is_enabled(service_code):
                    enabled_count += 1

            if enabled_count > 0:
                status_text = f"{enabled_count}/{total_count} enabled"
                status_class = "status-active"
            else:
                status_text = "None enabled"
                status_class = "status-missing"

            item = ListItem(
                Horizontal(
                    Static(cat_info["label"], classes="setup-list-item-label"),
                    Static(status_text, classes=f"setup-list-item-status {status_class}"),
                    classes="setup-list-item",
                ),
            )
            item.data = cat_code
            list_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle category selection."""
        cat_code = getattr(event.item, "data", None)
        if cat_code:
            self.app.push_screen(CategoryScreen(cat_code), self._on_category_complete)

    def _on_category_complete(self, result: bool | None) -> None:
        """Called when category screen is dismissed."""
        self._refresh_category_list()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(None)

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.dismiss(None)


class CategoryScreen(ModalScreen[bool]):
    """Modal screen showing services in a category."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    CategoryScreen {
        align: center middle;
    }

    #services-list {
        max-height: 10;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, category_code: str) -> None:
        super().__init__()
        self.category_code = category_code
        self.cat_info = SERVICE_CATEGORIES[category_code]

    def compose(self) -> ComposeResult:
        with Container(id="category-dialog", classes="setup-dialog-wide"):
            yield Static(self.cat_info["label"], classes="setup-title")
            yield ListView(id="services-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate services list."""
        self._refresh_services_list()

    def _refresh_services_list(self) -> None:
        """Refresh the services list with current status."""
        list_view = self.query_one("#services-list", ListView)
        list_view.clear()

        for service_code, service_label in self.cat_info["services"]:
            configured, enabled = get_service_status(service_code)

            if configured:
                if enabled:
                    status_text = "✓ Enabled"
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

        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle service selection."""
        service_code = getattr(event.item, "data", None)
        if service_code:
            configured, _ = get_service_status(service_code)
            service_label = next(
                (label for code, label in self.cat_info["services"] if code == service_code),
                service_code.capitalize(),
            )

            if configured:
                # Show actions menu
                self.app.push_screen(
                    ServiceActionsScreen(service_code, service_label),
                    self._on_service_complete,
                )
            else:
                # Configure directly
                self._configure_service(service_code, service_label)

    def _configure_service(self, service_code: str, service_label: str) -> None:
        """Open the appropriate configuration screen for a service."""
        screen = get_service_config_screen(service_code, service_label)
        if screen:
            self.app.push_screen(screen, self._on_service_complete)

    def _on_service_complete(self, result: bool) -> None:
        """Called when service config is complete."""
        self._refresh_services_list()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(False)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class ServiceActionsScreen(ModalScreen[bool]):
    """Modal screen showing actions for a configured service."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ServiceActionsScreen {
        align: center middle;
    }

    #actions-list {
        max-height: 6;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, service_code: str, service_label: str) -> None:
        super().__init__()
        self.service_code = service_code
        self.service_label = service_label

    def compose(self) -> ComposeResult:
        with Container(id="actions-dialog", classes="setup-dialog"):
            yield Static(f"Manage {self.service_label}", classes="setup-title")
            yield ListView(id="actions-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate actions list."""
        list_view = self.query_one("#actions-list", ListView)
        _, enabled = get_service_status(self.service_code)

        actions = []
        if enabled:
            actions.append(("disable", "Disable Service"))
        else:
            actions.append(("enable", "Enable Service"))
        actions.append(("reconfigure", "Reconfigure Credentials"))

        for action_id, action_label in actions:
            item = ListItem(Static(action_label))
            item.data = action_id
            list_view.append(item)

        list_view.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle action selection."""
        action = getattr(event.item, "data", None)
        if action == "enable":
            enable_service(self.service_code, sync=False, verbose=False)
            self.dismiss(True)
        elif action == "disable":
            disable_service(self.service_code, verbose=False)
            self.dismiss(True)
        elif action == "reconfigure":
            screen = get_service_config_screen(self.service_code, self.service_label)
            if screen:
                self.app.push_screen(screen, self._on_config_complete)

    def _on_config_complete(self, result: bool) -> None:
        """Called when config screen is dismissed."""
        self.dismiss(result)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


# ============================================================================
# Service-specific configuration screens
# ============================================================================


class SimpleApiKeyScreen(ModalScreen[bool]):
    """Generic screen for services that only need an API key."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    SimpleApiKeyScreen {
        align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        service_code: str,
        service_label: str,
        env_var: str,
        placeholder: str = "Enter API key...",
    ) -> None:
        super().__init__()
        self.service_code = service_code
        self.service_label = service_label
        self.env_var = env_var
        self.placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Container(id="api-key-dialog", classes="setup-dialog"):
            yield Static(f"{self.service_label} Configuration", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("API Key:", classes="setup-field-label")
                yield Input(
                    placeholder=self.placeholder,
                    password=True,
                    id="api-key-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the input."""
        self.query_one("#api-key-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        self._save_config()

    def _save_config(self) -> None:
        """Save the API key and enable service."""
        api_key = self.query_one("#api-key-input", Input).value.strip()
        error_label = self.query_one("#error-message", Static)

        if not api_key:
            error_label.update("API key is required")
            return

        save_env_vars({self.env_var: api_key})
        reload_env_and_settings()
        enable_service(self.service_code, sync=False, verbose=False)
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class OAuthChoiceScreen(ModalScreen[bool]):
    """Screen for services that support both API token and OAuth."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    OAuthChoiceScreen {
        align: center middle;
    }

    #choice-list {
        max-height: 6;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        service_code: str,
        service_label: str,
        token_option: tuple[str, str, str],  # (env_var, label, placeholder)
        oauth_option: tuple[
            str, str, str, str
        ],  # (client_id_var, client_secret_var, label, auth_module)
    ) -> None:
        super().__init__()
        self.service_code = service_code
        self.service_label = service_label
        self.token_option = token_option
        self.oauth_option = oauth_option

    def compose(self) -> ComposeResult:
        with Container(id="choice-dialog", classes="setup-dialog"):
            yield Static(f"{self.service_label} Authentication", classes="setup-title")
            yield Static("Choose authentication method:", classes="setup-hint")
            yield ListView(id="choice-list", classes="setup-list")

    def on_mount(self) -> None:
        """Populate choices."""
        list_view = self.query_one("#choice-list", ListView)

        item1 = ListItem(Static(self.token_option[1]))
        item1.data = "token"
        list_view.append(item1)

        item2 = ListItem(Static(self.oauth_option[2]))
        item2.data = "oauth"
        list_view.append(item2)

        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle choice selection."""
        choice = getattr(event.item, "data", None)
        if choice == "token":
            self.app.push_screen(
                SimpleApiKeyScreen(
                    self.service_code,
                    self.service_label,
                    self.token_option[0],
                    self.token_option[2],
                ),
                self._on_config_complete,
            )
        elif choice == "oauth":
            self.app.push_screen(
                OAuthCredentialsScreen(
                    self.service_code,
                    self.service_label,
                    self.oauth_option[0],
                    self.oauth_option[1],
                    self.oauth_option[3],
                ),
                self._on_config_complete,
            )

    def _on_config_complete(self, result: bool) -> None:
        """Called when config screen is dismissed."""
        self.dismiss(result)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class OAuthCredentialsScreen(ModalScreen[bool]):
    """Screen for entering OAuth client credentials."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    OAuthCredentialsScreen {
        align: center middle;
    }

    #oauth-dialog {
        width: 70;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        service_code: str,
        service_label: str,
        client_id_var: str,
        client_secret_var: str,
        auth_module: str | None = None,
    ) -> None:
        super().__init__()
        self.service_code = service_code
        self.service_label = service_label
        self.client_id_var = client_id_var
        self.client_secret_var = client_secret_var
        self.auth_module = auth_module

    def compose(self) -> ComposeResult:
        with Container(id="oauth-dialog", classes="setup-dialog-wide"):
            yield Static(f"{self.service_label} OAuth Setup", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("Client ID:", classes="setup-field-label")
                yield Input(
                    placeholder="Enter Client ID...",
                    id="client-id-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Client Secret:", classes="setup-field-label")
                yield Input(
                    placeholder="Enter Client Secret...",
                    password=True,
                    id="client-secret-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the first input."""
        self.query_one("#client-id-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save credentials and initiate OAuth flow."""
        client_id = self.query_one("#client-id-input", Input).value.strip()
        client_secret = self.query_one("#client-secret-input", Input).value.strip()
        error_label = self.query_one("#error-message", Static)

        if not client_id:
            error_label.update("Client ID is required")
            return
        if not client_secret:
            error_label.update("Client Secret is required")
            return

        error_label.update("")

        # Save credentials
        save_env_vars(
            {
                self.client_id_var: client_id,
                self.client_secret_var: client_secret,
            }
        )
        reload_env_and_settings()

        # Start OAuth flow if auth module specified
        if self.auth_module:
            self.app.push_screen(
                OAuthFlowScreen(self.service_label, self.service_code, self.auth_module),
                self._on_oauth_complete,
            )
        else:
            enable_service(self.service_code, sync=False, verbose=False)
            self.dismiss(True)

    def _on_oauth_complete(self, result: bool) -> None:
        """Called when OAuth flow completes."""
        if result:
            enable_service(self.service_code, sync=False, verbose=False)
        self.dismiss(result)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class ZohoCrmScreen(ModalScreen[bool]):
    """Configuration screen for Zoho CRM with region selection."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ZohoCrmScreen {
        align: center middle;
    }

    #zoho-dialog {
        width: 70;
    }

    #region-list {
        max-height: 8;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    REGIONS = [
        ("us", "US (zoho.com)"),
        ("eu", "EU (zoho.eu)"),
        ("in", "India (zoho.in)"),
        ("au", "Australia (zoho.com.au)"),
        ("cn", "China (zoho.com.cn)"),
        ("jp", "Japan (zoho.jp)"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.selected_region: str | None = None

    def compose(self) -> ComposeResult:
        with Container(id="zoho-dialog", classes="setup-dialog-wide"):
            yield Static("Zoho CRM Configuration", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("Client ID:", classes="setup-field-label")
                yield Input(
                    placeholder="Enter Client ID...",
                    id="client-id-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Client Secret:", classes="setup-field-label")
                yield Input(
                    placeholder="Enter Client Secret...",
                    password=True,
                    id="client-secret-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Data Center Region:", classes="setup-field-label")
                yield ListView(id="region-list", classes="setup-list")

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate region list and focus first input."""
        list_view = self.query_one("#region-list", ListView)
        for region_code, region_label in self.REGIONS:
            item = ListItem(Static(region_label))
            item.data = region_code
            list_view.append(item)

        self.query_one("#client-id-input", Input).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle region selection."""
        self.selected_region = getattr(event.item, "data", None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save Zoho configuration."""
        client_id = self.query_one("#client-id-input", Input).value.strip()
        client_secret = self.query_one("#client-secret-input", Input).value.strip()
        error_label = self.query_one("#error-message", Static)

        if not client_id:
            error_label.update("Client ID is required")
            return
        if not client_secret:
            error_label.update("Client Secret is required")
            return
        if not self.selected_region:
            error_label.update("Please select a region")
            return

        error_label.update("")

        save_env_vars(
            {
                "ZOHO_CLIENT_ID": client_id,
                "ZOHO_CLIENT_SECRET": client_secret,
                "ZOHO_REGION": self.selected_region,
            }
        )
        reload_env_and_settings()

        # Show OAuth progress screen
        self.app.push_screen(
            OAuthFlowScreen("Zoho CRM", "zohocrm", "sdrbot_cli.auth.zohocrm"),
            self._on_oauth_complete,
        )

    def _on_oauth_complete(self, result: bool) -> None:
        """Called when OAuth flow completes."""
        if result:
            enable_service("zohocrm", sync=False, verbose=False)
        self.dismiss(result)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class DatabaseConfigScreen(ModalScreen[bool]):
    """Configuration screen for database connections."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    DatabaseConfigScreen {
        align: center middle;
    }

    #db-dialog {
        width: 70;
    }

    #ssl-list {
        max-height: 6;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        service_code: str,
        service_label: str,
        env_prefix: str,
        default_port: str,
        ssl_options: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self.service_code = service_code
        self.service_label = service_label
        self.env_prefix = env_prefix
        self.default_port = default_port
        self.ssl_options = ssl_options
        self.selected_ssl: str | None = None

    def compose(self) -> ComposeResult:
        with Container(id="db-dialog", classes="setup-dialog-wide"):
            yield Static(f"{self.service_label} Configuration", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("Host:", classes="setup-field-label")
                yield Input(
                    placeholder="localhost",
                    value="localhost",
                    id="host-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Port:", classes="setup-field-label")
                yield Input(
                    placeholder=self.default_port,
                    value=self.default_port,
                    id="port-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Username:", classes="setup-field-label")
                yield Input(
                    placeholder="Enter username...",
                    id="user-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Password:", classes="setup-field-label")
                yield Input(
                    placeholder="Enter password...",
                    password=True,
                    id="pass-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Database Name:", classes="setup-field-label")
                yield Input(
                    placeholder="Enter database name...",
                    id="db-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("SSL Mode:", classes="setup-field-label")
                yield ListView(id="ssl-list", classes="setup-list")

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate SSL options and focus first input."""
        list_view = self.query_one("#ssl-list", ListView)
        for ssl_code, ssl_label in self.ssl_options:
            item = ListItem(Static(ssl_label))
            item.data = ssl_code
            list_view.append(item)

        self.query_one("#host-input", Input).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle SSL selection."""
        self.selected_ssl = getattr(event.item, "data", None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save database configuration."""
        host = self.query_one("#host-input", Input).value.strip()
        port = self.query_one("#port-input", Input).value.strip()
        user = self.query_one("#user-input", Input).value.strip()
        password = self.query_one("#pass-input", Input).value.strip()
        db_name = self.query_one("#db-input", Input).value.strip()
        error_label = self.query_one("#error-message", Static)

        if not host:
            error_label.update("Host is required")
            return
        if not user:
            error_label.update("Username is required")
            return
        if not password:
            error_label.update("Password is required")
            return
        if not db_name:
            error_label.update("Database name is required")
            return

        error_label.update("")

        env_vars = {
            f"{self.env_prefix}_HOST": host,
            f"{self.env_prefix}_PORT": port,
            f"{self.env_prefix}_USER": user,
            f"{self.env_prefix}_PASSWORD": password,
            f"{self.env_prefix}_DB": db_name,
        }

        if self.selected_ssl:
            env_vars[f"{self.env_prefix}_SSL_MODE"] = self.selected_ssl

        save_env_vars(env_vars)
        reload_env_and_settings()
        enable_service(self.service_code, sync=False, verbose=False)
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class MongoDbScreen(ModalScreen[bool]):
    """Configuration screen for MongoDB."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    MongoDbScreen {
        align: center middle;
    }

    #mongo-dialog {
        width: 70;
    }

    #tls-list {
        max-height: 4;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.selected_tls: str | None = "false"

    def compose(self) -> ComposeResult:
        with Container(id="mongo-dialog", classes="setup-dialog-wide"):
            yield Static("MongoDB Configuration", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("Connection URI:", classes="setup-field-label")
                yield Input(
                    placeholder="mongodb://localhost:27017",
                    value="mongodb://localhost:27017",
                    password=True,
                    id="uri-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Database Name:", classes="setup-field-label")
                yield Input(
                    placeholder="Enter database name...",
                    id="db-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Enable TLS:", classes="setup-field-label")
                yield ListView(id="tls-list", classes="setup-list")

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate TLS options and focus first input."""
        list_view = self.query_one("#tls-list", ListView)
        for tls_code, tls_label in [("false", "Disabled"), ("true", "Enabled")]:
            item = ListItem(Static(tls_label))
            item.data = tls_code
            list_view.append(item)

        self.query_one("#uri-input", Input).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle TLS selection."""
        self.selected_tls = getattr(event.item, "data", None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save MongoDB configuration."""
        uri = self.query_one("#uri-input", Input).value.strip()
        db_name = self.query_one("#db-input", Input).value.strip()
        error_label = self.query_one("#error-message", Static)

        if not uri:
            error_label.update("Connection URI is required")
            return
        if not db_name:
            error_label.update("Database name is required")
            return

        error_label.update("")

        env_vars = {
            "MONGODB_URI": uri,
            "MONGODB_DB": db_name,
        }

        if self.selected_tls == "true":
            env_vars["MONGODB_TLS"] = "true"

        save_env_vars(env_vars)
        reload_env_and_settings()
        enable_service("mongodb", sync=False, verbose=False)
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


# ============================================================================
# Factory function to get appropriate config screen for a service
# ============================================================================


def get_service_config_screen(service_code: str, service_label: str) -> ModalScreen | None:
    """Return the appropriate configuration screen for a service."""
    # Simple API key services
    if service_code == "attio":
        return SimpleApiKeyScreen(service_code, service_label, "ATTIO_API_KEY", "sk_...")
    elif service_code == "apollo":
        return SimpleApiKeyScreen(
            service_code, service_label, "APOLLO_API_KEY", "Enter Apollo API key..."
        )
    elif service_code == "hunter":
        return SimpleApiKeyScreen(
            service_code, service_label, "HUNTER_API_KEY", "Enter Hunter.io API key..."
        )
    elif service_code == "lusha":
        return SimpleApiKeyScreen(
            service_code, service_label, "LUSHA_API_KEY", "Enter Lusha API key..."
        )
    elif service_code == "tavily":
        return SimpleApiKeyScreen(service_code, service_label, "TAVILY_API_KEY", "tvly-...")

    # OAuth services with choice
    elif service_code == "hubspot":
        return OAuthChoiceScreen(
            service_code,
            service_label,
            ("HUBSPOT_ACCESS_TOKEN", "Personal Access Token", "pat-..."),
            (
                "HUBSPOT_CLIENT_ID",
                "HUBSPOT_CLIENT_SECRET",
                "OAuth (Client ID/Secret)",
                "sdrbot_cli.auth.hubspot",
            ),
        )
    elif service_code == "pipedrive":
        return OAuthChoiceScreen(
            service_code,
            service_label,
            ("PIPEDRIVE_API_TOKEN", "API Token", "Enter API token..."),
            (
                "PIPEDRIVE_CLIENT_ID",
                "PIPEDRIVE_CLIENT_SECRET",
                "OAuth (Client ID/Secret)",
                "sdrbot_cli.auth.pipedrive",
            ),
        )

    # OAuth-only services
    elif service_code == "salesforce":
        return OAuthCredentialsScreen(
            service_code,
            service_label,
            "SF_CLIENT_ID",
            "SF_CLIENT_SECRET",
            "sdrbot_cli.auth.salesforce",
        )

    # Complex services
    elif service_code == "zohocrm":
        return ZohoCrmScreen()

    # Database services
    elif service_code == "postgres":
        return DatabaseConfigScreen(
            service_code,
            service_label,
            "POSTGRES",
            "5432",
            [
                ("", "None (no SSL)"),
                ("require", "Require (encrypt, no verification)"),
                ("verify-ca", "Verify CA"),
                ("verify-full", "Verify Full"),
            ],
        )
    elif service_code == "mysql":
        return DatabaseConfigScreen(
            service_code,
            service_label,
            "MYSQL",
            "3306",
            [
                ("false", "Disabled"),
                ("true", "Enabled"),
            ],
        )
    elif service_code == "mongodb":
        return MongoDbScreen()

    return None
