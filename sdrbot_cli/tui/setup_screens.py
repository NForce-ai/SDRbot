"""Setup wizard screens for Textual TUI."""

import os
from pathlib import Path

import httpx
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from sdrbot_cli.config import load_model_config, load_provider_config, save_model_config
from sdrbot_cli.setup.env import reload_env_and_settings, save_env_vars

# Path to shared CSS
SETUP_CSS_PATH = Path(__file__).parent / "setup_common.tcss"

# Model choices per provider
MODEL_CHOICES = {
    "openai": [
        ("gpt-5-mini", "ChatGPT 5 Mini"),
        ("gpt-5", "ChatGPT 5"),
        ("gpt-5.1", "ChatGPT 5.1"),
        ("gpt-5.2-2025-12-11", "ChatGPT 5.2"),
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

# Bedrock model ID to friendly name mapping
BEDROCK_MODEL_NAMES = {
    "anthropic.claude-3-5-sonnet-20241022-v2:0": "Claude 3.5 Sonnet v2",
    "anthropic.claude-3-5-haiku-20241022-v1:0": "Claude 3.5 Haiku",
    "anthropic.claude-3-opus-20240229-v1:0": "Claude 3 Opus",
    "amazon.titan-text-premier-v1:0": "Titan Text Premier",
    "meta.llama3-70b-instruct-v1:0": "Llama 3 70B",
    "mistral.mistral-large-2407-v1:0": "Mistral Large",
}


def get_model_display_name(provider: str, model_id: str) -> str:
    """Get a friendly display name for a model.

    For Bedrock, looks up the friendly name. For others, returns as-is.
    """
    if provider == "bedrock" and model_id in BEDROCK_MODEL_NAMES:
        return BEDROCK_MODEL_NAMES[model_id]
    return model_id


def test_openai_compatible_endpoint(
    api_base: str, api_key: str, timeout: float = 10.0
) -> str | None:
    """Test an OpenAI-compatible endpoint by calling /models.

    Returns None on success, error message on failure.
    """
    try:
        url = f"{api_base.rstrip('/')}/models"
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        if response.status_code == 200:
            return None
        elif response.status_code == 401:
            return "Authentication failed - check your API key"
        elif response.status_code == 404:
            # Some endpoints don't have /models, try a chat completion
            return None  # Accept 404 on /models as some servers don't implement it
        else:
            return f"Server returned error {response.status_code}"
    except httpx.ConnectError:
        return "Cannot connect to server - is it running?"
    except httpx.TimeoutException:
        return "Connection timed out"
    except Exception as e:
        return f"Connection error: {e!s}"


def test_azure_endpoint(
    endpoint: str, deployment: str, api_version: str, api_key: str, timeout: float = 10.0
) -> str | None:
    """Test Azure OpenAI endpoint.

    Returns None on success, error message on failure.
    """
    try:
        url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/models?api-version={api_version}"
        response = httpx.get(
            url,
            headers={"api-key": api_key},
            timeout=timeout,
        )
        if response.status_code == 200:
            return None
        elif response.status_code == 401:
            return "Authentication failed - check your API key"
        elif response.status_code == 404:
            return "Deployment not found - check deployment name"
        else:
            # Accept other codes as Azure endpoints vary
            return None
    except httpx.ConnectError:
        return "Cannot connect to Azure endpoint"
    except httpx.TimeoutException:
        return "Connection timed out"
    except Exception as e:
        return f"Connection error: {e!s}"


def test_bedrock_credentials(region: str) -> str | None:
    """Test AWS Bedrock credentials by listing foundation models.

    Returns None on success, error message on failure.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        client = boto3.client("bedrock", region_name=region)
        client.list_foundation_models(maxResults=1)
        return None
    except NoCredentialsError:
        return "AWS credentials not found or invalid"
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "AccessDeniedException":
            return "Access denied - check IAM permissions for Bedrock"
        elif error_code == "UnrecognizedClientException":
            return "Invalid AWS credentials"
        return f"AWS error: {error_code}"
    except ImportError:
        return "boto3 not installed"
    except Exception as e:
        return f"Connection error: {e!s}"


# Providers organized by category
# Format: (code, display_name, env_var_for_api_key)
CLOUD_PROVIDERS = [
    ("openai", "OpenAI", "OPENAI_API_KEY"),
    ("anthropic", "Anthropic", "ANTHROPIC_API_KEY"),
    ("google", "Google Gemini", "GOOGLE_API_KEY"),
    ("azure", "Azure OpenAI", "AZURE_OPENAI_API_KEY"),
    ("bedrock", "Amazon Bedrock", "AWS_ACCESS_KEY_ID"),
    ("huggingface", "HuggingFace", "HUGGINGFACE_API_KEY"),
]

LOCAL_PROVIDERS = [
    ("ollama", "Ollama", None),
    ("vllm", "vLLM", None),
]

ADVANCED_PROVIDERS = [
    ("custom", "Custom Endpoint", None),
]

# Flat list for backwards compatibility
PROVIDERS = CLOUD_PROVIDERS + LOCAL_PROVIDERS + ADVANCED_PROVIDERS


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
        max-height: 14;
    }

    .setup-list-header {
        color: $text-muted;
        text-style: dim;
        padding: 0 1;
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
        """Refresh the provider list with current status, organized by category."""
        list_view = self.query_one("#models-list", ListView)
        list_view.clear()

        current_config = load_model_config()
        active_provider = current_config.get("provider") if current_config else None
        active_model = current_config.get("model_name") if current_config else None

        def add_provider_items(providers: list, header: str) -> None:
            """Add a group of providers with a header."""
            # Add section header (not selectable)
            header_item = ListItem(
                Static(f"── {header} ──", classes="setup-list-header"),
            )
            header_item.data = None  # Not selectable
            list_view.append(header_item)

            for provider_code, provider_name, env_var in providers:
                # Determine status
                has_api_key = bool(env_var and os.getenv(env_var))
                is_active = provider_code == active_provider and active_model

                # Local providers (ollama, vllm) and custom don't need API keys
                is_local = provider_code in ("ollama", "vllm", "custom")

                if is_active:
                    status_text = "● Active"
                    status_class = "status-active"
                elif has_api_key:
                    status_text = "Configured"
                    status_class = "status-configured"
                elif is_local:
                    status_text = ""
                    status_class = ""
                else:
                    status_text = "Not configured"
                    status_class = "status-missing"

                # Create the list item
                item = ListItem(
                    Horizontal(
                        Static(f"  {provider_name}", classes="setup-list-item-label"),
                        Static(status_text, classes=f"setup-list-item-status {status_class}"),
                        classes="setup-list-item",
                    ),
                )
                item.data = provider_code
                list_view.append(item)

        # Add providers by category
        add_provider_items(CLOUD_PROVIDERS, "Cloud")
        add_provider_items(LOCAL_PROVIDERS, "Local")
        add_provider_items(ADVANCED_PROVIDERS, "Advanced")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle provider selection."""
        provider_code = getattr(event.item, "data", None)
        if provider_code:
            self._configure_provider(provider_code)

    def _configure_provider(self, provider_code: str) -> None:
        """Open configuration screen for the selected provider."""
        # Providers with their own setup screens
        if provider_code == "ollama":
            self.app.push_screen(OllamaSetupScreen(), self._on_config_complete)
            return
        if provider_code == "vllm":
            self.app.push_screen(VLLMSetupScreen(), self._on_config_complete)
            return
        if provider_code == "azure":
            self.app.push_screen(AzureSetupScreen(), self._on_config_complete)
            return
        if provider_code == "huggingface":
            self.app.push_screen(HuggingFaceSetupScreen(), self._on_config_complete)
            return
        if provider_code == "bedrock":
            self.app.push_screen(BedrockSetupScreen(), self._on_config_complete)
            return
        if provider_code == "custom":
            self.app.push_screen(CustomProviderScreen(), self._on_config_complete)
            return

        # Cloud providers (openai, anthropic, google) - need API keys
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

    def __init__(self) -> None:
        super().__init__()
        # Load saved config for pre-filling
        saved = load_provider_config("custom")
        self.saved_url = saved.get("api_base", "http://localhost:11434/v1")
        self.saved_model = saved.get("model_name", "")
        self.saved_key = os.environ.get("CUSTOM_API_KEY", "")

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
                    value=self.saved_url,
                    id="base-url-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Model Name:", classes="setup-field-label")
                yield Input(
                    value=self.saved_model,
                    placeholder="e.g., llama2, codellama, mistral",
                    id="model-name-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("API Key (optional):", classes="setup-field-label")
                yield Input(
                    value=self.saved_key,
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

        # Test connection first
        error = test_openai_compatible_endpoint(base_url, api_key or "none")
        if error:
            error_label.update(f"Connection failed: {error}")
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


class OllamaSetupScreen(ModalScreen[bool]):
    """Modal screen for configuring Ollama with auto-detection."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    OllamaSetupScreen {
        align: center middle;
    }

    #ollama-dialog {
        width: 70;
    }

    #ollama-models-list {
        max-height: 8;
    }

    .ollama-status {
        text-align: center;
        padding: 1;
    }

    .ollama-status-ok {
        color: $success;
    }

    .ollama-status-error {
        color: $error;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Load saved config for pre-filling
        saved = load_provider_config("ollama")
        api_base = saved.get("api_base", "")
        # Extract base URL from api_base (remove /v1 suffix)
        if api_base.endswith("/v1"):
            self.base_url = api_base[:-3]
        else:
            self.base_url = api_base or "http://localhost:11434"
        self.saved_model = saved.get("model_name", "")
        self.available_models: list[dict] = []

    def compose(self) -> ComposeResult:
        with Container(id="ollama-dialog", classes="setup-dialog"):
            yield Static("Ollama Setup", classes="setup-title")
            yield Static("Detecting Ollama...", id="ollama-status", classes="ollama-status")

            with Vertical(classes="setup-field"):
                yield Label("Ollama URL:", classes="setup-field-label")
                yield Input(
                    value=self.base_url,
                    placeholder="http://localhost:11434",
                    id="ollama-url-input",
                    classes="setup-field-input",
                )

            yield Static("Select a model:", id="model-label", classes="setup-field-label")
            yield ListView(id="ollama-models-list", classes="setup-list")

            with Vertical(classes="setup-field", id="manual-model-field"):
                yield Label("Or enter model name manually:", classes="setup-field-label")
                yield Input(
                    value=self.saved_model,
                    placeholder="e.g., llama3.2, qwen2.5:7b",
                    id="manual-model-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Refresh", variant="default", id="btn-refresh", classes="setup-btn")
                yield Button("Save", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Check Ollama status on mount."""
        self._check_ollama()

    def _check_ollama(self) -> None:
        """Check if Ollama is running and get available models."""
        self.base_url = self.query_one("#ollama-url-input", Input).value.strip()
        status_widget = self.query_one("#ollama-status", Static)
        list_view = self.query_one("#ollama-models-list", ListView)
        list_view.clear()
        self.available_models = []

        try:
            # Query Ollama API for installed models
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                self.available_models = data.get("models", [])

                if self.available_models:
                    status_widget.update(
                        f"✓ Ollama running - {len(self.available_models)} models found"
                    )
                    status_widget.remove_class("ollama-status-error")
                    status_widget.add_class("ollama-status-ok")

                    # Populate model list
                    for model in self.available_models:
                        name = model.get("name", "Unknown")
                        size_bytes = model.get("size", 0)
                        size_gb = size_bytes / (1024**3) if size_bytes else 0

                        # Format display
                        if size_gb >= 1:
                            size_str = f"{size_gb:.1f}GB"
                        else:
                            size_str = f"{size_bytes / (1024**2):.0f}MB"

                        item = ListItem(
                            Horizontal(
                                Static(name, classes="setup-list-item-label"),
                                Static(size_str, classes="setup-list-item-status"),
                                classes="setup-list-item",
                            ),
                        )
                        item.data = name
                        list_view.append(item)

                    list_view.focus()
                else:
                    status_widget.update("✓ Ollama running but no models installed")
                    status_widget.remove_class("ollama-status-error")
                    status_widget.add_class("ollama-status-ok")
            else:
                status_widget.update(f"✗ Ollama returned error: {response.status_code}")
                status_widget.remove_class("ollama-status-ok")
                status_widget.add_class("ollama-status-error")
        except httpx.ConnectError:
            status_widget.update("✗ Cannot connect to Ollama - is it running?")
            status_widget.remove_class("ollama-status-ok")
            status_widget.add_class("ollama-status-error")
        except Exception as e:
            status_widget.update(f"✗ Error: {e!s}")
            status_widget.remove_class("ollama-status-ok")
            status_widget.add_class("ollama-status-error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-refresh":
            self._check_ollama()
        elif event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle model selection from list."""
        model_name = getattr(event.item, "data", None)
        if model_name:
            # Set manual input to selected model and save
            self.query_one("#manual-model-input", Input).value = model_name
            self._save_config()

    def _save_config(self) -> None:
        """Save the Ollama configuration."""
        base_url = self.query_one("#ollama-url-input", Input).value.strip()
        model_name = self.query_one("#manual-model-input", Input).value.strip()

        error_label = self.query_one("#error-message", Static)

        if not model_name:
            error_label.update("Please select or enter a model name")
            return

        # Test connection first
        api_base = f"{base_url}/v1"
        error = test_openai_compatible_endpoint(api_base, "ollama")
        if error:
            error_label.update(f"Connection failed: {error}")
            return

        # Save model config with Ollama-specific settings
        save_model_config("ollama", model_name, api_base)

        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class VLLMSetupScreen(ModalScreen[bool]):
    """Modal screen for configuring vLLM."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    VLLMSetupScreen {
        align: center middle;
    }

    #vllm-dialog {
        width: 70;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Load saved config for pre-filling
        saved = load_provider_config("vllm")
        self.saved_url = saved.get("api_base", "http://localhost:8000/v1")
        self.saved_model = saved.get("model_name", "")
        self.saved_key = os.environ.get("CUSTOM_API_KEY", "")

    def compose(self) -> ComposeResult:
        with Container(id="vllm-dialog", classes="setup-dialog"):
            yield Static("vLLM Setup", classes="setup-title")
            yield Static(
                "Configure your vLLM server endpoint",
                classes="setup-hint",
            )

            with Vertical(classes="setup-field"):
                yield Label("vLLM Server URL:", classes="setup-field-label")
                yield Input(
                    value=self.saved_url,
                    placeholder="http://localhost:8000/v1",
                    id="vllm-url-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Model Name:", classes="setup-field-label")
                yield Input(
                    value=self.saved_model,
                    placeholder="e.g., meta-llama/Llama-2-7b-chat-hf",
                    id="vllm-model-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("API Key (optional):", classes="setup-field-label")
                yield Input(
                    value=self.saved_key,
                    placeholder="Leave empty if not required",
                    password=True,
                    id="vllm-key-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Save", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the URL input."""
        self.query_one("#vllm-url-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save the vLLM configuration."""
        base_url = self.query_one("#vllm-url-input", Input).value.strip()
        model_name = self.query_one("#vllm-model-input", Input).value.strip()
        api_key = self.query_one("#vllm-key-input", Input).value.strip()

        error_label = self.query_one("#error-message", Static)

        if not base_url:
            error_label.update("Server URL is required")
            return

        if not model_name:
            error_label.update("Model name is required")
            return

        # Test connection first
        error = test_openai_compatible_endpoint(base_url, api_key or "none")
        if error:
            error_label.update(f"Connection failed: {error}")
            return

        # Save API key if provided
        if api_key:
            save_env_vars({"CUSTOM_API_KEY": api_key})
            reload_env_and_settings()

        # Save model config
        save_model_config("vllm", model_name, base_url)

        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class BedrockSetupScreen(ModalScreen[bool]):
    """Modal screen for configuring Amazon Bedrock."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    BedrockSetupScreen {
        align: center middle;
    }

    #bedrock-dialog {
        width: 80;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    # Common Bedrock model IDs
    BEDROCK_MODELS = [
        ("anthropic.claude-3-5-sonnet-20241022-v2:0", "Claude 3.5 Sonnet v2"),
        ("anthropic.claude-3-5-haiku-20241022-v1:0", "Claude 3.5 Haiku"),
        ("anthropic.claude-3-opus-20240229-v1:0", "Claude 3 Opus"),
        ("amazon.titan-text-premier-v1:0", "Amazon Titan Text Premier"),
        ("meta.llama3-70b-instruct-v1:0", "Llama 3 70B Instruct"),
        ("mistral.mistral-large-2407-v1:0", "Mistral Large"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Load saved config for pre-filling
        saved = load_provider_config("bedrock")
        self.saved_model = saved.get("model_name", "")
        # AWS credentials from env vars
        self.saved_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
        self.saved_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        self.saved_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    def compose(self) -> ComposeResult:
        with Container(id="bedrock-dialog", classes="setup-dialog"):
            yield Static("Amazon Bedrock Setup", classes="setup-title")

            with Vertical(classes="setup-field"):
                yield Label("AWS Access Key ID:", classes="setup-field-label")
                yield Input(
                    value=self.saved_access_key,
                    placeholder="AKIA...",
                    id="aws-access-key-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("AWS Secret Access Key:", classes="setup-field-label")
                yield Input(
                    value=self.saved_secret_key,
                    placeholder="Your secret key",
                    password=True,
                    id="aws-secret-key-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("AWS Region:", classes="setup-field-label")
                yield Input(
                    value=self.saved_region,
                    placeholder="us-east-1",
                    id="aws-region-input",
                    classes="setup-field-input",
                )

            yield Static("Select a model:", classes="setup-field-label")
            yield ListView(id="bedrock-models-list", classes="setup-list")

            with Vertical(classes="setup-field"):
                yield Label("Or enter model ID manually:", classes="setup-field-label")
                yield Input(
                    value=self.saved_model,
                    placeholder="e.g., anthropic.claude-3-sonnet-...",
                    id="bedrock-model-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Save", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Populate model list and focus first input."""
        list_view = self.query_one("#bedrock-models-list", ListView)
        for model_id, model_name in self.BEDROCK_MODELS:
            item = ListItem(Static(model_name))
            item.data = model_id
            list_view.append(item)

        # Focus appropriately based on whether we have saved config
        if self.saved_model:
            self.query_one("#btn-save", Button).focus()
        else:
            self.query_one("#aws-access-key-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle model selection from list."""
        model_id = getattr(event.item, "data", None)
        if model_id:
            self.query_one("#bedrock-model-input", Input).value = model_id

    def _save_config(self) -> None:
        """Save the Bedrock configuration."""
        access_key = self.query_one("#aws-access-key-input", Input).value.strip()
        secret_key = self.query_one("#aws-secret-key-input", Input).value.strip()
        region = self.query_one("#aws-region-input", Input).value.strip()
        model_id = self.query_one("#bedrock-model-input", Input).value.strip()

        error_label = self.query_one("#error-message", Static)

        if not access_key:
            error_label.update("AWS Access Key ID is required")
            return

        if not secret_key:
            error_label.update("AWS Secret Access Key is required")
            return

        if not region:
            error_label.update("AWS Region is required")
            return

        if not model_id:
            error_label.update("Please select or enter a model ID")
            return

        # Temporarily set env vars for boto3 to use during test
        os.environ["AWS_ACCESS_KEY_ID"] = access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
        os.environ["AWS_DEFAULT_REGION"] = region

        # Test connection first
        error = test_bedrock_credentials(region)
        if error:
            error_label.update(f"Connection failed: {error}")
            return

        # Save AWS credentials to env file
        save_env_vars(
            {
                "AWS_ACCESS_KEY_ID": access_key,
                "AWS_SECRET_ACCESS_KEY": secret_key,
                "AWS_DEFAULT_REGION": region,
            }
        )
        reload_env_and_settings()

        # Save model config
        save_model_config("bedrock", model_id)

        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class HuggingFaceSetupScreen(ModalScreen[bool]):
    """Modal screen for configuring HuggingFace Inference Endpoints."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    HuggingFaceSetupScreen {
        align: center middle;
    }

    #huggingface-dialog {
        width: 80;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Load saved config for pre-filling
        saved = load_provider_config("huggingface")
        self.saved_model = saved.get("model_name", "")
        api_base = saved.get("api_base", "")
        self.saved_token = os.environ.get("HUGGINGFACE_API_KEY", "")

        # Extract endpoint URL if it's a dedicated endpoint (not serverless)
        if api_base and "api-inference.huggingface.co" not in api_base:
            # Dedicated endpoint - extract the URL (strip /v1)
            self.saved_endpoint = api_base.replace("/v1", "").rstrip("/")
        else:
            self.saved_endpoint = ""

    def compose(self) -> ComposeResult:
        with Container(id="huggingface-dialog", classes="setup-dialog"):
            yield Static("HuggingFace Setup", classes="setup-title")
            yield Static(
                "For serverless: enter model ID. For dedicated: enter both URL and model name.",
                classes="setup-hint",
            )

            with Vertical(classes="setup-field"):
                yield Label("Model Name:", classes="setup-field-label")
                yield Input(
                    value=self.saved_model,
                    placeholder="e.g., meta-llama/Llama-3.2-3B-Instruct or tgi",
                    id="hf-model-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label(
                    "Endpoint URL (leave empty for serverless):", classes="setup-field-label"
                )
                yield Input(
                    value=self.saved_endpoint,
                    placeholder="e.g., https://xyz123.us-east-1.aws.endpoints.huggingface.cloud",
                    id="hf-endpoint-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("HuggingFace API Token:", classes="setup-field-label")
                yield Input(
                    value=self.saved_token,
                    placeholder="hf_...",
                    password=True,
                    id="hf-token-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Save", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the model input."""
        self.query_one("#hf-model-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save the HuggingFace configuration."""
        model_name = self.query_one("#hf-model-input", Input).value.strip()
        endpoint_url = self.query_one("#hf-endpoint-input", Input).value.strip()
        api_token = self.query_one("#hf-token-input", Input).value.strip()

        error_label = self.query_one("#error-message", Static)

        if not model_name:
            error_label.update("Model name is required")
            return

        if not api_token:
            error_label.update("HuggingFace API token is required")
            return

        # Determine API base URL
        if endpoint_url:
            # Dedicated endpoint - use provided URL
            api_base = endpoint_url.rstrip("/")
            if not api_base.endswith("/v1"):
                api_base = f"{api_base}/v1"
        else:
            # Serverless inference - construct URL from model ID
            api_base = f"https://api-inference.huggingface.co/models/{model_name}/v1"

        # Test connection first
        error = test_openai_compatible_endpoint(api_base, api_token)
        if error:
            error_label.update(f"Connection failed: {error}")
            return

        # Save API token to env
        save_env_vars({"HUGGINGFACE_API_KEY": api_token})
        reload_env_and_settings()

        save_model_config("huggingface", model_name, api_base)

        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)


class AzureSetupScreen(ModalScreen[bool]):
    """Modal screen for configuring Azure OpenAI."""

    CSS_PATH = [SETUP_CSS_PATH]

    CSS = """
    AzureSetupScreen {
        align: center middle;
    }

    #azure-dialog {
        width: 80;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Load saved config for pre-filling
        saved = load_provider_config("azure")
        self.saved_endpoint = saved.get("azure_endpoint", "")
        self.saved_deployment = saved.get("azure_deployment", "")
        self.saved_version = saved.get("azure_api_version", "2024-02-01")
        self.saved_key = os.environ.get("AZURE_OPENAI_API_KEY", "")

    def compose(self) -> ComposeResult:
        with Container(id="azure-dialog", classes="setup-dialog"):
            yield Static("Azure OpenAI Setup", classes="setup-title")
            yield Static(
                "Configure your Azure OpenAI deployment",
                classes="setup-hint",
            )

            with Vertical(classes="setup-field"):
                yield Label("Azure Endpoint:", classes="setup-field-label")
                yield Input(
                    value=self.saved_endpoint,
                    placeholder="https://your-resource.openai.azure.com/",
                    id="azure-endpoint-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("Deployment Name:", classes="setup-field-label")
                yield Input(
                    value=self.saved_deployment,
                    placeholder="e.g., gpt-4-deployment",
                    id="azure-deployment-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("API Version:", classes="setup-field-label")
                yield Input(
                    value=self.saved_version,
                    placeholder="2024-02-01",
                    id="azure-version-input",
                    classes="setup-field-input",
                )

            with Vertical(classes="setup-field"):
                yield Label("API Key:", classes="setup-field-label")
                yield Input(
                    value=self.saved_key,
                    placeholder="Your Azure OpenAI API key",
                    password=True,
                    id="azure-key-input",
                    classes="setup-field-input",
                )

            yield Static("", id="error-message", classes="setup-error")

            with Horizontal(classes="setup-buttons"):
                yield Button("Save", variant="success", id="btn-save", classes="setup-btn")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="setup-btn")

    def on_mount(self) -> None:
        """Focus the endpoint input."""
        self.query_one("#azure-endpoint-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-save":
            self._save_config()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save_config(self) -> None:
        """Save the Azure OpenAI configuration."""
        endpoint = self.query_one("#azure-endpoint-input", Input).value.strip()
        deployment = self.query_one("#azure-deployment-input", Input).value.strip()
        api_version = self.query_one("#azure-version-input", Input).value.strip()
        api_key = self.query_one("#azure-key-input", Input).value.strip()

        error_label = self.query_one("#error-message", Static)

        if not endpoint:
            error_label.update("Azure endpoint is required")
            return

        if not deployment:
            error_label.update("Deployment name is required")
            return

        if not api_key:
            error_label.update("API key is required")
            return

        # Test connection first
        error = test_azure_endpoint(endpoint, deployment, api_version, api_key)
        if error:
            error_label.update(f"Connection failed: {error}")
            return

        # Save API key to env
        save_env_vars({"AZURE_OPENAI_API_KEY": api_key})
        reload_env_and_settings()

        # Save model config with Azure-specific parameters
        save_model_config(
            provider="azure",
            model_name=deployment,  # Deployment name is used as model name
            api_base=None,
            azure_endpoint=endpoint,
            azure_deployment=deployment,
            azure_api_version=api_version,
        )

        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel and close."""
        self.dismiss(False)
