"""Main Textual application for SDRbot."""

import sys

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Footer, Header, RichLog, Static, TextArea

from sdrbot_cli.auth.oauth_server import shutdown_server as shutdown_oauth_server
from sdrbot_cli.config import SessionState
from sdrbot_cli.tui.agent_worker import AgentWorker
from sdrbot_cli.tui.approval_bar import ApprovalBar
from sdrbot_cli.tui.loading_screen import LoadingScreen
from sdrbot_cli.tui.messages import (
    AgentExit,
    AgentMessage,
    AutoApproveUpdate,
    SkillCountUpdate,
    StatusUpdate,
    TaskListUpdate,
    TokenUpdate,
    ToolApprovalRequest,
    ToolCountUpdate,
)
from sdrbot_cli.tui.widgets import AgentInfo, StatusDisplay, ThinkingIndicator
from sdrbot_cli.ui import render_todo_list


class ChatInput(TextArea):
    """Custom TextArea that submits on Enter and adds newline on Alt/Shift+Enter."""

    DEFAULT_PLACEHOLDER = "Type a message..."

    class Submitted(TextArea.Changed):
        """Event fired when user submits the input."""

        def __init__(self, text_area: TextArea, value: str) -> None:
            super().__init__(text_area)
            self.value = value

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("placeholder", self.DEFAULT_PLACEHOLDER)
        super().__init__(*args, **kwargs)
        self._is_locked = False

    def set_locked(self, status: str = "Thinking...") -> None:
        """Lock the input and show a status message."""
        self._is_locked = True
        self.placeholder = status
        self.disabled = True

    def set_unlocked(self) -> None:
        """Unlock the input and restore normal state."""
        self._is_locked = False
        self.placeholder = self.DEFAULT_PLACEHOLDER
        self.disabled = False
        self.focus()

    def update_status(self, status: str) -> None:
        """Update the status message while locked."""
        if self._is_locked:
            self.placeholder = status

    async def _on_key(self, event) -> None:
        """Handle key events, intercepting Enter for submission."""
        # Ctrl+J inserts newline (Ctrl+Enter sends ctrl+j in most terminals)
        if event.key == "ctrl+j":
            self.insert("\n")
            event.prevent_default()
            event.stop()
            return
        # Plain enter submits
        if event.key == "enter":
            value = self.text.strip()
            if value and not self._is_locked:
                self.clear()
                self.post_message(self.Submitted(self, value))
            event.prevent_default()
            event.stop()
            return
        # Let parent handle all other keys
        await super()._on_key(event)


