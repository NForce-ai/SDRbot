"""Custom Textual widgets for SDRbot."""

from rich.text import Text
from textual.events import Click
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
        # Track click regions: list of (start, end, message_type)
        self._click_regions: list[tuple[int, int, str]] = []

    def render(self) -> Text:
        """Render the agent info."""
        self._click_regions = []
        text = Text()

        # Agent name (clickable)
        text.append("Agent: ", style="dim")
        start = len(text)
        text.append(f"{self.agent_name}", style="underline cyan")
        self._click_regions.append((start, len(text), "agent"))

        # Skills count (clickable)
        text.append(" | ", style="dim")
        text.append("Skills: ", style="dim")
        start = len(text)
        text.append(f"{self.skill_count}", style="underline cyan")
        self._click_regions.append((start, len(text), "skills"))

        # Tools count (clickable)
        text.append(" | ", style="dim")
        text.append("Tools: ", style="dim")
        start = len(text)
        text.append(f"{self.tool_count}", style="underline cyan")
        self._click_regions.append((start, len(text), "tools"))

        # Add sandbox indicator (only if enabled)
        if self.sandbox_type:
            text.append(" | ", style="dim")
            text.append("Sandbox: ", style="dim")
            text.append(f"{self.sandbox_type}", style="magenta")

        # Add auto-approve indicator
        if self.auto_approve:
            text.append(" | ", style="dim")
            text.append("Auto: ", style="dim")
            text.append("ON", style="bold yellow")

        return text

    def on_click(self, event: Click) -> None:
        """Handle click on specific regions of the widget."""
        # Get click position relative to the widget content
        click_x = event.x

        for start, end, region_type in self._click_regions:
            if start <= click_x < end:
                if region_type == "agent":
                    self.post_message(self.AgentNameClicked())
                elif region_type == "skills":
                    self.post_message(self.SkillCountClicked())
                elif region_type == "tools":
                    self.post_message(self.ToolCountClicked())
                return

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
    """Widget to display status and token usage with animated spinner."""

    status = reactive("Idle")
    total_tokens = reactive(0)
    _frame_index = reactive(0)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.styles.height = 1
        self.styles.content_align = ("right", "middle")
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
        """Render the status and token display."""
        text = Text()
        text.append("Status: ", style="dim")

        if self.status == "Idle":
            text.append(self.status, style="dim")
        else:
            # Show animated spinner + status in cyan
            spinner = SPINNER_FRAMES[self._frame_index]
            text.append(f"{spinner} ", style="bold cyan")
            text.append(self.status, style="bold #00a2c7")

        text.append(" | ", style="dim")
        text.append(f"Tokens: {self.total_tokens:,}", style="dim")
        return text

    def set_status(self, status: str) -> None:
        """Update the status."""
        self.status = status

    def update_tokens(self, tokens: int) -> None:
        """Update the token count."""
        self.total_tokens = tokens
