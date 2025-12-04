"""MCP server setup screens for Textual TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    TextArea,
)

from sdrbot_cli.mcp.client import MCP_AVAILABLE, test_mcp_connection
from sdrbot_cli.mcp.config import (
    add_mcp_server,
    disable_mcp_server,
    enable_mcp_server,
    load_mcp_config,
    remove_mcp_server,
    update_server_tool_count,
)

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


class MCPSetupScreen(Screen[bool | None]):
    """Screen for managing MCP servers."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    MCPSetupScreen {
        align: center middle;
    }

    #mcp-container {
        width: 70;
    }

    #mcp-list {
        max-height: 12;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="mcp-container", classes="setup-dialog-wide"):
            yield Static("MCP Servers", classes="setup-title")
            yield ListView(id="mcp-list", classes="setup-list")
            yield Static("", id="mcp-hint", classes="setup-hint")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate the server list on mount."""
        if not MCP_AVAILABLE:
            hint = self.query_one("#mcp-hint", Static)
            hint.update("MCP SDK not installed. Install with: pip install mcp")
        else:
            hint = self.query_one("#mcp-hint", Static)
            hint.update("↑↓ Navigate • Enter Select • Esc Back")
        self._refresh_server_list()

    def _refresh_server_list(self) -> None:
        """Refresh the server list with current status."""
        list_view = self.query_one("#mcp-list", ListView)
        list_view.clear()

        # Add "Add MCP Server" option
        add_item = ListItem(
            Horizontal(
                Static("+ Add MCP Server", classes="setup-list-item-label"),
                Static("", classes="setup-list-item-status"),
                classes="setup-list-item",
            ),
        )
        add_item.data = "add"
        list_view.append(add_item)

        # Load existing servers
        config = load_mcp_config()
        servers = config.get("servers", {})

        if servers:
            for name, server_config in servers.items():
                enabled = server_config.get("enabled", False)
                tool_count = server_config.get("tool_count", "?")

                if enabled:
                    status_text = f"● {tool_count} tools"
                    status_class = "status-active"
                else:
                    status_text = "Disabled"
                    status_class = "status-configured"

                item = ListItem(
                    Horizontal(
                        Static(name, classes="setup-list-item-label"),
                        Static(status_text, classes=f"setup-list-item-status {status_class}"),
                        classes="setup-list-item",
                    ),
                )
                item.data = f"server:{name}"
                list_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle server selection."""
        data = getattr(event.item, "data", None)
        if data == "add":
            if MCP_AVAILABLE:
                self.app.push_screen(AddMCPServerScreen(), self._on_action_complete)
            else:
                self.notify("MCP SDK not installed", severity="error")
        elif data and data.startswith("server:"):
            server_name = data[7:]
            self.app.push_screen(ManageMCPServerScreen(server_name), self._on_action_complete)

    def _on_action_complete(self, result: bool | None) -> None:
        """Called when a sub-screen is dismissed."""
        self._refresh_server_list()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(None)

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.dismiss(None)


