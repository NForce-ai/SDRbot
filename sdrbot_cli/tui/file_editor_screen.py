"""File editor screen for editing text files in the TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Static, TextArea


class FileEditorScreen(Screen[dict | None]):
    """Screen for editing a text file with save/cancel/save-as functionality.

    Returns a dict with:
    - {"action": "save"} - saved to original file
    - {"action": "save_as", "content": "..."} - save as new file requested
    - None - cancelled
    """

    CSS = """
    FileEditorScreen {
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

    #editor-textarea {
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
        file_path: Path,
        title: str | None = None,
        create_if_missing: bool = False,
        default_content: str = "",
        allow_save_as: bool = False,
        read_only: bool = False,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        self.title_text = title or file_path.name
        self.create_if_missing = create_if_missing
        self.default_content = default_content
        self.allow_save_as = allow_save_as
        self.read_only = read_only
        self.original_content = ""
        self._has_unsaved_changes = False

    def compose(self) -> ComposeResult:
        with Container(id="editor-container"):
            with Horizontal(id="editor-header"):
                yield Static(self.title_text, id="editor-title")
                yield Static("", id="editor-status")
            yield TextArea(id="editor-textarea", read_only=self.read_only)
            if self.read_only:
                hint = "Esc Close"
                if self.allow_save_as:
                    hint = "Esc Close • Save As to create your own copy"
            else:
                hint = "Ctrl+S Save • Esc Cancel"
            yield Static(hint, id="editor-hint")
            with Horizontal(id="editor-buttons"):
                if not self.read_only:
                    yield Button("Save", variant="success", id="btn-save")
                if self.allow_save_as:
                    yield Button("Save As", variant="primary", id="btn-save-as")
                yield Button(
                    "Close" if self.read_only else "Cancel", variant="default", id="btn-cancel"
                )

    def on_mount(self) -> None:
        """Load file content on mount."""
        textarea = self.query_one("#editor-textarea", TextArea)

        if self.file_path.exists():
            self.original_content = self.file_path.read_text()
        elif self.create_if_missing:
            self.original_content = self.default_content
        else:
            self.notify(f"File not found: {self.file_path}", severity="error")
            self.dismiss(None)
            return

        textarea.load_text(self.original_content)
        textarea.focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Track unsaved changes."""
        current_content = event.text_area.text
        self._has_unsaved_changes = current_content != self.original_content
        self._update_status()

    def _update_status(self) -> None:
        """Update the status indicator."""
        status = self.query_one("#editor-status", Static)
        if self._has_unsaved_changes:
            status.update("● Unsaved changes")
        else:
            status.update("")

    def action_save(self) -> None:
        """Save the file and dismiss."""
        if not self.read_only:
            self._save_file()

    def action_cancel(self) -> None:
        """Cancel editing, warn if unsaved changes."""
        if self._has_unsaved_changes and not self.read_only:
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

    def _save_file(self) -> None:
        """Save content to file."""
        textarea = self.query_one("#editor-textarea", TextArea)
        content = textarea.text

        try:
            # Ensure parent directory exists
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(content)
            self.original_content = content
            self._has_unsaved_changes = False
            self.dismiss({"action": "save"})
        except Exception as e:
            self.notify(f"Error saving file: {e}", severity="error")

    def _save_as(self) -> None:
        """Return content for save-as operation."""
        textarea = self.query_one("#editor-textarea", TextArea)
        content = textarea.text
        self.dismiss({"action": "save_as", "content": content})

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_file()
        elif event.button.id == "btn-save-as":
            self._save_as()
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
