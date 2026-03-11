"""TUI screen for listing and resuming past conversation threads."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, ListItem, ListView, Static

from sdrbot_cli.sessions import delete_thread, list_threads

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"


class SessionsScreen(ModalScreen[str | None]):
    """Show a list of past conversation threads.

    Resolves with:
    - A ``thread_id`` string to resume that session.
    - ``"__clear__"`` when the user deleted the currently active session.
    - ``None`` if the user dismissed without acting.
    """

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    SessionsScreen {
        align: center middle;
    }

    #sessions-list {
        max-height: 12;
    }

    .session-meta {
        color: $text-muted;
        width: auto;
        text-align: right;
        min-width: 18;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("delete", "delete_selected", "Delete"),
    ]

    def __init__(self, current_thread_id: str | None = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._current_thread_id = current_thread_id
        self._deleted_current = False

    def compose(self) -> ComposeResult:
        with Container(id="sessions-container", classes="setup-dialog-wide"):
            yield Static("Sessions", classes="setup-title")
            yield Static(
                "Select a conversation to resume.",
                classes="setup-hint",
            )
            yield ListView(id="sessions-list", classes="setup-list")
            yield Static(
                "[dim]Enter: resume  |  Delete: remove  |  Esc: back[/dim]",
                classes="setup-hint",
            )
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        list_view = self.query_one("#sessions-list", ListView)
        list_view.clear()

        threads = list_threads(limit=30)
        if not threads:
            item = ListItem(
                Static("No saved sessions", classes="setup-list-item-label"),
            )
            item.data = {"type": "empty"}
            list_view.append(item)
            list_view.focus()
            return

        for t in threads:
            preview = t.get("preview", "(empty)")
            timestamp = t.get("timestamp", "")
            meta = timestamp[:10] if timestamp else ""

            item = ListItem(
                Horizontal(
                    Static(preview, classes="setup-list-item-label"),
                    Static(meta, classes="session-meta"),
                    classes="setup-list-item",
                ),
            )
            item.data = {"type": "session", "thread_id": t["thread_id"]}
            list_view.append(item)

        list_view.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter resumes the selected session."""
        data = getattr(event.item, "data", None)
        if not data or data.get("type") != "session":
            return
        self.dismiss(data["thread_id"])

    def action_delete_selected(self) -> None:
        """Delete key removes the highlighted session after confirmation."""
        list_view = self.query_one("#sessions-list", ListView)
        if list_view.highlighted_child is None:
            return
        data = getattr(list_view.highlighted_child, "data", None)
        if not data or data.get("type") != "session":
            return

        from sdrbot_cli.tui.agents_screen import ConfirmDeleteScreen

        thread_id = data["thread_id"]
        self.app.push_screen(
            ConfirmDeleteScreen("session", thread_id[:12]),
            lambda confirmed: self._on_delete_confirmed(confirmed, thread_id),
        )

    def _on_delete_confirmed(self, confirmed: bool, thread_id: str) -> None:
        if not confirmed:
            return
        delete_thread(thread_id)
        if thread_id == self._current_thread_id:
            self._deleted_current = True
        self.notify("Session deleted")
        self._refresh_list()

    def _dismiss_with_state(self) -> None:
        """Dismiss, signalling a clear if the active session was deleted."""
        if self._deleted_current:
            self.dismiss("__clear__")
        else:
            self.dismiss(None)

    def action_go_back(self) -> None:
        self._dismiss_with_state()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self._dismiss_with_state()
