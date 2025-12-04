"""Agents management screen for the TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, ListItem, ListView, Static

from sdrbot_cli.config import get_default_coding_instructions, settings

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


class AgentsManagementScreen(ModalScreen[dict | None]):
    """Screen for managing agent profiles.

    Returns a dict with:
    - "reload": bool - whether to reload the agent
    - "switched_to": str | None - new agent name if switched
    """

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    AgentsManagementScreen {
        align: center middle;
    }

    #agents-list {
        max-height: 12;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def __init__(self, active_agent: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.active_agent = active_agent
        self._needs_reload = False
        self._switched_to: str | None = None

    def compose(self) -> ComposeResult:
        with Container(id="agents-container", classes="setup-dialog-wide"):
            yield Static("Agent Profiles", classes="setup-title")
            yield Static(
                "Select an agent to edit or switch to.",
                classes="setup-hint",
            )
            yield ListView(id="agents-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate the agents list on mount."""
        self._refresh_list()

    def _get_display_name(self, agent_name: str) -> str:
        """Get the display name for an agent."""
        if agent_name == "agent":
            return "default"
        # Convert underscores back to spaces for display
        return agent_name.replace("_", " ")

    def _refresh_list(self) -> None:
        """Refresh the agents list."""
        list_view = self.query_one("#agents-list", ListView)
        list_view.clear()

        agents_dir = settings.agents_dir
        if not agents_dir.exists():
            agents_dir.mkdir(parents=True, exist_ok=True)

        # Get all agent directories (folders with prompt.md inside)
        agent_dirs = sorted(
            [d for d in agents_dir.iterdir() if d.is_dir() and (d / "prompt.md").exists()]
        )

        for agent_dir in agent_dirs:
            agent_name = agent_dir.name
            display_name = self._get_display_name(agent_name)

            # Determine status
            if agent_name == self.active_agent:
                status_text = "● Active"
                status_class = "status-active"
            else:
                status_text = ""
                status_class = ""

            item = ListItem(
                Horizontal(
                    Static(display_name, classes="setup-list-item-label"),
                    Static(status_text, classes=f"setup-list-item-status {status_class}"),
                    classes="setup-list-item",
                ),
            )
            item.data = {"type": "agent", "name": agent_name}
            list_view.append(item)

        # Add "+ New profile" option at the bottom
        new_item = ListItem(
            Static("+ New profile", classes="setup-list-item-label"),
        )
        new_item.data = {"type": "new"}
        list_view.append(new_item)

        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        data = getattr(event.item, "data", None)
        if not data:
            return

        if data.get("type") == "new":
            self._create_new_agent()
        elif data.get("type") == "agent":
            agent_name = data.get("name")
            is_active = agent_name == self.active_agent
            if is_active:
                # Active agent - go straight to edit
                self._edit_agent(agent_name)
            else:
                # Inactive agent - show actions menu
                self.app.push_screen(
                    AgentActionsScreen(agent_name),
                    self._on_action_complete,
                )

    def _on_action_complete(self, result: dict | None) -> None:
        """Handle action screen result."""
        if result:
            action = result.get("action")
            agent_name = result.get("agent")

            if action == "edit":
                self._edit_agent(agent_name)
            elif action == "switch":
                self._switch_agent(agent_name)
            elif action == "delete":
                self._delete_agent(agent_name)
        else:
            self._refresh_list()

    def _create_new_agent(self) -> None:
        """Show dialog to create a new agent."""
        self.app.push_screen(
            CreateAgentScreen(),
            self._on_create_complete,
        )

    def _on_create_complete(self, agent_name: str | None) -> None:
        """Handle new agent creation."""
        if agent_name:
            # Create the agent folder with prompt.md and memory.md
            agent_prompt = settings.get_agent_prompt_path(agent_name)
            if not agent_prompt.exists():
                settings.ensure_agent_prompt(agent_name, get_default_coding_instructions())
                settings.ensure_agent_memory(agent_name)
                self._needs_reload = True

            self._refresh_list()
            # Open editor for the new agent
            self._edit_agent(agent_name)

    def _edit_agent(self, agent_name: str) -> None:
        """Open the tabbed editor for an agent's prompt and memory."""
        from sdrbot_cli.tui.agent_editor_screen import AgentEditorScreen

        agent_prompt = settings.get_agent_prompt_path(agent_name)
        agent_memory = settings.get_agent_memory_path(agent_name)
        display_name = self._get_display_name(agent_name)
        self.app.push_screen(
            AgentEditorScreen(
                agent_name=agent_name,
                prompt_path=agent_prompt,
                memory_path=agent_memory,
                title=f"{display_name} agent",
                default_prompt=get_default_coding_instructions(),
            ),
            self._on_edit_complete,
        )

    def _on_edit_complete(self, result: dict | None) -> None:
        """Handle edit completion."""
        if result:
            action = result.get("action")
            if action == "save":
                self._needs_reload = True
                # Build notification message
                changes = []
                if result.get("prompt_changed"):
                    changes.append("prompt")
                if result.get("memory_changed"):
                    changes.append("memory")
                if changes:
                    self.notify(f"Agent {', '.join(changes)} updated.")
                else:
                    self.notify("Agent saved.")
        self._refresh_list()

    def _switch_agent(self, agent_name: str) -> None:
        """Switch to a different agent."""
        if agent_name == self.active_agent:
            return

        self.active_agent = agent_name
        self._switched_to = agent_name
        self._needs_reload = True
        self.notify(f"Switched to agent: {agent_name}")
        self._refresh_list()

    def _delete_agent(self, agent_name: str) -> None:
        """Delete an agent after confirmation."""
        self.app.push_screen(
            ConfirmDeleteScreen("agent", agent_name),
            lambda confirmed: self._on_delete_confirmed(confirmed, agent_name),
        )

    def _on_delete_confirmed(self, confirmed: bool, agent_name: str) -> None:
        """Handle delete confirmation."""
        if confirmed:
            import shutil

            agent_dir = settings.get_agent_dir(agent_name)
            try:
                shutil.rmtree(agent_dir)
                self.notify(f"Deleted agent: {agent_name}")
                self._refresh_list()
            except Exception as e:
                self.notify(f"Error deleting agent: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.action_go_back()

    def action_go_back(self) -> None:
        """Go back to the main screen."""
        if self._needs_reload or self._switched_to:
            self.dismiss(
                {
                    "reload": self._needs_reload,
                    "switched_to": self._switched_to,
                }
            )
        else:
            self.dismiss(None)


class AgentActionsScreen(ModalScreen[dict | None]):
    """Screen showing actions for a selected agent."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    AgentActionsScreen {
        align: center middle;
    }

    #actions-list {
        max-height: 6;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, agent_name: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.agent_name = agent_name
        if agent_name == "agent":
            self.display_name = "default"
        else:
            self.display_name = agent_name.replace("_", " ")

    def compose(self) -> ComposeResult:
        with Container(id="actions-container", classes="setup-dialog"):
            yield Static(self.display_name, classes="setup-title")
            yield ListView(id="actions-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate actions list."""
        list_view = self.query_one("#actions-list", ListView)
        list_view.clear()

        # Build actions list (only shown for non-active agents)
        actions = [
            ("edit", "Edit"),
            ("switch", "Switch to this agent"),
        ]

        # Can't delete default agent
        if self.agent_name != "agent":
            actions.append(("delete", "Delete"))

        for action_id, action_label in actions:
            item = ListItem(Static(action_label))
            item.data = action_id
            list_view.append(item)

        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle action selection."""
        action = getattr(event.item, "data", None)
        if action in ("edit", "switch", "delete"):
            self.dismiss({"action": action, "agent": self.agent_name})

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(None)


class CreateAgentScreen(ModalScreen[str | None]):
    """Dialog for creating a new agent."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    CreateAgentScreen {
        align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="create-container", classes="setup-dialog"):
            yield Static("Create New Agent", classes="setup-title")
            yield Input(placeholder="Agent name (e.g., sales research)", id="create-input")
            with Horizontal(classes="setup-buttons"):
                yield Button("Create", variant="success", id="btn-create", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one("#create-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter key in input."""
        self._create()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-create":
            self._create()
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def _create(self) -> None:
        """Validate and create the agent."""
        import re

        name_input = self.query_one("#create-input", Input)
        display_name = name_input.value.strip()

        if not display_name:
            self.notify("Please enter an agent name.", severity="warning")
            return

        # Validate name - allow alphanumeric, hyphens, underscores, and spaces
        if not re.match(r"^[a-zA-Z0-9_\- ]+$", display_name):
            self.notify(
                "Invalid name. Use only letters, numbers, hyphens, underscores, and spaces.",
                severity="error",
            )
            return

        # Convert spaces to underscores for directory name
        agent_name = display_name.replace(" ", "_")

        # Check if already exists
        agent_dir = settings.get_agent_dir(agent_name)
        if agent_dir.exists():
            self.notify(f"Agent '{display_name}' already exists.", severity="warning")
            return

        self.dismiss(agent_name)

    def action_cancel(self) -> None:
        """Cancel creation."""
        self.dismiss(None)


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Confirmation dialog for deleting an agent or skill."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ConfirmDeleteScreen {
        align: center middle;
    }

    #confirm-message {
        text-align: center;
        padding: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, item_type: str, item_name: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.item_type = item_type
        self.item_name = item_name

    def compose(self) -> ComposeResult:
        with Container(id="confirm-container", classes="setup-dialog"):
            yield Static(f"Delete {self.item_type.title()}", classes="setup-title")
            yield Static(
                f"Delete '{self.item_name}'?\nThis cannot be undone.",
                id="confirm-message",
            )
            with Horizontal(classes="setup-buttons"):
                yield Button("Delete", variant="error", id="btn-delete", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-delete":
            self.dismiss(True)
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        """Cancel deletion."""
        self.dismiss(False)