class SDRBotTUI(App[None]):
    """SDRbot Textual application."""

    CSS_PATH = ["sdrbot.css", "setup_common.tcss"]

    # Lock to dark theme and disable command palette
    ENABLE_COMMAND_PALETTE = False

    def get_css_variables(self) -> dict[str, str]:
        """Override theme CSS variables."""
        variables = super().get_css_variables()
        variables["accent"] = "teal"
        variables["warning"] = "teal"
        variables["footer-key-foreground"] = "teal"
        variables["text-accent"] = "teal"
        variables["text-warning"] = "teal"
        return variables

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+g", "show_help", "Help"),
        ("ctrl+j", "newline", "New line"),
        ("ctrl+t", "toggle_auto_approve", "Toggle Auto-approve"),
        ("ctrl+c", "interrupt_agent", "Interrupt"),
    ]

    # Add paste binding only on non-macOS platforms
    if sys.platform != "darwin":
        BINDINGS.insert(3, ("ctrl+shift+v", "paste", "Paste"))

    def __init__(self, session_state: SessionState, assistant_id: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.session_state = session_state
        self.assistant_id = assistant_id
        self.agent_worker: AgentWorker | None = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Horizontal(id="status_bar"):
            # Get sandbox type if set
            sandbox_type = getattr(self.session_state, "sandbox_type", None) or ""
            if sandbox_type == "none":
                sandbox_type = ""
            yield AgentInfo(
                agent_name="default" if self.assistant_id in (None, "agent") else self.assistant_id,
                auto_approve=self.session_state.auto_approve,
                sandbox_type=sandbox_type,
                id="agent_info",
            )
            yield StatusDisplay(id="status_display")
        with Container(id="app_grid"):
            yield RichLog(id="chat_log", wrap=True, auto_scroll=True)
            yield Static("", id="task_list_display")
        yield ApprovalBar(id="approval_bar")
        yield ThinkingIndicator(id="thinking_indicator")
        yield ChatInput(id="main_input")
        yield Footer()

    def action_quit(self) -> None:
        """An action to quit the app."""
        # Shutdown any active OAuth server before exiting
        shutdown_oauth_server()
        self.exit()

    def action_show_help(self) -> None:
        """Show the help screen."""
        from sdrbot_cli.tui.help_screen import HelpScreen

        self.push_screen(HelpScreen())

    def action_toggle_auto_approve(self) -> None:
        """Toggle auto-approve mode."""
        self.session_state.auto_approve = not self.session_state.auto_approve
        self.query_one("#agent_info", AgentInfo).set_auto_approve(self.session_state.auto_approve)
        status = "ON" if self.session_state.auto_approve else "OFF"
        self.notify(f"Auto-approve: {status}", severity="information")

    async def on_mount(self) -> None:
        """Called when app is mounted."""
        self.query_one("#main_input", ChatInput).focus()

        # Check if setup is needed (set by main.py) or forced (via /setup command)
        needs_setup = getattr(self.session_state, "needs_setup", False)
        force_setup = getattr(self.session_state, "force_setup", False)

        if needs_setup or force_setup:
            # Show setup wizard first
            from sdrbot_cli.tui.setup_wizard_screen import SetupWizardScreen

            # first_time=True shows Quit instead of Back
            self.push_screen(SetupWizardScreen(first_time=needs_setup), self._on_setup_complete)
        else:
            # Normal startup - initialize with loading screen
            self.run_worker(self._initialize_on_startup(), exclusive=True)

    def _on_setup_complete(self, result: bool | None = None) -> None:
        """Called when setup wizard is dismissed."""
        # Check if agent already exists (e.g., from /setup command when model was already configured)
        if self.session_state.agent is not None:
            # Agent exists, just reload it to pick up any changes
            self.run_worker(self._reload_existing_agent(), exclusive=True)
        else:
            # First-time setup, need to initialize everything
            self.run_worker(self._initialize_after_setup(), exclusive=True)

    async def _initialize_on_startup(self) -> None:
        """Initialize services, MCP, and agent on normal startup."""
        import asyncio

        from sdrbot_cli.config import create_model
        from sdrbot_cli.mcp.manager import initialize_mcp, reinitialize_mcp
        from sdrbot_cli.services import sync_enabled_services_if_needed

        # Show loading screen
        loading = LoadingScreen(title="Starting", message="Loading...")
        self.push_screen(loading)

        failed_mcp_servers: list[str] = []

        try:
            loop = asyncio.get_event_loop()

            # Sync services
            loading.update_message("Syncing services...")
            await loop.run_in_executor(None, sync_enabled_services_if_needed)

            # Initialize MCP
            loading.update_message("Initializing MCP servers...")
            _, failed_mcp_servers = await initialize_mcp()

            # Create model
            loading.update_message("Creating model...")
            model = await loop.run_in_executor(None, create_model)

            # Create agent
            from sdrbot_cli.agent import create_agent_with_config
            from sdrbot_cli.tools import fetch_url, http_request

            # Get sandbox backend if provided
            sandbox_backend = getattr(self.session_state, "sandbox_backend", None)
            sandbox_type = getattr(self.session_state, "sandbox_type", None)
            # Convert "none" string to actual None
            if sandbox_type == "none":
                sandbox_type = None

            def create_agent():
                tools = [http_request, fetch_url]
                return create_agent_with_config(
                    model,
                    self.assistant_id,
                    tools,
                    sandbox=sandbox_backend,
                    sandbox_type=sandbox_type,
                )

            loading.update_message("Creating agent...")
            agent, composite_backend, tool_count, skill_count = await loop.run_in_executor(
                None, create_agent
            )
            self.session_state.agent = agent
            self.session_state.backend = composite_backend
            self.session_state.tool_count = tool_count
            self.session_state.skill_count = skill_count

            # Set up reload callback
            async def reload_agent():
                _, new_failed = await reinitialize_mcp()
                new_agent, new_backend, new_tool_count, new_skill_count = create_agent()
                self.session_state.agent = new_agent
                self.session_state.backend = new_backend
                self.session_state.tool_count = new_tool_count
                self.session_state.skill_count = new_skill_count
                return new_failed

            self.session_state.set_reload_callback(reload_agent)

        finally:
            self.pop_screen()

        # Store failed servers to display after agent worker starts
        self._failed_mcp_servers = failed_mcp_servers

        # Start the agent worker
        self._start_agent_worker()

    async def _reload_existing_agent(self) -> None:
        """Reload the existing agent after setup changes."""
        if self.session_state._reload_callback:
            await self.session_state._reload_callback()
            # Update tool and skill counts in UI
            if self.agent_worker:
                self.agent_worker._send_counts()

    async def _initialize_after_setup(self) -> None:
        """Initialize services, MCP, and agent after setup completes."""
        import asyncio
        from pathlib import Path

        import dotenv

        from sdrbot_cli.config import create_model, settings
        from sdrbot_cli.mcp.manager import initialize_mcp, reinitialize_mcp
        from sdrbot_cli.services import sync_enabled_services_if_needed

        # Show loading screen
        loading = LoadingScreen(title="Initializing", message="Loading configuration...")
        self.push_screen(loading)

        failed_mcp_servers: list[str] = []

        try:
            # Reload environment to pick up changes from setup wizard
            dotenv.load_dotenv(Path.cwd() / ".env", override=True)
            settings.reload()

            # Run blocking sync operation in thread pool
            loop = asyncio.get_event_loop()
            loading.update_message("Syncing services...")
            await loop.run_in_executor(None, sync_enabled_services_if_needed)

            # Initialize MCP (already async)
            loading.update_message("Initializing MCP servers...")
            _, failed_mcp_servers = await initialize_mcp()

            # Create model (run in executor as it might be slow)
            loading.update_message("Creating model...")
            model = await loop.run_in_executor(None, create_model)

            # Now we need to create the agent
            from sdrbot_cli.agent import create_agent_with_config
            from sdrbot_cli.tools import fetch_url, http_request

            def create_agent():
                tools = [http_request, fetch_url]
                return create_agent_with_config(
                    model, self.assistant_id, tools, sandbox=None, sandbox_type=None
                )

            # Run agent creation in thread pool
            loading.update_message("Creating agent...")
            agent, composite_backend, tool_count, skill_count = await loop.run_in_executor(
                None, create_agent
            )
            self.session_state.agent = agent
            self.session_state.backend = composite_backend
            self.session_state.tool_count = tool_count
            self.session_state.skill_count = skill_count

            # Set up reload callback
            async def reload_agent():
                _, new_failed = await reinitialize_mcp()
                new_agent, new_backend, new_tool_count, new_skill_count = create_agent()
                self.session_state.agent = new_agent
                self.session_state.backend = new_backend
                self.session_state.tool_count = new_tool_count
                self.session_state.skill_count = new_skill_count
                return new_failed

            self.session_state.set_reload_callback(reload_agent)

        finally:
            # Dismiss loading screen
            self.pop_screen()

        # Store failed servers to display after agent worker starts
        self._failed_mcp_servers = failed_mcp_servers

        # Start the agent worker
        self._start_agent_worker()

    def _start_agent_worker(self) -> None:
        """Initialize and start the agent worker."""
        # Get failed MCP servers if any
        failed_mcp_servers = getattr(self, "_failed_mcp_servers", [])
        self._failed_mcp_servers = []  # Clear after reading

        self.agent_worker = AgentWorker(self, self.session_state, self.assistant_id)
        # Start the initial agent loop (splash, greetings etc.)
        self.run_worker(
            self.agent_worker._run_agent_loop(failed_mcp_servers=failed_mcp_servers),
            exclusive=True,
        )

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        """Handle chat input submission."""
        value = event.value.strip()
        if not value:
            return

        # Don't show slash commands in chat log
        if not value.startswith("/"):
            chat_log = self.query_one("#chat_log", RichLog)
            chat_log.write(Text(f"> {value}", style="bold #00a2c7"))

        # Update status to "Thinking" and show thinking indicator
        self.query_one("#status_display", StatusDisplay).set_status("Thinking")
        self.query_one("#main_input", ChatInput).display = False
        self.query_one("#thinking_indicator", ThinkingIndicator).show("Thinking...")

        if self.agent_worker:
            # Run user input processing as a worker to avoid blocking UI
            self.run_worker(self.agent_worker.process_user_input(value), exclusive=True)

    async def on_agent_message(self, message: AgentMessage) -> None:
        """Handle messages from the agent worker."""
        chat_log = self.query_one("#chat_log", RichLog)
        chat_log.write(message.renderable)

    async def on_agent_exit(self, message: AgentExit) -> None:
        """Handle agent exit message."""
        self.exit()

    async def on_task_list_update(self, message: TaskListUpdate) -> None:
        """Handle task list updates from the agent worker."""
        task_list_display = self.query_one("#task_list_display", Static)
        app_grid = self.query_one("#app_grid", Container)
        panel = render_todo_list(message.todos)
        if panel and message.todos:
            task_list_display.update(panel)
            task_list_display.add_class("visible")
            app_grid.add_class("has-tasks")
        else:
            task_list_display.remove_class("visible")
            app_grid.remove_class("has-tasks")

    async def on_token_update(self, message: TokenUpdate) -> None:
        """Handle token updates."""
        self.query_one("#status_display", StatusDisplay).update_tokens(message.total_tokens)

    async def on_tool_count_update(self, message: ToolCountUpdate) -> None:
        """Handle tool count updates."""
        self.query_one("#agent_info", AgentInfo).update_tool_count(message.count)

    async def on_skill_count_update(self, message: SkillCountUpdate) -> None:
        """Handle skill count updates."""
        self.query_one("#agent_info", AgentInfo).update_skill_count(message.count)

    def on_agent_info_agent_name_clicked(self, message: AgentInfo.AgentNameClicked) -> None:
        """Handle click on agent name - show agents screen."""
        from sdrbot_cli.tui.agents_screen import AgentsManagementScreen

        self.push_screen(
            AgentsManagementScreen(active_agent=self.assistant_id),
            self.agent_worker._on_agents_screen_closed if self.agent_worker else None,
        )

    def on_agent_info_skill_count_clicked(self, message: AgentInfo.SkillCountClicked) -> None:
        """Handle click on skill count - show skills screen."""
        from sdrbot_cli.tui.skills_screen import SkillsManagementScreen

        self.push_screen(
            SkillsManagementScreen(),
            self.agent_worker._on_setup_screen_closed if self.agent_worker else None,
        )

    def on_agent_info_tool_count_clicked(self, message: AgentInfo.ToolCountClicked) -> None:
        """Handle click on tool count - show tools screen."""
        from sdrbot_cli.tui.tools_screen import ToolsScreen

        self.push_screen(ToolsScreen())

    async def on_status_update(self, message: StatusUpdate) -> None:
        """Handle status updates."""
        self.query_one("#status_display", StatusDisplay).set_status(message.status)
        chat_input = self.query_one("#main_input", ChatInput)
        thinking_indicator = self.query_one("#thinking_indicator", ThinkingIndicator)

        if message.status == "Idle":
            # Hide thinking indicator and show input
            thinking_indicator.hide()
            chat_input.display = True
            chat_input.focus()
        else:
            # Update thinking indicator status
            thinking_indicator.update_status(message.status)

    async def on_auto_approve_update(self, message: AutoApproveUpdate) -> None:
        """Handle auto-approve status updates."""
        self.session_state.auto_approve = message.enabled
        self.query_one("#agent_info", AgentInfo).set_auto_approve(message.enabled)

    async def on_tool_approval_request(self, message: ToolApprovalRequest) -> None:
        """Handle tool approval request."""
        # Hide thinking indicator, show approval bar
        self.query_one("#thinking_indicator", ThinkingIndicator).hide()
        approval_bar = self.query_one("#approval_bar", ApprovalBar)
        approval_bar.show(message.future)

    def action_interrupt_agent(self) -> None:
        """Interrupt the running agent."""
        # Only interrupt if there are running workers
        cancelled_any = False
        for worker in self.workers:
            if worker.is_running:
                worker.cancel()
                cancelled_any = True
        if cancelled_any:
            self.query_one("#status_display", StatusDisplay).set_status("Interrupted")
            self.notify("Agent interrupted", severity="warning")

    async def on_unmount(self) -> None:
        """Cleanup when app is unmounted."""
        # Ensure OAuth server is shutdown on any exit path
        shutdown_oauth_server()
