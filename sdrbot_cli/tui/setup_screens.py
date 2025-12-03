"""Setup wizard screens for Textual TUI."""

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from sdrbot_cli.config import load_model_config, save_model_config
from sdrbot_cli.setup.env import reload_env_and_settings, save_env_vars

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"

# Model choices per provider
MODEL_CHOICES = {
    "openai": [
        ("gpt-5-mini", "ChatGPT 5 Mini"),
        ("gpt-5", "ChatGPT 5"),
        ("gpt-5.1", "ChatGPT 5.1"),
    ],
    "anthropic": [
        ("claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"),
        ("claude-opus-4-5-20251101", "Claude Opus 4.5"),
    ],
    "google": [
        ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("gemini-3-pro-preview", "Gemini 3 Pro"),
    ],
}

PROVIDERS = [
    ("openai", "OpenAI", "OPENAI_API_KEY"),
    ("anthropic", "Anthropic", "ANTHROPIC_API_KEY"),
    ("google", "Google Gemini", "GOOGLE_API_KEY"),
    ("custom", "Custom (OpenAI-compatible)", None),
]


class ModelsSetupScreen(Screen[bool | None]):
    """Screen for selecting and configuring LLM providers."""

    CSS_PATH = [SETUP_CSS_PATH]

    # Screen-specific overrides only
    CSS = """
    ModelsSetupScreen {
        align: center middle;
    }

    #models-container {
        width: 70;
    }

    #models-list {
        max-height: 8;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="models-container", classes="setup-dialog-wide"):
            yield Static("LLM Provider Setup", classes="setup-title")
            yield ListView(id="models-list", classes="setup-list")
            yield Static("↑↓ Navigate • Enter Select • Esc Back", classes="setup-hint")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate the provider list on mount."""
        self._refresh_provider_list()

    def _refresh_provider_list(self) -> None:
        """Refresh the provider list with current status."""
        list_view = self.query_one("#models-list", ListView)
        list_view.clear()

        current_config = load_model_config()
        active_provider = current_config.get("provider") if current_config else None
        active_model = current_config.get("model_name") if current_config else None

        for provider_code, provider_name, env_var in PROVIDERS:
            # Determine status - must have both provider selected AND model chosen
            has_api_key = bool(env_var and os.getenv(env_var))
            is_active = provider_code == active_provider and active_model

            if is_active:
                status_text = "● Active"
                status_class = "status-active"
            elif has_api_key:
                status_text = "Disabled"
                status_class = "status-configured"
            elif provider_code == "custom" and active_provider == "custom" and active_model:
                status_text = "● Active"
                status_class = "status-active"
            else:
                status_text = "Not configured"
                status_class = "status-missing"

            # Create the list item (no ID to avoid duplicates on refresh)
            item = ListItem(
                Horizontal(
                    Static(provider_name, classes="setup-list-item-label"),
                    Static(status_text, classes=f"setup-list-item-status {status_class}"),
                    classes="setup-list-item",
                ),
            )
            item.data = provider_code  # Store provider code as data
            list_view.append(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle provider selection."""
        provider_code = getattr(event.item, "data", None)
        if provider_code:
            self._configure_provider(provider_code)

    def _configure_provider(self, provider_code: str) -> None:
        """Open configuration screen for the selected provider."""
        if provider_code == "custom":
            self.app.push_screen(CustomProviderScreen(), self._on_config_complete)
        else:
            # Find the env var name for this provider
            env_var = next(
                (env for code, _, env in PROVIDERS if code == provider_code and env),
                None,
            )
            provider_name = next(
                (name for code, name, _ in PROVIDERS if code == provider_code),
                provider_code.capitalize(),
            )

            # Check if API key is already configured
            has_api_key = bool(os.getenv(env_var)) if env_var else False

            if has_api_key:
                # Show actions menu (Change Model / Change API Key)
                self.app.push_screen(
                    ProviderActionsScreen(provider_code, provider_name, env_var),
                    self._on_config_complete,
                )
            else:
                # First time setup: API key first, then model selection
                self.app.push_screen(
                    ApiKeyScreen(provider_code, provider_name, env_var, next_screen="model_select"),
                    self._on_config_complete,
                )

    def _on_config_complete(self, result: bool | None) -> None:
        """Called when a config screen is dismissed."""
        self._refresh_provider_list()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(None)

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.dismiss(None)


class ProviderActionsScreen(ModalScreen[bool]):
    """Modal screen showing actions for an already-configured provider."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ProviderActionsScreen {
        align: center middle;
    }

    #actions-list {
        max-height: 6;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        provider_code: str,
        provider_name: str,
        env_var: str | None,
    ) -> None:
        super().__init__()
        self.provider_code = provider_code
        self.provider_name = provider_name
        self.env_var = env_var

    def compose(self) -> ComposeResult:
        with Container(id="actions-dialog", classes="setup-dialog"):
            yield Static(f"Manage {self.provider_name}", classes="setup-title")
            yield ListView(id="actions-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate actions list."""
        list_view = self.query_one("#actions-list", ListView)

        actions = [
            ("change_model", "Change Model"),
            ("change_api_key", "Change API Key"),
        ]

        for action_id, action_label in actions:
            item = ListItem(Static(action_label))
            item.data = action_id
            list_view.append(item)

        list_view.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle action selection."""
        action = getattr(event.item, "data", None)
        if action == "change_model":
            self.app.push_screen(
                ModelSelectScreen(self.provider_code, self.provider_name, self.env_var),
                self._on_action_complete,
            )
        elif action == "change_api_key":
            self.app.push_screen(
                ApiKeyScreen(self.provider_code, self.provider_name, self.env_var, None),
                self._on_action_complete,
            )

    def _on_action_complete(self, result: bool) -> None:
        """Called when sub-screen is dismissed."""
        if result:
            self.dismiss(True)
        # If cancelled, stay on actions screen

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class ModelSelectScreen(ModalScreen[bool]):
    """Modal screen for selecting a model from a provider."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ModelSelectScreen {
        align: center middle;
    }

    #model-list {
        max-height: 8;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        provider_code: str,
        provider_name: str,
        env_var: str | None,
    ) -> None:
        super().__init__()
        self.provider_code = provider_code
        self.provider_name = provider_name
        self.env_var = env_var
        self.models: list[tuple[str, str]] = MODEL_CHOICES.get(provider_code, [])

    def compose(self) -> ComposeResult:
        with Container(id="model-select-dialog", classes="setup-dialog"):
            yield Static(f"Select {self.provider_name} Model", classes="setup-title")
            yield ListView(id="model-list", classes="setup-list")
            with Horizontal(classes="setup-buttons"):
                yield Button("Back", variant="default", id="btn-back", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate model list."""
        list_view = self.query_one("#model-list", ListView)

        # Get current model if any
        current_config = load_model_config()
        current_model = None
        if current_config and current_config.get("provider") == self.provider_code:
            current_model = current_config.get("model_name")

        for idx, (model_id, model_name) in enumerate(self.models):
            suffix = " (current)" if model_id == current_model else ""
            item = ListItem(Static(f"{model_name}{suffix}"))
            item.data = idx  # Store index as data
            list_view.append(item)

        list_view.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.dismiss(False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle model selection."""
        idx = getattr(event.item, "data", None)
        if idx is not None:
            selected_model_id = self.models[idx][0]
            save_model_config(self.provider_code, selected_model_id)
            self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class ApiKeyScreen(ModalScreen[bool]):
    """Modal screen for entering an API key."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    ApiKeyScreen {
        align: center middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        provider_code: str,
        provider_name: str,
        env_var: str | None,
        selected_model_id: str | None = None,
        next_screen: str | None = None,  # "model_select" to chain to model selection
    ) -> None:
        super().__init__()
        self.provider_code = provider_code
        self.provider_name = provider_name
        self.env_var = env_var
        self.selected_model_id = selected_model_id
        self.next_screen = next_screen

    def compose(self) -> ComposeResult:
        with Container(id="api-key-dialog", classes="setup-dialog"):
            yield Static(f"{self.provider_name} API Key", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("Enter your API key:", classes="setup-field-label")
                yield Input(
                    placeholder="sk-...",
                    password=True,
                    id="api-key-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the input."""
        self.query_one("#api-key-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        self._save_config()

    def _save_config(self) -> None:
        """Save the API key and optionally chain to model selection."""
        api_key = self.query_one("#api-key-input", Input).value.strip()
        error_label = self.query_one("#error-message", Static)

        if not api_key:
            error_label.update("API key is required")
            return

        # Save API key to .env
        if self.env_var:
            save_env_vars({self.env_var: api_key})
            reload_env_and_settings()

        # If we have a pre-selected model, save it
        if self.selected_model_id:
            save_model_config(self.provider_code, self.selected_model_id)
            self.dismiss(True)
        elif self.next_screen == "model_select":
            # Chain to model selection
            self.app.push_screen(
                ModelSelectScreen(self.provider_code, self.provider_name, self.env_var),
                self._on_model_select_complete,
            )
        else:
            # Just saving the API key (e.g., from "Change API Key" action)
            self.dismiss(True)

    def _on_model_select_complete(self, result: bool) -> None:
        """Called when model selection is complete."""
        self.dismiss(result)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class CustomProviderScreen(ModalScreen[bool]):
    """Modal screen for configuring a custom OpenAI-compatible provider."""

    CSS_PATH = [SETUP_CSS_PATH]

    # Screen-specific overrides only
    CSS = """
    CustomProviderScreen {
        align: center middle;
    }

    #custom-dialog {
        width: 70;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="custom-dialog", classes="setup-dialog"):
            yield Static("Configure Custom Provider", classes="setup-title")
            yield Static(
                "Configure an OpenAI-compatible endpoint (e.g., Ollama, vLLM)",
                classes="setup-hint",
            )

            with Vertical(classes="setup-field"):
                yield Label("API Base URL:", classes="setup-field-label")
                yield Input(
                    placeholder="http://localhost:11434/v1",
                    value="http://localhost:11434/v1",
                    id="base-url-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Model Name:", classes="setup-field-label")
                yield Input(
                    placeholder="e.g., llama2, codellama, mistral",
                    id="model-name-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("API Key (optional):", classes="setup-field-label")
                yield Input(
                    placeholder="Leave empty if not required",
                    password=True,
                    id="api-key-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Continue", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the first input."""
        self.query_one("#base-url-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save the custom provider configuration."""
        base_url = self.query_one("#base-url-input", Input).value.strip()
        model_name = self.query_one("#model-name-input", Input).value.strip()
        api_key = self.query_one("#api-key-input", Input).value.strip()

        error_label = self.query_one("#error-message", Static)

        if not base_url:
            error_label.update("API Base URL is required")
            return

        if not model_name:
            error_label.update("Model name is required")
            return

        # Save API key if provided
        if api_key:
            save_env_vars({"CUSTOM_API_KEY": api_key})
            reload_env_and_settings()

        # Save model config
        save_model_config("custom", model_name, base_url)

        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)
