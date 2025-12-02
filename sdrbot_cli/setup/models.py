"""LLM model configuration for the setup wizard."""

import os

from sdrbot_cli.config import COLORS, console, load_model_config, save_model_config

from .env import get_or_prompt, reload_env_and_settings, save_env_vars
from .menu import CancelledError, show_choice_menu, show_menu

MODEL_CHOICES = {
    "openai": [
        ("ChatGPT 5 Mini", "gpt-5-mini"),
        ("ChatGPT 5", "gpt-5"),
        ("ChatGPT 5.1", "gpt-5.1"),
    ],
    "anthropic": [
        ("Claude Sonnet 4.5", "claude-sonnet-4-5-20250929"),
        ("Claude Opus 4.5", "claude-opus-4-5-20251101"),
    ],
    "google": [
        ("Gemini 2.5 Pro", "gemini-2.5-pro"),
        ("Gemini 3 Pro", "gemini-3-pro-preview"),
    ],
}

PROVIDERS = [
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("google", "Google Gemini"),
    ("custom", "Custom (OpenAI-compatible)"),
]


def get_model_status() -> tuple[str | None, str | None, str]:
    """
    Get current model configuration status.

    Returns:
        (provider, model_name, status_string)
    """
    current_config = load_model_config()
    active_provider = current_config.get("provider") if current_config else None
    active_model = current_config.get("model_name") if current_config else None

    if active_provider:
        provider_display = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "google": "Google",
            "custom": "Custom",
        }.get(active_provider, active_provider.capitalize())

        status = f"[green]✓ {provider_display} ({active_model})[/green]"
    else:
        status = "[dim]• Not Configured[/dim]"

    return active_provider, active_model, status


async def setup_models() -> str | None:
    """
    Run the Models setup wizard.

    Returns:
        "back" to return to main menu, None if exited
    """
    try:
        return await _setup_models_impl()
    except CancelledError:
        console.print(f"\n[{COLORS['dim']}]Configuration cancelled.[/{COLORS['dim']}]")
        return "back"


async def _setup_models_impl() -> str | None:
    """Implementation of models setup that may raise CancelledError."""
    while True:
        # Load current state
        current_config = load_model_config()
        active_provider = current_config.get("provider") if current_config else None

        menu_items = []
        for code, label in PROVIDERS:
            # Check configuration
            is_configured = False
            if code == "openai":
                is_configured = bool(os.getenv("OPENAI_API_KEY"))
            elif code == "anthropic":
                is_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
            elif code == "google":
                is_configured = bool(os.getenv("GOOGLE_API_KEY"))
            elif code == "custom":
                is_configured = active_provider == "custom"

            status_parts = []
            if code == active_provider:
                status_parts.append("[green]● Active[/green]")
            elif is_configured:
                status_parts.append("[cyan]Configured[/cyan]")
            else:
                status_parts.append("[dim]Missing Keys[/dim]")

            status_str = " ".join(status_parts)
            menu_items.append((code, label, status_str))

        menu_items.append(("---", "──────────────", ""))
        menu_items.append(("back", "← Back", ""))

        selected_provider = await show_menu(menu_items, title="Models")

        if selected_provider == "back" or selected_provider is None:
            return "back"

        # Provider Selected - Show Actions
        await _configure_provider(selected_provider, active_provider)


async def _configure_provider(provider_code: str, active_provider: str | None) -> None:
    """Configure a specific provider."""
    # Check if configured
    is_configured = False
    if provider_code == "openai":
        is_configured = bool(os.getenv("OPENAI_API_KEY"))
    elif provider_code == "anthropic":
        is_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
    elif provider_code == "google":
        is_configured = bool(os.getenv("GOOGLE_API_KEY"))

    action = None
    is_explicit_config = False

    if not is_configured:
        action = "configure"
    else:
        action_items = []
        if provider_code != "custom":
            action_items.append(("activate", "Activate / Switch Model", ""))

        action_items.append(("configure", "Configure Credentials", ""))
        action_items.append(("back", "Back", ""))

        action = await show_menu(action_items, title=f"Manage {provider_code.capitalize()}")

        if action == "configure":
            is_explicit_config = True

    if action == "back" or action is None:
        return

    env_vars = {}

    if action == "configure" or (action == "activate" and provider_code == "custom"):
        # Configuration Logic
        if provider_code == "openai":
            openai_key = await get_or_prompt(
                "OPENAI_API_KEY",
                "OpenAI API Key",
                is_secret=True,
                required=True,
                force=is_explicit_config,
            )
            if openai_key:
                env_vars["OPENAI_API_KEY"] = openai_key
                model_value = await show_choice_menu(
                    [(v, label) for label, v in MODEL_CHOICES["openai"]],
                    title="Choose OpenAI model",
                )
                if model_value:
                    save_model_config("openai", model_value)

        elif provider_code == "anthropic":
            anthropic_key = await get_or_prompt(
                "ANTHROPIC_API_KEY",
                "Anthropic API Key",
                is_secret=True,
                required=True,
                force=is_explicit_config,
            )
            if anthropic_key:
                env_vars["ANTHROPIC_API_KEY"] = anthropic_key
                model_value = await show_choice_menu(
                    [(v, label) for label, v in MODEL_CHOICES["anthropic"]],
                    title="Choose Anthropic model",
                )
                if model_value:
                    save_model_config("anthropic", model_value)

        elif provider_code == "google":
            google_key = await get_or_prompt(
                "GOOGLE_API_KEY",
                "Google API Key",
                is_secret=True,
                required=True,
                force=is_explicit_config,
            )
            if google_key:
                env_vars["GOOGLE_API_KEY"] = google_key
                model_value = await show_choice_menu(
                    [(v, label) for label, v in MODEL_CHOICES["google"]],
                    title="Choose Google Gemini model",
                )
                if model_value:
                    save_model_config("google", model_value)

        elif provider_code == "custom":
            console.print(
                f"[{COLORS['dim']}]Configure a custom OpenAI-compatible endpoint "
                "(e.g., local Ollama, vLLM).[/]"
            )
            api_base = await get_or_prompt(
                "CUSTOM_API_BASE",
                "API Base URL",
                required=True,
                force=True,
                default="http://localhost:11434/v1",
            )
            model_name = await get_or_prompt(
                "CUSTOM_MODEL_NAME", "Model Name", required=True, force=True
            )
            api_key = await get_or_prompt(
                "CUSTOM_API_KEY",
                "API Key (Optional)",
                is_secret=True,
                required=False,
                force=True,
            )
            if api_key:
                env_vars["CUSTOM_API_KEY"] = api_key

            if api_base and model_name:
                save_model_config("custom", model_name, api_base)

    elif action == "activate":
        # Just switching model for already configured provider
        if provider_code in MODEL_CHOICES:
            model_value = await show_choice_menu(
                [(v, label) for label, v in MODEL_CHOICES[provider_code]],
                title=f"Choose {provider_code.capitalize()} model",
            )
            if model_value:
                save_model_config(provider_code, model_value)

    if env_vars:
        save_env_vars(env_vars)
        reload_env_and_settings()
