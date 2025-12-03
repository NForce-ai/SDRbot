"""Inline approval bar that replaces the input field during tool approval."""

from asyncio import Future

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, Static


class ApprovalBar(Widget):
    """Inline bar that replaces input field for approving tool calls."""

    DEFAULT_CSS = """
    ApprovalBar {
        height: 3;
        margin: 1 0;
        display: none;
    }

    ApprovalBar.visible {
        display: block;
    }

    ApprovalBar #approval-row {
        height: 3;
        width: 100%;
    }

    ApprovalBar #approval-text {
        height: 3;
        width: 34;
        content-align: left middle;
    }
    """

    BINDINGS = [
        ("y", "approve", "Yes"),
        ("n", "reject", "No"),
        ("a", "auto_approve", "Auto"),
        ("escape", "reject", "Reject"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._future: Future[str] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="approval-row"):
            yield Static("", id="approval-text")
            with Horizontal(id="approval-buttons"):
                yield Button("Yes", variant="success", id="btn-yes")
                yield Button("No", variant="error", id="btn-no")
                yield Button("Auto", variant="warning", id="btn-auto")

    def show(self, future: Future[str]) -> None:
        """Show the approval bar."""
        self._future = future

        self.query_one("#approval-text", Static).update("Tool Action Requires Approval:")
        self.add_class("visible")
        # Focus the Yes button
        self.query_one("#btn-yes", Button).focus()

    def hide(self) -> None:
        """Hide the approval bar."""
        self.remove_class("visible")
        self._future = None

    def _resolve(self, result: str) -> None:
        """Resolve the future and hide the bar."""
        if self._future and not self._future.done():
            self._future.set_result(result)
        self.hide()
        # Restore thinking indicator (agent continues processing)
        try:
            thinking_indicator = self.app.query_one("#thinking_indicator")
            thinking_indicator.show("Processing...")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        event.stop()
        if event.button.id == "btn-yes":
            self._resolve("approve")
        elif event.button.id == "btn-no":
            self._resolve("reject")
        elif event.button.id == "btn-auto":
            self._resolve("auto_approve_all")

    def action_approve(self) -> None:
        """Approve the tool call."""
        if self.has_class("visible"):
            self._resolve("approve")

    def action_reject(self) -> None:
        """Reject the tool call."""
        if self.has_class("visible"):
            self._resolve("reject")

    def action_auto_approve(self) -> None:
        """Auto-approve all tool calls."""
        if self.has_class("visible"):
            self._resolve("auto_approve_all")