class AddMCPServerScreen(ModalScreen[bool]):
    """Modal screen for adding a new MCP server."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    AddMCPServerScreen {
        align: center middle;
    }

    #add-mcp-dialog {
        width: 70;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="add-mcp-dialog", classes="setup-dialog-wide"):
            yield Static("Add MCP Server", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("Server name:", classes="setup-field-label")
                yield Input(
                    placeholder="e.g., github, filesystem, exa",
                    id="server-name-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Transport type:", classes="setup-field-label")
                yield ListView(id="transport-list", classes="setup-list")

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-continue", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate transport list and focus input."""
        list_view = self.query_one("#transport-list", ListView)

        # NOTE: HTTP transport disabled due to MCP SDK bug
        transports = [
            ("stdio", "stdio - Run as subprocess (npx, uvx, python)"),
            ("sse", "SSE - Server-Sent Events (HTTP streaming)"),
        ]

        for transport_id, transport_label in transports:
            item = ListItem(Static(transport_label))
            item.data = transport_id
            list_view.append(item)

        self.query_one("#server-name-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-continue":
            self._continue_setup()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in input field."""
        self._continue_setup()

    def _continue_setup(self) -> None:
        """Continue to transport-specific configuration."""
        name = self.query_one("#server-name-input", Input).value.strip()
        error_label = self.query_one("#error-message", Static)

        if not name:
            error_label.update("Server name is required")
            return

        # Check for duplicate
        config = load_mcp_config()
        if name in config.get("servers", {}):
            error_label.update(f"Server '{name}' already exists")
            return

        # Get selected transport
        list_view = self.query_one("#transport-list", ListView)
        if list_view.highlighted_child is None:
            error_label.update("Select a transport type")
            return

        transport = getattr(list_view.highlighted_child, "data", None)
        if not transport:
            error_label.update("Select a transport type")
            return

        # Continue to transport-specific screen
        if transport == "stdio":
            self.app.push_screen(
                StdioConfigScreen(name),
                self._on_config_complete,
            )
        else:  # sse
            self.app.push_screen(
                SSEConfigScreen(name),
                self._on_config_complete,
            )

    def _on_config_complete(self, result: bool) -> None:
        """Called when config screen completes."""
        if result:
            self.dismiss(True)
        # Stay on this screen if cancelled

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class StdioConfigScreen(ModalScreen[bool]):
    """Modal screen for configuring stdio transport."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    StdioConfigScreen {
        align: center middle;
    }

    #stdio-dialog {
        width: 70;
        height: auto;
    }

    #env-input {
        height: 4;
    }

    #status-message {
        height: auto;
        padding: 0;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, server_name: str) -> None:
        super().__init__()
        self.server_name = server_name

    def compose(self) -> ComposeResult:
        with Container(id="stdio-dialog", classes="setup-dialog-wide"):
            yield Static(f"Configure {self.server_name} (stdio)", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("Command:", classes="setup-field-label")
                yield Input(
                    placeholder="e.g., npx, uvx, python",
                    id="command-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Arguments:", classes="setup-field-label")
                yield Input(
                    placeholder="e.g., -y @modelcontextprotocol/server-github",
                    id="args-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label(
                    "Environment variables (KEY=VALUE, one per line):", classes="setup-field-label"
                )
                yield TextArea(
                    id="env-input",
                    classes="setup-field-input",
                )

            yield Static("", id="status-message", classes="setup-hint")
            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the first input."""
        self.query_one("#command-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._test_and_save()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _test_and_save(self) -> None:
        """Test connection and save configuration."""
        command = self.query_one("#command-input", Input).value.strip()
        args_str = self.query_one("#args-input", Input).value.strip()
        env_str = self.query_one("#env-input", TextArea).text.strip()

        error_label = self.query_one("#error-message", Static)
        status_label = self.query_one("#status-message", Static)

        if not command:
            error_label.update("Command is required")
            return

        args = args_str.split() if args_str else []

        # Parse environment variables (one per line)
        env = {}
        if env_str:
            for line in env_str.splitlines():
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip()

        server_config = {
            "enabled": True,
            "transport": "stdio",
            "command": command,
            "args": args,
            "env": env,
        }

        # Test connection
        status_label.update("Testing connection...")
        error_label.update("")

        # Run test in worker to avoid blocking UI
        self.run_worker(self._do_test_and_save(server_config), exclusive=True)

    async def _do_test_and_save(self, server_config: dict) -> None:
        """Run the connection test and save."""
        status_label = self.query_one("#status-message", Static)
        error_label = self.query_one("#error-message", Static)

        success, tool_count, error = await test_mcp_connection(server_config)

        if success:
            status_label.update(f"Connected! Found {tool_count} tools")

            # Save configuration
            add_mcp_server(
                name=self.server_name,
                transport="stdio",
                command=server_config["command"],
                args=server_config["args"],
                env=server_config["env"],
                enabled=True,
            )
            update_server_tool_count(self.server_name, tool_count)

            self.notify(f"Added MCP server: {self.server_name}", severity="information")
            self.dismiss(True)
        else:
            # Show error prominently - user must fix config or cancel
            status_label.update("")
            error_label.update(error)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class SSEConfigScreen(ModalScreen[bool]):
    """Modal screen for configuring SSE transport."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    SSEConfigScreen {
        align: center middle;
    }

    #sse-dialog {
        width: 70;
    }

    #auth-list {
        max-height: 6;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, server_name: str) -> None:
        super().__init__()
        self.server_name = server_name

    def compose(self) -> ComposeResult:
        with Container(id="sse-dialog", classes="setup-dialog-wide"):
            yield Static(f"Configure {self.server_name} (SSE)", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("Server URL:", classes="setup-field-label")
                yield Input(
                    placeholder="e.g., http://localhost:8080/mcp",
                    id="url-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Authentication:", classes="setup-field-label")
                yield ListView(id="auth-list", classes="setup-list")

            yield Static("", id="status-message", classes="setup-hint")
            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-continue", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate auth list and focus input."""
        list_view = self.query_one("#auth-list", ListView)

        auth_types = [
            ("none", "None - No authentication"),
            ("bearer", "Bearer Token"),
            ("apikey", "API Key (X-API-Key header)"),
            ("custom", "Custom Headers"),
        ]

        for auth_id, auth_label in auth_types:
            item = ListItem(Static(auth_label))
            item.data = auth_id
            list_view.append(item)

        self.query_one("#url-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-continue":
            self._continue_setup()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _continue_setup(self) -> None:
        """Continue to auth configuration or test."""
        url = self.query_one("#url-input", Input).value.strip()
        error_label = self.query_one("#error-message", Static)

        if not url:
            error_label.update("Server URL is required")
            return

        # Get selected auth type
        list_view = self.query_one("#auth-list", ListView)
        if list_view.highlighted_child is None:
            error_label.update("Select an authentication type")
            return

        auth_type = getattr(list_view.highlighted_child, "data", "none")

        if auth_type == "none":
            # No auth needed, go directly to test
            server_config = {
                "enabled": True,
                "transport": "sse",
                "url": url,
                "auth": {"type": "none"},
            }
            self.run_worker(self._test_and_save(server_config), exclusive=True)
        else:
            # Need to get auth details
            self.app.push_screen(
                SSEAuthScreen(self.server_name, url, auth_type),
                self._on_auth_complete,
            )

    def _on_auth_complete(self, result: bool) -> None:
        """Handle auth screen completion."""
        if result:
            self.dismiss(True)

    async def _test_and_save(self, server_config: dict) -> None:
        """Test and save the configuration."""
        status_label = self.query_one("#status-message", Static)
        error_label = self.query_one("#error-message", Static)

        status_label.update("Testing connection...")
        error_label.update("")

        success, tool_count, error = await test_mcp_connection(server_config)

        if success:
            status_label.update(f"Connected! Found {tool_count} tools")

            add_mcp_server(
                name=self.server_name,
                transport="sse",
                url=server_config["url"],
                auth=server_config.get("auth"),
                enabled=True,
            )
            update_server_tool_count(self.server_name, tool_count)

            self.notify(f"Added MCP server: {self.server_name}", severity="information")
            self.dismiss(True)
        else:
            # Show error prominently - user must fix config or cancel
            status_label.update("")
            error_label.update(error)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class SSEAuthScreen(ModalScreen[bool]):
    """Modal screen for configuring SSE authentication."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    SSEAuthScreen {
        align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, server_name: str, url: str, auth_type: str) -> None:
        super().__init__()
        self.server_name = server_name
        self.url = url
        self.auth_type = auth_type

    def compose(self) -> ComposeResult:
        with Container(id="auth-dialog", classes="setup-dialog"):
            yield Static(f"Authentication ({self.auth_type})", classes="setup-title")
            yield Static(
                "Use ${VAR_NAME} to reference environment variables",
                classes="setup-hint",
            )

            if self.auth_type == "bearer":
                with Vertical(classes="setup-field"):
                    yield Label("Bearer Token:", classes="setup-field-label")
                    yield Input(
                        placeholder="token or ${TOKEN_VAR}",
                        password=True,
                        id="token-input",
                        classes="setup-field-input",
                    )
            elif self.auth_type == "apikey":
                with Vertical(classes="setup-field"):
                    yield Label("API Key:", classes="setup-field-label")
                    yield Input(
                        placeholder="key or ${API_KEY_VAR}",
                        password=True,
                        id="apikey-input",
                        classes="setup-field-input",
                    )
            else:  # custom
                with Vertical(classes="setup-field"):
                    yield Label(
                        "Custom headers (KEY=VALUE, comma-separated):", classes="setup-field-label"
                    )
                    yield Input(
                        placeholder="e.g., X-Custom=value, Authorization=token",
                        id="headers-input",
                        classes="setup-field-input",
                    )

            yield Static("", id="status-message", classes="setup-hint")
            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the appropriate input."""
        if self.auth_type == "bearer":
            self.query_one("#token-input", Input).focus()
        elif self.auth_type == "apikey":
            self.query_one("#apikey-input", Input).focus()
        else:
            self.query_one("#headers-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._test_and_save()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _test_and_save(self) -> None:
        """Build config and test connection."""
        auth_config: dict = {"type": self.auth_type}

        if self.auth_type == "bearer":
            token = self.query_one("#token-input", Input).value.strip()
            if token:
                auth_config["token"] = token
        elif self.auth_type == "apikey":
            api_key = self.query_one("#apikey-input", Input).value.strip()
            if api_key:
                auth_config["api_key"] = api_key
        else:  # custom
            headers_str = self.query_one("#headers-input", Input).value.strip()
            headers = {}
            if headers_str:
                for part in headers_str.split(","):
                    part = part.strip()
                    if "=" in part:
                        key, value = part.split("=", 1)
                        headers[key.strip()] = value.strip()
            if headers:
                auth_config["headers"] = headers

        server_config = {
            "enabled": True,
            "transport": "sse",
            "url": self.url,
            "auth": auth_config,
        }

        self.run_worker(self._do_test_and_save(server_config), exclusive=True)

    async def _do_test_and_save(self, server_config: dict) -> None:
        """Run test and save."""
        status_label = self.query_one("#status-message", Static)
        error_label = self.query_one("#error-message", Static)

        status_label.update("Testing connection...")
        error_label.update("")

        success, tool_count, error = await test_mcp_connection(server_config)

        if success:
            status_label.update(f"Connected! Found {tool_count} tools")

            add_mcp_server(
                name=self.server_name,
                transport="sse",
                url=server_config["url"],
                auth=server_config.get("auth"),
                enabled=True,
            )
            update_server_tool_count(self.server_name, tool_count)

            self.notify(f"Added MCP server: {self.server_name}", severity="information")
            self.dismiss(True)
        else:
            # Show error prominently - user must fix config or cancel
            status_label.update("")
            error_label.update(error)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class ManageMCPServerScreen(ModalScreen[bool]):
    """Modal screen for managing an existing MCP server."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ManageMCPServerScreen {
        align: center middle;
    }

    #manage-list {
        max-height: 8;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, server_name: str) -> None:
        super().__init__()
        self.server_name = server_name

    def compose(self) -> ComposeResult:
        with Container(id="manage-dialog", classes="setup-dialog"):
            yield Static(f"Manage: {self.server_name}", classes="setup-title")
            yield Static("", id="server-info", classes="setup-hint")
            yield ListView(id="manage-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate server info and actions."""
        self._refresh_view()

    def _refresh_view(self) -> None:
        """Refresh the view with current server state."""
        config = load_mcp_config()
        server_config = config.get("servers", {}).get(self.server_name)

        if not server_config:
            self.dismiss(False)
            return

        enabled = server_config.get("enabled", False)
        tool_count = server_config.get("tool_count", "?")
        transport = server_config.get("transport", "unknown")

        # Build info string
        if transport == "stdio":
            cmd = server_config.get("command", "")
            args = " ".join(server_config.get("args", []))
            info = f"{cmd} {args}"
            if len(info) > 50:
                info = info[:47] + "..."
        else:
            info = server_config.get("url", "")
            if len(info) > 50:
                info = info[:47] + "..."

        info_label = self.query_one("#server-info", Static)
        info_label.update(f"Transport: {transport}\n{info}\nTools: {tool_count}")

        # Build action list
        list_view = self.query_one("#manage-list", ListView)
        list_view.clear()

        if enabled:
            disable_item = ListItem(Static("Disable"))
            disable_item.data = "disable"
            list_view.append(disable_item)
        else:
            enable_item = ListItem(Static("Enable"))
            enable_item.data = "enable"
            list_view.append(enable_item)

        test_item = ListItem(Static("Test Connection"))
        test_item.data = "test"
        list_view.append(test_item)

        view_item = ListItem(Static(f"View Tools ({tool_count})"))
        view_item.data = "view_tools"
        list_view.append(view_item)

        remove_item = ListItem(Static("Remove Server"))
        remove_item.data = "remove"
        list_view.append(remove_item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(True)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle action selection."""
        action = getattr(event.item, "data", None)

        if action == "enable":
            enable_mcp_server(self.server_name)
            self.notify(f"Enabled {self.server_name}", severity="information")
            self._refresh_view()
        elif action == "disable":
            disable_mcp_server(self.server_name)
            self.notify(f"Disabled {self.server_name}", severity="warning")
            self._refresh_view()
        elif action == "test":
            self.run_worker(self._test_connection(), exclusive=True)
        elif action == "view_tools":
            self.app.push_screen(ViewToolsScreen(self.server_name))
        elif action == "remove":
            self.app.push_screen(
                ConfirmRemoveScreen(self.server_name),
                self._on_remove_complete,
            )

    async def _test_connection(self) -> None:
        """Test the server connection."""
        config = load_mcp_config()
        server_config = config.get("servers", {}).get(self.server_name)

        if not server_config:
            self.notify("Server not found", severity="error")
            return

        self.notify("Testing connection...", severity="information")

        success, tool_count, error = await test_mcp_connection(server_config)

        if success:
            self.notify(f"Connected! Found {tool_count} tools", severity="information")
            update_server_tool_count(self.server_name, tool_count)
            self._refresh_view()
        else:
            self.notify(f"Connection failed: {error}", severity="error")

    def _on_remove_complete(self, result: bool) -> None:
        """Handle remove confirmation result."""
        if result:
            self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(True)


class ConfirmRemoveScreen(ModalScreen[bool]):
    """Modal to confirm removing an MCP server."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ConfirmRemoveScreen {
        align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, server_name: str) -> None:
        super().__init__()
        self.server_name = server_name

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog", classes="setup-dialog"):
            yield Static("Remove Server", classes="setup-title")
            yield Static(
                f"Are you sure you want to remove '{self.server_name}'?",
                classes="setup-hint",
            )

            with Horizontal(classes="setup-buttons"):
                yield Button("Remove", variant="error", id="btn-remove", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-remove":
            remove_mcp_server(self.server_name)
            self.notify(f"Removed {self.server_name}", severity="information")
            self.dismiss(True)
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class ViewToolsScreen(ModalScreen[None]):
    """Modal screen to view tools from an MCP server."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ViewToolsScreen {
        align: center middle;
    }

    #tools-dialog {
        width: 70;
        height: auto;
        max-height: 80%;
    }

    #tools-list {
        max-height: 15;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
    ]

    def __init__(self, server_name: str) -> None:
        super().__init__()
        self.server_name = server_name

    def compose(self) -> ComposeResult:
        with Container(id="tools-dialog", classes="setup-dialog-wide"):
            yield Static(f"Tools: {self.server_name}", classes="setup-title")
            yield Static("Loading...", id="tools-status", classes="setup-hint")
            yield ListView(id="tools-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Close", variant="default", id="btn-close", classes="setup-btn")

    def on_mount(self) -> None:
        """Load and display tools."""
        self.run_worker(self._load_tools(), exclusive=True)

    async def _load_tools(self) -> None:
        """Load tools from the server."""
        from sdrbot_cli.mcp.client import MCPServerConnection

        status_label = self.query_one("#tools-status", Static)
        list_view = self.query_one("#tools-list", ListView)

        config = load_mcp_config()
        server_config = config.get("servers", {}).get(self.server_name)

        if not server_config:
            status_label.update("Server not found")
            return

        status_label.update("Connecting...")

        conn = MCPServerConnection(name=self.server_name, config=server_config)

        try:
            if await conn.connect():
                status_label.update(f"Found {len(conn.tools)} tools:")

                for tool in conn.tools:
                    desc = tool.description or "No description"
                    if len(desc) > 50:
                        desc = desc[:47] + "..."

                    item = ListItem(
                        Vertical(
                            Static(f"[cyan]{tool.name}[/cyan]"),
                            Static(f"[dim]{desc}[/dim]"),
                        )
                    )
                    list_view.append(item)

                await conn.disconnect()
            else:
                status_label.update("Failed to connect")
        except Exception as e:
            status_label.update(f"Error: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-close":
            self.dismiss(None)

    def action_close(self) -> None:
        """Close the screen."""
        self.dismiss(None)
