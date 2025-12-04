"""Custom Textual widgets for SDRbot."""

from rich.text import Text
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

# Spinner frames for the thinking animation
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class ThinkingIndicator(Widget):
    """Animated thinking indicator that replaces the chat input while agent is processing."""

    DEFAULT_CSS = """
    ThinkingIndicator {
        height: auto;
        min-height: 3;
        max-height: 3;
        margin: 0;
        border: heavy $accent;
        padding: 0 1;
        display: none;
    }

    ThinkingIndicator.visible {
        display: block;
    }

    ThinkingIndicator #thinking-content {
        height: 1;
        width: 100%;
        content-align: left middle;
    }
    """

    status = reactive("Thinking...")
    _frame_index = reactive(0)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._timer = None

    def compose(self):
        yield Static("", id="thinking-content")

    def on_mount(self) -> None:
        """Start the animation timer when mounted."""
        self._timer = self.set_interval(1 / 12, self._advance_frame)

    def _advance_frame(self) -> None:
        """Advance to the next spinner frame."""
        if self.has_class("visible"):
            self._frame_index = (self._frame_index + 1) % len(SPINNER_FRAMES)

    def watch__frame_index(self, frame_index: int) -> None:
        """Update the display when frame changes."""
        self._update_display()

    def watch_status(self, status: str) -> None:
        """Update the display when status changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the thinking content display."""
        try:
            content = self.query_one("#thinking-content", Static)
            spinner = SPINNER_FRAMES[self._frame_index]
            text = Text()
            text.append(f" {spinner} ", style="bold cyan")
            text.append(self.status, style="bold #00a2c7")
            content.update(text)
        except Exception:
            pass

    def show(self, status: str = "Thinking...") -> None:
        """Show the thinking indicator."""
        self.status = status
        self.add_class("visible")

    def hide(self) -> None:
        """Hide the thinking indicator."""
        self.remove_class("visible")

    def update_status(self, status: str) -> None:
        """Update the status message."""
        self.status = status


class AgentInfo(Static):
    """Widget to display agent name, skill count, tool count, auto-approve status, and sandbox."""

    agent_name = reactive("default")
    skill_count = reactive(0)
    tool_count = reactive(0)
    auto_approve = reactive(False)
    sandbox_type = reactive("")

    class AgentNameClicked(Message):
        """Message emitted when agent name is clicked."""

        pass

    class SkillCountClicked(Message):
        """Message emitted when skill count is clicked."""

        pass

    class ToolCountClicked(Message):
        """Message emitted when tool count is clicked."""

        pass

    def __init__(
        self,
        agent_name: str = "default",
        auto_approve: bool = False,
        sandbox_type: str = "",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.agent_name = agent_name
        self.auto_approve = auto_approve
        self.sandbox_type = sandbox_type
        self.styles.height = 1

    def render(self) -> Text:
        """Render the agent info."""
        # Use @click markup for clickable elements (color set via CSS link-color)
        parts = [
            f"[dim]Agent:[/] [@click=click_agent]{self.agent_name}[/]",
            f"[dim]Skills:[/] [@click=click_skills]{self.skill_count}[/]",
            f"[dim]Tools:[/] [@click=click_tools]{self.tool_count}[/]",
        ]

        # Add sandbox indicator (only if enabled)
        if self.sandbox_type:
            parts.append(f"[dim]Sandbox:[/] [magenta]{self.sandbox_type}[/]")

        # Add auto-approve indicator
        if self.auto_approve:
            parts.append("[dim]Auto:[/] [bold yellow]ON[/]")

        markup = " [dim]|[/] ".join(parts)
        return Text.from_markup(markup)

    def action_click_agent(self) -> None:
        """Action triggered when agent name is clicked."""
        self.post_message(self.AgentNameClicked())

    def action_click_skills(self) -> None:
        """Action triggered when skills count is clicked."""
        self.post_message(self.SkillCountClicked())

    def action_click_tools(self) -> None:
        """Action triggered when tools count is clicked."""
        self.post_message(self.ToolCountClicked())

    def update_skill_count(self, count: int) -> None:
        """Update the skill count."""
        self.skill_count = count

    def update_tool_count(self, count: int) -> None:
        """Update the tool count."""
        self.tool_count = count

    def set_auto_approve(self, enabled: bool) -> None:
        """Update the auto-approve status."""
        self.auto_approve = enabled


class StatusDisplay(Static):
    """Widget to display model, token usage, and status with animated spinner."""

    status = reactive("Idle")
    total_tokens = reactive(0)
    model_name = reactive("...")
    _frame_index = reactive(0)

    class ModelClicked(Message):
        """Message emitted when model name is clicked."""

        pass

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.styles.height = 1
        self._timer = None

    def on_mount(self) -> None:
        """Start the animation timer when mounted."""
        self._timer = self.set_interval(1 / 12, self._advance_frame)

    def _advance_frame(self) -> None:
        """Advance to the next spinner frame when not idle."""
        if self.status != "Idle":
            self._frame_index = (self._frame_index + 1) % len(SPINNER_FRAMES)

    def watch__frame_index(self, frame_index: int) -> None:
        """Refresh display when frame changes."""
        self.refresh()

    def render(self) -> Text:
        """Render the status, tokens, and model display."""
        # Status first
        if self.status == "Idle":
            status_part = f"[dim]Status: {self.status}[/]"
        else:
            spinner = SPINNER_FRAMES[self._frame_index]
            status_part = f"[dim]Status:[/] [bold cyan]{spinner}[/] [bold #00a2c7]{self.status}[/]"

        tokens_part = f"[dim]Tokens: {self.total_tokens:,}[/]"
        # Use @click markup for clickable model name (color set via CSS link-color)
        model_part = f"[dim]Model:[/] [@click=show_models]{self.model_name}[/]"

        markup = f"{status_part} [dim]|[/] {tokens_part} [dim]|[/] {model_part}"
        return Text.from_markup(markup)

    def action_show_models(self) -> None:
        """Action triggered when model name is clicked."""
        self.post_message(self.ModelClicked())

    def set_status(self, status: str) -> None:
        """Update the status."""
        self.status = status

    def update_tokens(self, tokens: int) -> None:
        """Update the token count."""
        self.total_tokens = tokens

    def set_model(self, model_name: str) -> None:
        """Update the model name."""
        self.model_name = model_name
        self.refresh()
