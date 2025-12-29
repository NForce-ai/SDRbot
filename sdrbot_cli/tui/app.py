"""Main Textual application for SDRbot."""

import sys

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Header, OptionList, RichLog, Static, TextArea
from textual.widgets.option_list import Option

from sdrbot_cli.auth.oauth_server import shutdown_server as shutdown_oauth_server
from sdrbot_cli.config import TUI_COMMANDS, SessionState
from sdrbot_cli.image_utils import (
    ImageTracker,
    get_clipboard_image,
    is_image_path,
    load_image_from_path,
)
from sdrbot_cli.tui.agent_worker import AgentWorker
from sdrbot_cli.tui.approval_bar import ApprovalBar
from sdrbot_cli.tui.loading_screen import LoadingScreen
from sdrbot_cli.tui.messages import (
    AgentExit,
    AgentMessage,
    AutoApproveUpdate,
    ImageCountUpdate,
    SkillCountUpdate,
    StatusUpdate,
    TaskListUpdate,
    TokenUpdate,
    ToolApprovalRequest,
    ToolCountUpdate,
)
from sdrbot_cli.tui.widgets import (
    AgentInfo,
    AppFooter,
    ImageAttachmentBar,
    StatusDisplay,
    ThinkingIndicator,
    VersionIndicator,
)
from sdrbot_cli.ui import render_todo_list


