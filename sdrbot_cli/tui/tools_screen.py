"""Tools modal screen for displaying all loaded tools."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static, Tab, Tabs

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


def get_grouped_tools() -> dict[str, dict[str, list[tuple[str, str]]]]:
    """Get all tools grouped by category and source.

    Only includes tools allowed under the current tool scope setting.

    Returns:
        Dict with keys "builtin", "services", "mcp", each mapping
        source name to list of (tool_name, description) tuples.
    """
    from sdrbot_cli.mcp.manager import get_mcp_manager
    from sdrbot_cli.services import SERVICES, TRACING_SERVICES
    from sdrbot_cli.services.registry import get_tool_scope_setting, load_config
    from sdrbot_cli.tools import is_tool_allowed

    result = {
        "builtin": {},
        "services": {},
        "mcp": {},
    }

    config = load_config()
    current_scope = get_tool_scope_setting()

    # Deepagents built-in tools (provided by the agent framework)
    deepagents_tools = [
        ("edit_file", "Edit a file by replacing text"),
        ("execute", "Execute shell commands"),
        ("glob", "Find files matching a pattern"),
        ("grep", "Search for text in files"),
        ("ls", "List directory contents"),
        ("read_file", "Read contents of a file"),
        ("task", "Delegate work to a subagent"),
        ("write_file", "Write content to a file"),
        ("write_todos", "Manage task list"),
    ]
    result["builtin"]["Deepagents"] = deepagents_tools

    # SDRbot core tools
    sdrbot_tools = [
        ("fetch_url", "Fetch and parse web page content"),
        ("http_request", "Make HTTP requests to external APIs"),
        ("sync_crm_schema", "Sync CRM schema and regenerate tools"),
    ]
    result["builtin"]["SDRbot"] = sdrbot_tools

    # Memory tools
    memory_tools = [
        ("append_memory", "Append content to long-term memory"),
        ("read_memory", "Read long-term memory file"),
        ("write_memory", "Write to long-term memory file"),
    ]
    result["builtin"]["Memory"] = memory_tools

    # Service tools
    for service_name in SERVICES:
        if not config.is_enabled(service_name):
            continue

        # Tracing services provide callbacks, not tools
        if service_name in TRACING_SERVICES:
            continue

        try:
            service_module = __import__(
                f"sdrbot_cli.services.{service_name}", fromlist=["get_tools"]
            )
            if hasattr(service_module, "get_tools"):
                service_tools = service_module.get_tools()
                if service_tools:
                    tool_list = []
                    for tool in service_tools:
                        # Filter by current scope
                        if not is_tool_allowed(tool, current_scope):
                            continue
                        desc = tool.description or "No description"
                        # Truncate long descriptions
                        if len(desc) > 60:
                            desc = desc[:57] + "..."
                        tool_list.append((tool.name, desc))
                    # Sort alphabetically
                    tool_list.sort(key=lambda x: x[0])
                    if tool_list:  # Only add if there are tools after filtering
                        result["services"][service_name.title()] = tool_list
        except ImportError:
            pass

    # MCP tools
    mcp_manager = get_mcp_manager()
    for server_name in sorted(mcp_manager.get_connected_servers()):
        conn = mcp_manager.connections[server_name]
        if conn.tools:
            tool_list = []
            for mcp_tool in conn.tools:
                desc = mcp_tool.description or "No description"
                if len(desc) > 60:
                    desc = desc[:57] + "..."
                tool_list.append((mcp_tool.name, desc))
            # Sort alphabetically
            tool_list.sort(key=lambda x: x[0])
            result["mcp"][server_name] = tool_list

    return result


class ToolsScreen(ModalScreen[None]):
    """Modal screen displaying all loaded tools."""

    CSS_PATH = [SETUP_CSS_PATH]

    def __init__(self, initial_tab: str = "tab-builtin", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._initial_tab = initial_tab
        self._current_tab = initial_tab

    CSS = """
    ToolsScreen {
        align: center middle;
    }

    #tools-container {
        width: 90;
        height: 35;
    }

    #tools-tabs {
        height: 3;
        dock: top;
    }

    .tools-scroll {
        height: 20;
        padding: 0 1;
        scrollbar-gutter: stable;
        scrollbar-size: 1 1;
    }

    .tools-group-title {
        text-style: bold;
        color: #00d7af;
        margin-top: 1;
    }

    .tools-group-title-first {
        text-style: bold;
        color: #00d7af;
    }

    .tool-line {
        padding-left: 2;
        height: 1;
    }

    .tool-name {
        color: $primary;
        text-style: bold;
        width: auto;
    }

    .tool-desc {
        color: $text-muted;
        width: 1fr;
    }

    .content-pane {
        display: none;
    }

    .content-pane.active {
        display: block;
    }

    #tools-hint {
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
        ("ctrl+t", "cycle_scope", "Cycle Scope"),
    ]

    def compose(self) -> ComposeResult:
        self._groups = get_grouped_tools()

        # Count tools per category
        builtin_count = sum(len(tools) for tools in self._groups["builtin"].values())
        services_count = sum(len(tools) for tools in self._groups["services"].values())
        mcp_count = sum(len(tools) for tools in self._groups["mcp"].values())

        with Container(id="tools-container", classes="setup-dialog-wide"):
            yield Tabs(
                Tab(f"Built-in ({builtin_count})", id="tab-builtin"),
                Tab(f"Services ({services_count})", id="tab-services"),
                Tab(f"MCP ({mcp_count})", id="tab-mcp"),
                id="tools-tabs",
            )

            # Built-in content
            with VerticalScroll(classes="tools-scroll content-pane active", id="pane-builtin"):
                first_group = True
                for source_name, tools in sorted(self._groups["builtin"].items()):
                    title_class = "tools-group-title-first" if first_group else "tools-group-title"
                    yield Static(f"{source_name} ({len(tools)})", classes=title_class)
                    first_group = False
                    for tool_name, description in tools:
                        with Horizontal(classes="tool-line"):
                            yield Static(f"{tool_name}: ", classes="tool-name")
                            yield Static(description, classes="tool-desc")

            # Services content
            with VerticalScroll(classes="tools-scroll content-pane", id="pane-services"):
                if self._groups["services"]:
                    first_group = True
                    for source_name, tools in sorted(self._groups["services"].items()):
                        title_class = (
                            "tools-group-title-first" if first_group else "tools-group-title"
                        )
                        yield Static(f"{source_name} ({len(tools)})", classes=title_class)
                        first_group = False
                        for tool_name, description in tools:
                            with Horizontal(classes="tool-line"):
                                yield Static(f"{tool_name}: ", classes="tool-name")
                                yield Static(description, classes="tool-desc")
                else:
                    yield Static("No services enabled.", classes="tool-line")

            # MCP content
            with VerticalScroll(classes="tools-scroll content-pane", id="pane-mcp"):
                if self._groups["mcp"]:
                    first_group = True
                    for source_name, tools in sorted(self._groups["mcp"].items()):
                        title_class = (
                            "tools-group-title-first" if first_group else "tools-group-title"
                        )
                        yield Static(f"{source_name} ({len(tools)})", classes=title_class)
                        first_group = False
                        for tool_name, description in tools:
                            with Horizontal(classes="tool-line"):
                                yield Static(f"{tool_name}: ", classes="tool-name")
                                yield Static(description, classes="tool-desc")
                else:
                    yield Static("No MCP servers connected.", classes="tool-line")

            yield Static("^t Tool Scope • Esc Close", id="tools-hint", classes="setup-hint")
            with Container(classes="setup-buttons"):
                yield Button("Close", variant="default", id="btn-close", classes="setup-btn")

    def on_mount(self) -> None:
        """Activate the initial tab on mount."""
        if self._initial_tab != "tab-builtin":
            tabs = self.query_one("#tools-tabs", Tabs)
            tabs.active = self._initial_tab

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Handle tab switching."""
        # Track current tab
        self._current_tab = event.tab.id

        # Hide all panes
        for pane in self.query(".content-pane"):
            pane.remove_class("active")

        # Show the selected pane
        tab_id = event.tab.id
        if tab_id == "tab-builtin":
            self.query_one("#pane-builtin").add_class("active")
        elif tab_id == "tab-services":
            self.query_one("#pane-services").add_class("active")
        elif tab_id == "tab-mcp":
            self.query_one("#pane-mcp").add_class("active")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-close":
            self.dismiss(None)

    def action_close(self) -> None:
        """Close the tools screen."""
        self.dismiss(None)

    def action_cycle_scope(self) -> None:
        """Cycle tool scope and refresh the tools list."""
        from sdrbot_cli.services.registry import cycle_tool_scope

        from .widgets import AgentInfo

        new_scope = cycle_tool_scope()

        # Update the app's AgentInfo widget
        try:
            self.app.query_one("#agent_info", AgentInfo).update_tool_scope(new_scope)
        except Exception:
            pass  # Widget may not exist in some contexts

        self.notify(f"Tool scope: {new_scope.capitalize()}")

        # Dismiss and re-push to refresh the tools list, restoring the current tab
        current_tab = self._current_tab

        def reopen_screen(_: None) -> None:
            self.app.push_screen(ToolsScreen(initial_tab=current_tab))

        self.dismiss(None)
        self.app.call_after_refresh(reopen_screen, None)

        # Trigger agent reload in the app
        if hasattr(self.app, "agent_worker") and self.app.agent_worker:
            self.app.run_worker(self.app.agent_worker._reload_agent_async(), exclusive=True)
