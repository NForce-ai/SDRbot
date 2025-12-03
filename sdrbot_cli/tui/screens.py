"""Textual screens for SDRbot."""

from rich.console import RenderableType
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ToolApprovalModal(ModalScreen[str]):
    """Modal screen for approving tool actions."""

    def __init__(
        self,
        content: RenderableType,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name, id, classes)
        self.content = content

    def compose(self) -> ComposeResult:
        with Container(id="approval_dialog"):
            yield Static(self.content, id="approval_content")
            with Horizontal(id="approval_buttons"):
                yield Button("Approve", variant="success", id="btn_approve")
                yield Button("Reject", variant="error", id="btn_reject")
                yield Button("Auto-Approve All", variant="primary", id="btn_auto_approve")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_approve":
            self.dismiss("approve")
        elif event.button.id == "btn_reject":
            self.dismiss("reject")
        elif event.button.id == "btn_auto_approve":
            self.dismiss("auto_approve_all")
