"""Context usage modal screen for Textual TUI."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, ProgressBar, Static

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"

# Default summarization settings
DEFAULT_TRIGGER_FRACTION = 0.85
DEFAULT_KEEP_FRACTION = 0.10
FALLBACK_TRIGGER_TOKENS = 170_000
FALLBACK_KEEP_MESSAGES = 6


def _parse_trigger_fraction(value: str | None) -> float:
    """Parse trigger value from settings, returns fraction 0-1."""
    if value is None:
        return DEFAULT_TRIGGER_FRACTION
    try:
        num = float(value)
        if 0 < num <= 1:
            return num
        # If > 1, it's a token count - can't convert to fraction without max_tokens
        return DEFAULT_TRIGGER_FRACTION
    except ValueError:
        return DEFAULT_TRIGGER_FRACTION


class ContextScreen(ModalScreen[None]):
    """Modal screen displaying context usage and summarization status."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ContextScreen {
        align: center middle;
    }

    #context-container {
        width: 50;
        height: auto;
    }

    .context-label {
        color: $text-muted;
        height: 1;
    }

    .context-value {
        text-style: bold;
        height: 1;
    }

    #context-bar {
        height: 1;
        width: 100%;
        margin: 1 0;
    }

    #context-bar Bar {
        width: 1fr;
    }

    .context-status {
        height: 1;
    }

    .status-green {
        color: $success;
    }

    .status-yellow {
        color: $warning;
    }

    .status-red {
        color: $error;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(
        self,
        current_tokens: int,
        model_max_tokens: int | None,
        trigger_setting: str | None = None,
    ) -> None:
        super().__init__()
        self.current_tokens = current_tokens
        self.model_max_tokens = model_max_tokens
        self.trigger_setting = trigger_setting

    def compose(self) -> ComposeResult:
        current = self.current_tokens
        max_tokens = self.model_max_tokens
        trigger_fraction = _parse_trigger_fraction(self.trigger_setting)

        with Container(id="context-container", classes="setup-dialog"):
            yield Static("Context Usage", classes="setup-title")

            yield Static(f"Current: {current:,} tokens", classes="context-value")

            if max_tokens:
                # Check if trigger_setting is an absolute token count
                trigger_at = int(max_tokens * trigger_fraction)
                if self.trigger_setting:
                    try:
                        num = float(self.trigger_setting)
                        if num > 1:
                            # Absolute token count
                            trigger_at = int(num)
                            trigger_pct = int((trigger_at / max_tokens) * 100)
                        else:
                            trigger_pct = int(trigger_fraction * 100)
                    except ValueError:
                        trigger_pct = int(trigger_fraction * 100)
                else:
                    trigger_pct = int(trigger_fraction * 100)

                keep_tokens = int(max_tokens * DEFAULT_KEEP_FRACTION)
                remaining = max(0, trigger_at - current)
                usage_pct = (current / trigger_at) * 100

                yield Static(f"Model max: {max_tokens:,} tokens", classes="context-label")
                yield Static(
                    f"Summarization at: {trigger_at:,} tokens ({trigger_pct}%)",
                    classes="context-label",
                )

                bar = ProgressBar(total=trigger_at, show_eta=False, id="context-bar")
                bar.advance(current)
                yield bar

                # Status message
                if current >= trigger_at:
                    yield Static(
                        "Summarization will trigger on next message",
                        classes="context-status status-red",
                    )
                elif usage_pct >= 90:
                    yield Static(
                        f"~{remaining:,} tokens until summarization",
                        classes="context-status status-yellow",
                    )
                else:
                    yield Static(
                        f"~{remaining:,} tokens until summarization",
                        classes="context-status status-green",
                    )

                yield Static(
                    f"Keeps ~{keep_tokens:,} tokens (10%) after summarization",
                    classes="context-label",
                )
            else:
                # Check if trigger_setting is an absolute token count
                trigger_at = FALLBACK_TRIGGER_TOKENS
                if self.trigger_setting:
                    try:
                        num = float(self.trigger_setting)
                        if num > 1:
                            trigger_at = int(num)
                    except ValueError:
                        pass

                remaining = max(0, trigger_at - current)

                yield Static(
                    f"Summarization at: {trigger_at:,} tokens (fallback)",
                    classes="context-label",
                )

                bar = ProgressBar(total=trigger_at, show_eta=False, id="context-bar")
                bar.advance(current)
                yield bar

                yield Static(
                    f"~{remaining:,} tokens until summarization",
                    classes="context-status status-green",
                )
                yield Static(
                    f"Keeps last {FALLBACK_KEEP_MESSAGES} messages after summarization",
                    classes="context-label",
                )

            with Container(classes="setup-buttons"):
                yield Button("Close", variant="default", id="btn-close", classes="setup-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-close":
            self.dismiss(None)

    def action_close(self) -> None:
        """Close the context screen."""
        self.dismiss(None)
