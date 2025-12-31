"""Custom Textual widgets for SDRbot."""

from collections import defaultdict

import pyperclip
from rich.text import Text
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static
from textual.widgets._footer import Footer, FooterKey

from sdrbot_cli.ui import format_token_count
from sdrbot_cli.version import __version__

# Desired order for footer bindings (by action name)
FOOTER_BINDING_ORDER = [
    "quit",
    "show_help",
    "show_setup",
    "cycle_tool_scope",
    "toggle_auto_approve",
    "interrupt_agent",
    "paste",
    "newline",
]


class OrderedFooter(Footer):
    """Footer that displays bindings in a predefined order."""

    def compose(self):
        """Compose footer with bindings in FOOTER_BINDING_ORDER."""
        if not self._bindings_ready:
            return

        active_bindings = self.screen.active_bindings
        bindings = [
            (binding, enabled, tooltip)
            for (_, binding, enabled, tooltip) in active_bindings.values()
            if binding.show
        ]

        # Group by action
        action_to_bindings: defaultdict[str, list[tuple]] = defaultdict(list)
        for binding, enabled, tooltip in bindings:
            action_to_bindings[binding.action].append((binding, enabled, tooltip))

        # Sort actions by our predefined order
        def sort_key(action: str) -> int:
            try:
                return FOOTER_BINDING_ORDER.index(action)
            except ValueError:
                return len(FOOTER_BINDING_ORDER)  # Unknown actions go last

        sorted_actions = sorted(action_to_bindings.keys(), key=sort_key)

        for action in sorted_actions:
            multi_bindings = action_to_bindings[action]
            binding, enabled, tooltip = multi_bindings[0]
            yield FooterKey(
                binding.key,
                self.app.get_key_display(binding),
                binding.description,
                binding.action,
                disabled=not enabled,
                tooltip=tooltip,
            ).data_bind(compact=Footer.compact)


class CopyableRichLog(RichLog):
    """RichLog that copies content to clipboard on right-click."""

    def on_click(self, event: Click) -> None:
        """Handle click events - right-click copies content to clipboard."""
        if event.button == 3:  # Right-click
            self._copy_to_clipboard()
            event.stop()

    def _copy_to_clipboard(self) -> None:
        """Extract text content and copy to clipboard."""
        # Extract plain text from all lines (Strip objects)
        text_lines = []
        for strip in self.lines:
            # Strip contains Segments, each with text attribute
            line_text = "".join(segment.text for segment in strip._segments)
            text_lines.append(line_text)

        full_text = "\n".join(text_lines)

        try:
            pyperclip.copy(full_text)
            self.app.notify("Chat log copied to clipboard", timeout=2)
        except Exception as e:
            self.app.notify(f"Failed to copy: {e}", severity="error", timeout=3)


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
    """Widget to display agent name, skill count, tool count, scope, auto-approve, and sandbox."""

    agent_name = reactive("default")
    skill_count = reactive(0)
    tool_count = reactive(0)
    tool_scope = reactive("standard")
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

    class ToolScopeClicked(Message):
        """Message emitted when tool scope is clicked."""

        pass

    def __init__(
        self,
        agent_name: str = "default",
        auto_approve: bool = False,
        sandbox_type: str = "",
        tool_scope: str = "standard",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.agent_name = agent_name
        self.auto_approve = auto_approve
        self.sandbox_type = sandbox_type
        self.tool_scope = tool_scope
        self.styles.height = 1

    def render(self) -> Text:
        """Render the agent info."""
        # Format scope for display (capitalize first letter)
        scope_display = self.tool_scope.capitalize()

        # Use @click markup for clickable elements (color set via CSS link-color)
        parts = [
            f"[dim]Agent:[/] [@click=click_agent]{self.agent_name}[/]",
            f"[dim]Skills:[/] [@click=click_skills]{self.skill_count}[/]",
            f"[dim]Tools:[/] [@click=click_tools]{self.tool_count}[/]",
            f"[dim]Scope:[/] [@click=click_scope][yellow]{scope_display}[/yellow][/]",
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

    def action_click_scope(self) -> None:
        """Action triggered when tool scope is clicked."""
        self.post_message(self.ToolScopeClicked())

    def update_skill_count(self, count: int) -> None:
        """Update the skill count."""
        self.skill_count = count

    def update_tool_count(self, count: int) -> None:
        """Update the tool count."""
        self.tool_count = count

    def update_tool_scope(self, scope: str) -> None:
        """Update the tool scope display."""
        self.tool_scope = scope

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

        tokens_part = f"[dim]Tokens: {format_token_count(self.total_tokens)}[/]"
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


class VersionIndicator(Static):
    """Widget to display version and update availability in the footer."""

    DEFAULT_CSS = """
    VersionIndicator {
        dock: right;
        width: auto;
        height: 1;
        padding: 0 1;
        link-color: cyan;
        link-style: bold;
    }
    """

    class UpdateClicked(Message):
        """Message emitted when update link is clicked."""

        def __init__(self, latest_version: str, release_url: str) -> None:
            super().__init__()
            self.latest_version = latest_version
            self.release_url = release_url

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(f"[dim]v{__version__}[/]", *args, **kwargs)
        self._latest_version = ""
        self._release_url = ""

    def action_click_update(self) -> None:
        """Action triggered when update link is clicked."""
        self.post_message(self.UpdateClicked(self._latest_version, self._release_url))

    def set_update_available(self, latest_version: str, release_url: str) -> None:
        """Set update availability."""
        self._latest_version = latest_version
        self._release_url = release_url
        markup = f"[dim]v{__version__}[/] • [@click=click_update][cyan bold]Update (v{latest_version})[/][/]"
        self.update(markup)


class ImageAttachmentBar(Static):
    """Bar showing attached images above the chat input."""

    DEFAULT_CSS = """
    ImageAttachmentBar {
        height: 1;
        width: 100%;
        padding: 0 1;
        display: none;
        background: $primary-background;
        color: $text;
    }

    ImageAttachmentBar.visible {
        display: block;
    }
    """

    image_count = reactive(0)

    class ClearImages(Message):
        """Message emitted when clear button is clicked."""

        pass

    def watch_image_count(self, count: int) -> None:
        """Update display when image count changes."""
        if count > 0:
            self.add_class("visible")
        else:
            self.remove_class("visible")
        self.refresh()

    def render(self) -> Text:
        """Render the attachment bar content."""
        if self.image_count > 0:
            s = "s" if self.image_count > 1 else ""
            # Use visible colors - cyan for icon/text, red for close button
            markup = f"[cyan]📷 {self.image_count} image{s} attached[/] [@click=clear_images][white][[/][bold red]x[/][white]][/][/]"
            return Text.from_markup(markup)
        return Text("")

    def action_clear_images(self) -> None:
        """Action triggered when clear button is clicked."""
        self.post_message(self.ClearImages())

    def set_count(self, count: int) -> None:
        """Update the image count."""
        self.image_count = count


class AppFooter(Widget):
    """Custom footer with version indicator."""

    DEFAULT_CSS = """
    AppFooter {
        dock: bottom;
        height: 1;
        layout: horizontal;
        background: $footer-background;
    }

    AppFooter Footer {
        width: 1fr;
    }
    """

    def compose(self):
        yield OrderedFooter(show_command_palette=False)
        yield VersionIndicator(id="version_indicator")