class CommandSuggestions(OptionList):
    """Dropdown widget showing slash command suggestions."""

    DEFAULT_CSS = """
    CommandSuggestions {
        layer: overlay;
        height: auto;
        max-height: 10;
        width: auto;
        min-width: 30;
        background: $surface;
        border: round $accent;
        display: none;
        padding: 0;
    }

    CommandSuggestions:focus {
        border: round $accent;
    }

    CommandSuggestions.visible {
        display: block;
    }

    CommandSuggestions > .option-list--option-highlighted {
        background: $accent 30%;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._commands = TUI_COMMANDS

    def filter_commands(self, prefix: str) -> list[tuple[str, str]]:
        """Filter commands that match the given prefix."""
        # Remove leading slash if present
        search = prefix.lstrip("/").lower()
        matches = []
        for cmd, desc in self._commands.items():
            if cmd.startswith(search):
                matches.append((cmd, desc))
        # Sort by command name
        return sorted(matches, key=lambda x: x[0])

    def update_suggestions(self, prefix: str) -> bool:
        """Update the suggestions based on prefix. Returns True if there are matches."""
        matches = self.filter_commands(prefix)
        self.clear_options()
        if matches:
            for cmd, desc in matches:
                # Create a rich text prompt with command and description
                prompt = Text()
                prompt.append(f"/{cmd}", style="bold #00CCA3")
                prompt.append(f"  {desc}", style="dim")
                self.add_option(Option(prompt, id=cmd))
            self.highlighted = 0
            return True
        return False

    def get_selected_command(self) -> str | None:
        """Get the currently highlighted command."""
        if self.highlighted is not None and self.option_count > 0:
            option = self.get_option_at_index(self.highlighted)
            return f"/{option.id}"
        return None


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
        self._suggestions_visible = False
        # History navigation
        self._history: list[str] = []
        self._history_index: int = -1  # -1 means not navigating history
        self._draft: str = ""  # Stores current text when navigating history

    def set_locked(self, status: str = "Thinking...") -> None:
        """Lock the input and show a status message."""
        self._is_locked = True
        self.placeholder = status
        self.disabled = True
        # Hide suggestions when locked
        self._hide_suggestions()

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

    def _get_suggestions_widget(self) -> CommandSuggestions | None:
        """Get the command suggestions widget from the app."""
        try:
            return self.app.query_one("#command_suggestions", CommandSuggestions)
        except Exception:
            return None

    def _show_suggestions(self) -> None:
        """Show the suggestions dropdown."""
        suggestions = self._get_suggestions_widget()
        if suggestions:
            suggestions.add_class("visible")
            self._suggestions_visible = True

    def _hide_suggestions(self) -> None:
        """Hide the suggestions dropdown."""
        suggestions = self._get_suggestions_widget()
        if suggestions:
            suggestions.remove_class("visible")
            self._suggestions_visible = False

    def _update_suggestions(self) -> None:
        """Update suggestions based on current input."""
        text = self.text.strip()
        suggestions = self._get_suggestions_widget()
        if not suggestions:
            return

        # Check if input starts with / and is a single line (command mode)
        if text.startswith("/") and "\n" not in text:
            has_matches = suggestions.update_suggestions(text)
            if has_matches:
                self._show_suggestions()
            else:
                self._hide_suggestions()
        else:
            self._hide_suggestions()

    def _complete_with_suggestion(self) -> bool:
        """Complete the input with the selected suggestion. Returns True if completed."""
        suggestions = self._get_suggestions_widget()
        if suggestions and self._suggestions_visible:
            cmd = suggestions.get_selected_command()
            if cmd:
                self.text = cmd
                # Move cursor to end of line
                self.action_cursor_line_end()
                self._hide_suggestions()
                return True
        return False

    def complete_with_command(self, command: str) -> None:
        """Complete the input with a specific command (used for click handling)."""
        self.text = command
        self.action_cursor_line_end()
        self._hide_suggestions()
        self.focus()

    async def _on_key(self, event) -> None:
        """Handle key events, intercepting Enter for submission."""
        # Handle suggestions navigation when visible
        if self._suggestions_visible:
            suggestions = self._get_suggestions_widget()
            if suggestions:
                if event.key == "down":
                    # Move to next suggestion
                    if suggestions.highlighted is not None:
                        next_idx = (suggestions.highlighted + 1) % suggestions.option_count
                        suggestions.highlighted = next_idx
                    event.prevent_default()
                    event.stop()
                    return
                elif event.key == "up":
                    # Move to previous suggestion
                    if suggestions.highlighted is not None:
                        prev_idx = (suggestions.highlighted - 1) % suggestions.option_count
                        suggestions.highlighted = prev_idx
                    event.prevent_default()
                    event.stop()
                    return
                elif event.key == "tab":
                    # Complete with selected suggestion
                    if self._complete_with_suggestion():
                        event.prevent_default()
                        event.stop()
                        return
                elif event.key == "escape":
                    # Hide suggestions
                    self._hide_suggestions()
                    event.prevent_default()
                    event.stop()
                    return

        # History navigation (only when suggestions not visible)
        if event.key == "up" and self._history:
            # Save draft if starting to navigate
            if self._history_index == -1:
                self._draft = self.text
            # Move back in history
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.text = self._history[-(self._history_index + 1)]
                self.action_cursor_line_end()
            event.prevent_default()
            event.stop()
            return
        elif event.key == "down" and self._history_index >= 0:
            if self._history_index > 0:
                # Move forward in history
                self._history_index -= 1
                self.text = self._history[-(self._history_index + 1)]
                self.action_cursor_line_end()
            else:
                # Return to draft
                self._history_index = -1
                self.text = self._draft
                self.action_cursor_line_end()
            event.prevent_default()
            event.stop()
            return

        # Reset history navigation on any other key
        if self._history_index != -1:
            self._history_index = -1
            self._draft = ""

        # Ctrl+J inserts newline (Ctrl+Enter sends ctrl+j in most terminals)
        if event.key == "ctrl+j":
            self.insert("\n")
            event.prevent_default()
            event.stop()
            return
        # Plain enter: complete suggestion if visible and submit
        if event.key == "enter":
            # If suggestions visible, complete with selection first
            if self._suggestions_visible:
                self._complete_with_suggestion()
            # Then submit
            value = self.text.strip()
            if value and not self._is_locked:
                # Add to history (avoid duplicates of last entry)
                if not self._history or self._history[-1] != value:
                    self._history.append(value)
                # Reset history navigation
                self._history_index = -1
                self._draft = ""
                self.clear()
                self._hide_suggestions()
                self.post_message(self.Submitted(self, value))
            event.prevent_default()
            event.stop()
            return
        # Let parent handle all other keys
        await super()._on_key(event)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """React to text changes to update suggestions."""
        self._update_suggestions()

    def _on_paste(self, event) -> None:
        """Intercept paste to handle image file paths."""
        if event.text:
            text = event.text.strip()
            # Check if it's an image file path - if so, let the app handle it
            if is_image_path(text):
                image_data = load_image_from_path(text)
                if image_data:
                    self.app._add_image(image_data)
                else:
                    self.app.notify(f"Failed to load image: {text}", severity="error")
                event.stop()
                event.prevent_default()
                return
        # For non-image text, let parent handle it


class SDRBotTUI(App[None]):
    """SDRbot Textual application."""

    CSS_PATH = ["sdrbot.css", "setup_common.tcss"]
    LAYERS = ["below", "overlay"]

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
        Binding("ctrl+c", "interrupt_agent", "Interrupt", priority=True),
    ]

    # Add paste binding for Windows/Linux (Ctrl+Shift+V)
    # macOS uses Cmd+V which triggers a Paste event handled by _on_paste
    if sys.platform != "darwin":
        BINDINGS.insert(3, ("ctrl+shift+v", "paste", "Paste"))

    def __init__(self, session_state: SessionState, assistant_id: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.session_state = session_state
        self.assistant_id = assistant_id
        self.agent_worker: AgentWorker | None = None
        self.image_tracker = ImageTracker()  # Track pasted images for multimodal messages

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
            with VerticalScroll(id="task_list_container"):
                yield Static("", id="task_list_display")
        yield ApprovalBar(id="approval_bar")
        yield ThinkingIndicator(id="thinking_indicator")
        yield CommandSuggestions(id="command_suggestions")
        yield ImageAttachmentBar(id="image_attachment_bar")
        yield ChatInput(id="main_input")
        yield AppFooter()

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

    def _update_image_attachment_bar(self) -> None:
        """Update the image attachment bar with current image count."""
        try:
            bar = self.query_one("#image_attachment_bar", ImageAttachmentBar)
            bar.set_count(len(self.image_tracker.images))
        except Exception:
            pass

    def _add_image(self, image_data) -> None:
        """Add an image to the tracker and update the UI."""
        self.image_tracker.add_image(image_data)
        self._update_image_attachment_bar()

    def action_paste(self) -> None:
        """Paste from system clipboard into focused input.

        Checks for images first (for multimodal support), then falls back to text.
        """
        focused = self.focused
        if focused is None or not hasattr(focused, "insert"):
            return

        # Try to get an image from clipboard first
        try:
            image_data = get_clipboard_image()
            if image_data:
                self._add_image(image_data)
                return
        except Exception:
            pass  # Fall through to text paste

        # Fall back to text paste
        try:
            import pyperclip

            text = pyperclip.paste()
            if text:
                text = text.strip()
                # Check if it's an image file path
                if is_image_path(text):
                    image_data = load_image_from_path(text)
                    if image_data:
                        self._add_image(image_data)
                    else:
                        self.notify(f"Failed to load image: {text}", severity="error")
                    return  # Don't insert path as text
                # Regular text paste
                focused.insert(text)
        except Exception:
            # Silently fail if clipboard is unavailable
            pass

    async def on_mount(self) -> None:
        """Called when app is mounted."""
        self.query_one("#main_input", ChatInput).focus()

        # Check for updates after a delay (non-blocking)
        self.set_timer(2.0, self._check_for_updates_sync)

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
        # Always update model display to reflect any changes
        self._update_model_display()

        # Check if agent already exists (e.g., from /setup command when model was already configured)
        if self.session_state.agent is not None:
            # Agent exists, just reload it to pick up any changes
            self.run_worker(self._reload_existing_agent(), exclusive=True)
        else:
            # First-time setup, need to initialize everything
            self.run_worker(self._initialize_after_setup(), exclusive=True)

    def _check_for_updates_sync(self) -> None:
        """Check for updates and update the version indicator."""
        from sdrbot_cli.updates import check_for_updates

        try:
            latest_version, release_url = check_for_updates()
            if latest_version:
                indicator = self.query_one("#version_indicator", VersionIndicator)
                indicator.set_update_available(latest_version, release_url)
        except Exception:
            pass  # Silently ignore update check failures

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

            # Initialize model
            loading.update_message("Initializing model...")
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
                    session_state=self.session_state,
                )

            loading.update_message("Initializing agent...")
            (
                agent,
                composite_backend,
                tool_count,
                skill_count,
                checkpointer,
                baseline_tokens,
            ) = await loop.run_in_executor(None, create_agent)
            self.session_state.agent = agent
            self.session_state.backend = composite_backend
            self.session_state.checkpointer = checkpointer
            self.session_state.tool_count = tool_count
            self.session_state.skill_count = skill_count
            self.session_state.baseline_tokens = baseline_tokens

            # Set up reload callback
            async def reload_agent():
                from pathlib import Path

                import dotenv

                from sdrbot_cli.config import create_model as create_fresh_model
                from sdrbot_cli.config import settings as app_settings

                # Reload environment to pick up any config changes
                dotenv.load_dotenv(Path.cwd() / ".env", override=True)
                app_settings.reload()

                _, new_failed = await reinitialize_mcp()
                # Re-create model from current config (don't use stale closure)
                fresh_model = await loop.run_in_executor(None, create_fresh_model)
                tools = [http_request, fetch_url]
                # Pass existing checkpointer to preserve conversation history
                new_agent, new_backend, new_tool_count, new_skill_count, _, new_baseline = (
                    create_agent_with_config(
                        fresh_model,
                        self.assistant_id,
                        tools,
                        sandbox=sandbox_backend,
                        sandbox_type=sandbox_type,
                        checkpointer=self.session_state.checkpointer,
                        session_state=self.session_state,
                    )
                )
                self.session_state.agent = new_agent
                self.session_state.backend = new_backend
                self.session_state.tool_count = new_tool_count
                self.session_state.skill_count = new_skill_count
                self.session_state.baseline_tokens = new_baseline
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

            # Initialize model (run in executor as it might be slow)
            loading.update_message("Initializing model...")
            model = await loop.run_in_executor(None, create_model)

            # Now we need to create the agent
            from sdrbot_cli.agent import create_agent_with_config
            from sdrbot_cli.tools import fetch_url, http_request

            def create_agent():
                tools = [http_request, fetch_url]
                return create_agent_with_config(
                    model,
                    self.assistant_id,
                    tools,
                    sandbox=None,
                    sandbox_type=None,
                    session_state=self.session_state,
                )

            # Initialize agent in thread pool
            loading.update_message("Initializing agent...")
            (
                agent,
                composite_backend,
                tool_count,
                skill_count,
                checkpointer,
                baseline_tokens,
            ) = await loop.run_in_executor(None, create_agent)
            self.session_state.agent = agent
            self.session_state.backend = composite_backend
            self.session_state.checkpointer = checkpointer
            self.session_state.tool_count = tool_count
            self.session_state.skill_count = skill_count
            self.session_state.baseline_tokens = baseline_tokens

            # Set up reload callback
            async def reload_agent():
                from pathlib import Path

                import dotenv

                from sdrbot_cli.config import create_model as create_fresh_model
                from sdrbot_cli.config import settings as app_settings

                # Reload environment to pick up any config changes
                dotenv.load_dotenv(Path.cwd() / ".env", override=True)
                app_settings.reload()

                _, new_failed = await reinitialize_mcp()
                # Re-create model from current config (don't use stale closure)
                fresh_model = await loop.run_in_executor(None, create_fresh_model)
                tools = [http_request, fetch_url]
                # Pass existing checkpointer to preserve conversation history
                new_agent, new_backend, new_tool_count, new_skill_count, _, new_baseline = (
                    create_agent_with_config(
                        fresh_model,
                        self.assistant_id,
                        tools,
                        sandbox=None,
                        sandbox_type=None,
                        checkpointer=self.session_state.checkpointer,
                        session_state=self.session_state,
                    )
                )
                self.session_state.agent = new_agent
                self.session_state.backend = new_backend
                self.session_state.tool_count = new_tool_count
                self.session_state.skill_count = new_skill_count
                self.session_state.baseline_tokens = new_baseline
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

        # Update model display
        self._update_model_display()

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

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle click on command suggestion."""
        # Only handle events from our command suggestions widget
        if event.option_list.id == "command_suggestions":
            command = f"/{event.option.id}"
            chat_input = self.query_one("#main_input", ChatInput)
            chat_input.complete_with_command(command)

    async def on_agent_message(self, message: AgentMessage) -> None:
        """Handle messages from the agent worker."""
        chat_log = self.query_one("#chat_log", RichLog)
        chat_log.write(message.renderable)

    async def on_agent_exit(self, message: AgentExit) -> None:
        """Handle agent exit message."""
        self.exit()

    async def on_task_list_update(self, message: TaskListUpdate) -> None:
        """Handle task list updates from the agent worker."""
        task_list_container = self.query_one("#task_list_container", VerticalScroll)
        task_list_display = self.query_one("#task_list_display", Static)
        app_grid = self.query_one("#app_grid", Container)
        content = render_todo_list(message.todos)
        if content and message.todos:
            task_list_display.update(content)
            task_list_container.border_title = "Action Plan"
            task_list_container.add_class("visible")
            app_grid.add_class("has-tasks")
        else:
            task_list_container.remove_class("visible")
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

    def on_status_display_model_clicked(self, message: StatusDisplay.ModelClicked) -> None:
        """Handle click on model - show models screen."""
        from sdrbot_cli.tui.setup_screens import ModelsSetupScreen

        self.push_screen(
            ModelsSetupScreen(),
            self._on_models_screen_closed,
        )

    def on_version_indicator_update_clicked(self, message: VersionIndicator.UpdateClicked) -> None:
        """Handle click on update available - show update modal."""
        from sdrbot_cli.tui.update_screen import UpdateModal

        self.push_screen(UpdateModal(message.latest_version, message.release_url))

    def on_image_attachment_bar_clear_images(self, message: ImageAttachmentBar.ClearImages) -> None:
        """Handle click on clear images button."""
        self.image_tracker.clear()
        self._update_image_attachment_bar()

    def _on_models_screen_closed(self, result: bool | None = None) -> None:
        """Called when models screen is dismissed - reload agent if model changed."""
        from sdrbot_cli.config import load_model_config

        # Check if model actually changed
        model_config = load_model_config()
        new_model = model_config.get("model_name", "Unknown") if model_config else "Unknown"
        current_model = self.query_one("#status_display", StatusDisplay).model_name

        if new_model != current_model:
            # Model was changed, reload agent
            self.run_worker(self._reload_existing_agent(), exclusive=True)

        # Always update display to reflect current config
        self._update_model_display()

    def _update_model_display(self) -> None:
        """Update the model name in the status display."""
        try:
            from sdrbot_cli.config import load_model_config
            from sdrbot_cli.tui.setup_screens import get_model_display_name

            model_config = load_model_config()
            if model_config:
                provider = model_config.get("provider", "")
                model_id = model_config.get("model_name", "Unknown")
                display_name = get_model_display_name(provider, model_id)
                self.query_one("#status_display", StatusDisplay).set_model(
                    display_name or model_id or "Unknown"
                )
        except Exception:
            # Widget may not exist yet during first-time setup, retry after mount
            self.call_later(self._update_model_display)

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

    async def on_image_count_update(self, message: ImageCountUpdate) -> None:
        """Handle image count updates from agent worker."""
        try:
            bar = self.query_one("#image_attachment_bar", ImageAttachmentBar)
            bar.set_count(message.count)
        except Exception:
            pass

    async def on_tool_approval_request(self, message: ToolApprovalRequest) -> None:
        """Handle tool approval request."""
        # Hide thinking indicator, set status to Idle, show approval bar
        self.query_one("#thinking_indicator", ThinkingIndicator).hide()
        self.query_one("#status_display", StatusDisplay).set_status("Idle")
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
