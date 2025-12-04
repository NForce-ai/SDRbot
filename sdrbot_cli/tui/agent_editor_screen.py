"""Agent editor screen with tabbed Prompt/Memory editing."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Static, TabbedContent, TabPane, TextArea


class AgentEditorScreen(Screen[dict | None]):
    """Screen for editing an agent's prompt and memory files in tabs.

    Returns a dict with:
    - {"action": "save", "prompt_changed": bool, "memory_changed": bool}
    - None - cancelled
    """

    CSS = """
    AgentEditorScreen {
        align: center middle;
    }

    #editor-container {
        width: 100%;
        height: 100%;
        padding: 1;
    }

    #editor-header {
        height: 1;
        width: 100%;
        margin-bottom: 1;
    }

    #editor-title {
        width: 1fr;
    }

    #editor-status {
        width: auto;
        color: $warning;
    }

    #editor-tabs {
        height: 1fr;
    }

    #editor-tabs TextArea {
        height: 1fr;
        border: heavy $accent;
    }

    #editor-buttons {
        width: 100%;
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    #editor-buttons Button {
        margin: 0 1;
    }

    #editor-hint {
        text-align: center;
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        agent_name: str,
        prompt_path: Path,
        memory_path: Path,
        title: str | None = None,
        default_prompt: str = "",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.agent_name = agent_name
        self.prompt_path = prompt_path
        self.memory_path = memory_path
        self.title_text = title or f"{agent_name} agent"
        self.default_prompt = default_prompt

        self.original_prompt = ""
        self.original_memory = ""
        self._prompt_changed = False
        self._memory_changed = False

    def compose(self) -> ComposeResult:
        with Container(id="editor-container"):
            with Horizontal(id="editor-header"):
                yield Static(self.title_text, id="editor-title")
                yield Static("", id="editor-status")
            with TabbedContent(id="editor-tabs"):
                with TabPane("Prompt", id="tab-prompt"):
                    yield TextArea(id="prompt-textarea")
                with TabPane("Memory", id="tab-memory"):
                    yield TextArea(id="memory-textarea")
            yield Static("Ctrl+S Save • Esc Cancel", id="editor-hint")
            with Horizontal(id="editor-buttons"):
                yield Button("Save", variant="success", id="btn-save")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_mount(self) -> None:
        """Load file contents on mount."""
        prompt_area = self.query_one("#prompt-textarea", TextArea)
        memory_area = self.query_one("#memory-textarea", TextArea)

        # Load prompt content
        if self.prompt_path.exists():
            self.original_prompt = self.prompt_path.read_text()
        else:
            self.original_prompt = self.default_prompt

        # Load memory content (may not exist)
        if self.memory_path.exists():
            self.original_memory = self.memory_path.read_text()
        else:
            self.original_memory = ""

        prompt_area.load_text(self.original_prompt)
        memory_area.load_text(self.original_memory)
        prompt_area.focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Track unsaved changes for both textareas."""
        textarea_id = event.text_area.id
        current_content = event.text_area.text

        if textarea_id == "prompt-textarea":
            self._prompt_changed = current_content != self.original_prompt
        elif textarea_id == "memory-textarea":
            self._memory_changed = current_content != self.original_memory

        self._update_status()

    def _update_status(self) -> None:
        """Update the status indicator."""
        status = self.query_one("#editor-status", Static)
        has_changes = self._prompt_changed or self._memory_changed
        if has_changes:
            parts = []
            if self._prompt_changed:
                parts.append("prompt")
            if self._memory_changed:
                parts.append("memory")
            status.update(f"● Unsaved: {', '.join(parts)}")
        else:
            status.update("")

    @property
    def has_unsaved_changes(self) -> bool:
        """Check if there are any unsaved changes."""
        return self._prompt_changed or self._memory_changed

    def action_save(self) -> None:
        """Save the files and dismiss."""
        self._save_files()

    def action_cancel(self) -> None:
        """Cancel editing, warn if unsaved changes."""
        if self.has_unsaved_changes:
            self.app.push_screen(
                ConfirmDiscardScreen(),
                self._on_confirm_discard,
            )
        else:
            self.dismiss(None)

    def _on_confirm_discard(self, discard: bool) -> None:
        """Handle discard confirmation."""
        if discard:
            self.dismiss(None)

    def _save_files(self) -> None:
        """Save both prompt and memory files."""
        prompt_area = self.query_one("#prompt-textarea", TextArea)
        memory_area = self.query_one("#memory-textarea", TextArea)

        prompt_content = prompt_area.text
        memory_content = memory_area.text

        try:
            # Ensure agent directory exists
            self.prompt_path.parent.mkdir(parents=True, exist_ok=True)

            # Save prompt (always)
            self.prompt_path.write_text(prompt_content)

            # Save memory (only if it has content or already exists)
            if memory_content.strip() or self.memory_path.exists():
                self.memory_path.write_text(memory_content)

            # Track what changed for caller
            result = {
                "action": "save",
                "prompt_changed": self._prompt_changed,
                "memory_changed": self._memory_changed,
            }

            # Update originals
            self.original_prompt = prompt_content
            self.original_memory = memory_content
            self._prompt_changed = False
            self._memory_changed = False

            self.dismiss(result)
        except Exception as e:
            self.notify(f"Error saving files: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_files()
        elif event.button.id == "btn-cancel":
            self.action_cancel()


class ConfirmDiscardScreen(Screen[bool]):
    """Confirmation dialog for discarding unsaved changes."""

    CSS = """
    ConfirmDiscardScreen {
        align: center middle;
    }

    #confirm-container {
        width: 50;
        height: auto;
        border: heavy $warning;
        background: $panel;
        padding: 1 2;
    }

    #confirm-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #confirm-message {
        text-align: center;
        margin-bottom: 1;
    }

    #confirm-buttons {
        width: 100%;
        height: 3;
        align: center middle;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="confirm-container"):
            yield Static("Unsaved Changes", id="confirm-title")
            yield Static(
                "You have unsaved changes. Discard them?",
                id="confirm-message",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button("Discard", variant="error", id="btn-discard")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-discard":
            self.dismiss(True)
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        """Cancel and go back to editing."""
        self.dismiss(False)
