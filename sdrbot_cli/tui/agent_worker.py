"""Agent worker for Textual application."""

import asyncio
import random
import re
from typing import TYPE_CHECKING

from rich.console import RenderableType
from rich.text import Text
from textual.worker import Worker

from sdrbot_cli.commands import handle_command
from sdrbot_cli.config import COLORS, DEEP_AGENTS_ASCII, SessionState
from sdrbot_cli.execution import execute_task
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
from sdrbot_cli.ui import TokenTracker
from sdrbot_cli.version import __version__

if TYPE_CHECKING:
    from sdrbot_cli.tui.app import SDRBotTUI

# Matches slash commands like /help, /models, /sync hubspot
# Does NOT match file paths like /home/user/image.png
SLASH_COMMAND_RE = re.compile(r"^/([a-z]+)(\s+.*)?$")


class AgentWorker(Worker):
    """Runs the agent's main loop in a background thread."""

    def __init__(self, app: "SDRBotTUI", session_state: SessionState, assistant_id: str) -> None:
        super().__init__(app, "_run_agent_loop", name="AgentWorker")
        self.app = app
        self.session_state = session_state
        self.assistant_id = assistant_id
        self.token_tracker = TokenTracker()
        self.last_output_renderables: list[RenderableType] = []

    def _send_message_to_app(self, renderable: RenderableType) -> None:
        """Send a renderable message to the Textual app's chat log."""
        self.app.post_message(AgentMessage(renderable))

    def _send_tool_count(self) -> None:
        """Send the current tool count to the app."""
        self.app.post_message(ToolCountUpdate(self.session_state.tool_count))

    def _send_skill_count(self) -> None:
        """Send the current skill count to the app."""
        self.app.post_message(SkillCountUpdate(self.session_state.skill_count))

    def _send_counts(self) -> None:
        """Send both tool and skill counts to the app."""
        self._send_tool_count()
        self._send_skill_count()

    def _on_setup_screen_closed(self, result: bool | None = None) -> None:
        """Called when a setup screen is dismissed. Reloads the agent."""
        # Update model display to reflect any changes
        self.app._update_model_display()
        # Run reload in a worker to avoid blocking the UI
        self.app.run_worker(self._reload_agent_async(), exclusive=True)

    def _on_agents_screen_closed(self, result: dict | None = None) -> None:
        """Called when the agents screen is dismissed. Reloads if needed."""
        if result:
            # Check if agent was switched
            switched_to = result.get("switched_to")
            if switched_to:
                # Update the assistant_id in both worker and app
                self.assistant_id = switched_to
                self.app.assistant_id = switched_to
                # Update AgentInfo widget to show new agent name
                from sdrbot_cli.tui.widgets import AgentInfo

                agent_info = self.app.query_one("#agent_info", AgentInfo)
                agent_info.agent_name = "default" if switched_to in (None, "agent") else switched_to

            # Reload if needed
            if result.get("reload") or switched_to:
                self.app.run_worker(self._reload_agent_async(), exclusive=True)

    async def _reload_agent_async(self) -> None:
        """Reload the agent asynchronously."""
        from sdrbot_cli.tui.loading_screen import LoadingScreen

        if self.session_state._reload_callback:
            # Show loading screen
            loading = LoadingScreen(title="Reloading", message="Updating agent...")
            self.app.push_screen(loading)

            try:
                failed_servers = await self.session_state._reload_callback()
                self._send_counts()
                # Notify about failed MCP servers
                if failed_servers:
                    servers_list = ", ".join(failed_servers)
                    self.app.notify(
                        f"Failed to connect to MCP server(s): {servers_list}",
                        severity="warning",
                    )
            except Exception as e:
                self.app.notify(f"Error reloading agent: {e}", severity="error")
            finally:
                self.app.pop_screen()

    async def _run_sync_command(self, user_input: str) -> None:
        """Run the /sync command."""
        from sdrbot_cli.services import SYNCABLE_SERVICES, resync_service
        from sdrbot_cli.services.registry import load_config
        from sdrbot_cli.tui.loading_screen import LoadingScreen

        # Parse command arguments
        parts = user_input.strip().split()
        service_arg = parts[1] if len(parts) > 1 else None

        # Validate service arg first (before showing loading screen)
        if service_arg and service_arg not in SYNCABLE_SERVICES:
            self._send_message_to_app(
                Text(f"Service '{service_arg}' does not support syncing.", style="red")
            )
            self._send_message_to_app(
                Text(f"Syncable services: {', '.join(SYNCABLE_SERVICES)}", style="dim")
            )
            self.app.post_message(StatusUpdate("Idle"))
            return

        # Show loading screen
        loading = LoadingScreen(title="Syncing", message="Preparing...")
        self.app.push_screen(loading)

        loop = asyncio.get_event_loop()

        try:
            if service_arg:
                # Sync specific service
                loading.update_message(f"Syncing {service_arg}...")
                await loop.run_in_executor(None, resync_service, service_arg, False)
            else:
                # Sync all enabled syncable services
                config = load_config()
                synced_any = False

                for service in SYNCABLE_SERVICES:
                    if config.is_enabled(service):
                        loading.update_message(f"Syncing {service}...")
                        await loop.run_in_executor(None, resync_service, service, False)
                        synced_any = True

                if not synced_any:
                    loading.update_message("No services to sync")

            # Reload agent to pick up newly generated tools
            if self.session_state._reload_callback:
                loading.update_message("Reloading agent...")
                await self.session_state._reload_callback()

        finally:
            # Dismiss loading screen and update counts
            self.app.pop_screen()
            self._send_counts()
            self.app.post_message(StatusUpdate("Idle"))

    def _send_command_result_to_app(
        self, result: str | RenderableType | list[RenderableType]
    ) -> None:
        """Send a command result to the Textual app."""
        if isinstance(result, str):
            self.app.post_message(AgentMessage(Text(result, style=COLORS["command"])))
        elif isinstance(result, RenderableType):
            self.app.post_message(AgentMessage(result))
        elif isinstance(result, list):
            for renderable in result:
                self.app.post_message(AgentMessage(renderable))

    async def _request_tool_approval(self) -> str:
        """Request tool approval from the user via the TUI."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.app.post_message(ToolApprovalRequest(future))
        return await future

    async def _run_agent_loop(self, failed_mcp_servers: list[str] | None = None) -> None:
        """The main agent loop, adapted for a Textual worker."""
        if self.is_cancelled:
            return

        # Initial splash and greetings (adapted from simple_cli)
        if not self.session_state.no_splash:
            version_display = f"v{__version__}"
            visible_length = len(version_display) + 2
            ascii_width = 51
            padding = (ascii_width - visible_length) // 2
            centered_version = " " * padding + f"[{version_display}]"

            self._send_message_to_app(
                Text(
                    DEEP_AGENTS_ASCII.replace("[VERSION_PLACEHOLDER]", centered_version),
                    style=f"bold {COLORS['primary']}",
                )
            )

        greetings = [
            "RevOps agent standing by. What's the mission?",
            "Quotas don't hit themselves. Shall we begin?",
            "Ready to hunt. Who are we targeting today?",
            "Pipeline awaiting updates. How can I help?",
        ]
        self._send_message_to_app(Text(random.choice(greetings), style=COLORS["agent"]))
        self._send_message_to_app(Text(""))

        # Display warning about failed MCP servers
        if failed_mcp_servers:
            servers_list = ", ".join(failed_mcp_servers)
            self._send_message_to_app(
                Text.from_markup(
                    f"[bold red]Warning:[/bold red] [yellow]Failed to connect to MCP server(s): {servers_list}[/yellow]"
                )
            )
            self._send_message_to_app(
                Text.from_markup(
                    "[dim]These servers have been disabled. Use /mcp to reconfigure.[/dim]"
                )
            )
            self._send_message_to_app(Text(""))

        tips = "/help to view the user guide"
        self._send_message_to_app(Text(tips, style=COLORS["dim"]))
        self._send_message_to_app(Text(""))

        # Send initial tool and skill counts
        self._send_counts()

        # Set up post-reload callback to update counts after agent reload
        self.session_state.set_post_reload_callback(self._send_counts)

    async def process_user_input(self, user_input: str) -> None:
        """Process user input received from the app."""
        user_input = user_input.strip()

        if not user_input:
            self.app.post_message(StatusUpdate("Idle"))
            return

        try:
            # Check for slash commands first (but not file paths)
            if SLASH_COMMAND_RE.match(user_input):
                if user_input == "/help":
                    from sdrbot_cli.tui.help_screen import HelpScreen

                    self.app.push_screen(HelpScreen())
                    return
                elif user_input == "/tokens":
                    results = self.token_tracker.display_session()
                    self._send_command_result_to_app(results)
                    return
                elif user_input == "/tools":
                    from sdrbot_cli.tui.tools_screen import ToolsScreen

                    self.app.push_screen(ToolsScreen())
                    return
                elif user_input == "/models":
                    # Open models setup screen
                    from sdrbot_cli.tui.setup_screens import ModelsSetupScreen

                    self.app.push_screen(ModelsSetupScreen(), self._on_setup_screen_closed)
                    return
                elif user_input == "/services":
                    # Open services setup screen
                    from sdrbot_cli.tui.services_screens import ServicesSetupScreen

                    self.app.push_screen(ServicesSetupScreen(), self._on_setup_screen_closed)
                    return
                elif user_input == "/mcp":
                    # Open MCP setup screen
                    from sdrbot_cli.tui.mcp_screens import MCPSetupScreen

                    self.app.push_screen(MCPSetupScreen(), self._on_setup_screen_closed)
                    return
                elif user_input == "/setup":
                    # Open setup wizard screen
                    from sdrbot_cli.tui.setup_wizard_screen import SetupWizardScreen

                    self.app.push_screen(SetupWizardScreen(), self._on_setup_screen_closed)
                    return
                elif user_input == "/tracing":
                    # Open tracing setup screen
                    from sdrbot_cli.tui.tracing_screens import TracingSetupScreen

                    self.app.push_screen(TracingSetupScreen(), self._on_setup_screen_closed)
                    return
                elif user_input == "/sync" or user_input.startswith("/sync "):
                    # Sync services - run as worker to avoid blocking
                    self.app.run_worker(self._run_sync_command(user_input), exclusive=True)
                    return
                elif user_input == "/agents":
                    # Open agents management screen
                    from sdrbot_cli.tui.agents_screen import AgentsManagementScreen

                    self.app.push_screen(
                        AgentsManagementScreen(active_agent=self.assistant_id),
                        self._on_agents_screen_closed,
                    )
                    return
                elif user_input == "/skills":
                    # Open skills management screen
                    from sdrbot_cli.tui.skills_screen import SkillsManagementScreen

                    self.app.push_screen(
                        SkillsManagementScreen(),
                        self._on_setup_screen_closed,
                    )
                    return
                else:
                    result = await handle_command(
                        user_input, self.session_state, self.token_tracker
                    )
                    if result == "exit":
                        self.app.post_message(AgentExit())
                        return
                    if result:
                        # Check if it's an unknown command (returns list with "Unknown command" text)
                        if isinstance(result, list) and len(result) > 0:
                            first_item = result[0]
                            if (
                                hasattr(first_item, "plain")
                                and "Unknown command" in first_item.plain
                            ):
                                cmd = user_input.split()[0] if user_input else user_input
                                self.app.notify(
                                    f"Unknown command {cmd}.\nCheck /help for available commands.",
                                    severity="warning",
                                )
                                return
                        self._send_command_result_to_app(result)
                        return

            if user_input.startswith("!"):
                self._send_message_to_app(
                    Text("Bash commands (!) are not yet supported in the TUI.", style="red")
                )
                return

            if user_input.lower() in ["quit", "exit", "q"]:
                self.app.post_message(AgentExit())
                return

            # Get any attached images and clear tracker
            images = None
            if hasattr(self.app, "image_tracker") and self.app.image_tracker.has_images():
                images = self.app.image_tracker.get_images()
                self.app.image_tracker.clear()
                self.app.post_message(ImageCountUpdate(0))  # Update UI

            # Execute agent task
            await execute_task(
                user_input,
                self.session_state.agent,
                self.assistant_id,
                self.session_state,
                self.token_tracker,
                backend=self.session_state.backend,
                ui_callback=self._send_message_to_app,
                todo_callback=lambda todos: self.app.post_message(TaskListUpdate(todos)),
                approval_callback=self._request_tool_approval,
                auto_approve_callback=lambda enabled: self.app.post_message(
                    AutoApproveUpdate(enabled)
                ),
                token_callback=lambda total: self.app.post_message(TokenUpdate(total)),
                # Simplify status to just "Thinking" - detailed tool info is too verbose
                status_callback=lambda _: self.app.post_message(StatusUpdate("Thinking")),
                images=images,
            )
        finally:
            self.app.post_message(StatusUpdate("Idle"))
