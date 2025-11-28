"""CLI commands for model management.

This module provides the implementation for model-related commands:
- /models list: Show all available models and the active one
- /models switch: Interactive wizard to switch provider and model
- /models configure <provider>: Reconfigure API key and model for a provider
"""

import os

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from sdrbot_cli.config import COLORS, load_model_config, save_model_config, settings
from sdrbot_cli.setup_wizard import MODEL_CHOICES

console = Console(highlight=False)

PROVIDERS = ["openai", "anthropic", "google", "custom"]


def handle_models_command(args: list[str]) -> str | bool:
    """Handle /models commands.

    Args:
        args: Command arguments (e.g., ["switch"], ["configure", "openai"])

    Returns:
        - "reload": Agent needs to be reloaded (new model selected)
        - True: Command was handled
        - False: Command was not handled
    """
    if not args:
        _list_models()
        return True

    action = args[0].lower()

    if action == "list":
        _list_models()
        return True

    if action == "switch":
        return _switch_model()

    if action == "configure" and len(args) > 1:
        provider = args[1].lower()
        return _configure_model(provider)

    # Show usage
    _show_usage()
    return True


def _show_usage() -> None:
    """Show usage information for /models command."""
    console.print()
    console.print("[yellow]Usage:[/yellow]")
    console.print("  /models                       - List active and available models")
    console.print("  /models switch                - Switch to a different provider/model")
    console.print("  /models configure <provider>  - Reconfigure API key and model")
    console.print()
    console.print("[dim]Providers: openai, anthropic, google, custom[/dim]")
    console.print()


def _list_models() -> None:
    """List all models and their status."""
    current_config = load_model_config()
    active_provider = current_config["provider"] if current_config else None

    # If no config file, fallback to checking settings (legacy)
    if not active_provider:
        if settings.has_custom:
            active_provider = "custom"
        elif settings.has_openai:
            active_provider = "openai"
        elif settings.has_anthropic:
            active_provider = "anthropic"
        elif settings.has_google:
            active_provider = "google"

    table = Table(title="LLM Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Active", justify="center")
    table.add_column("Current Model", style="dim")
    table.add_column("Configured", justify="center")

    for provider in PROVIDERS:
        is_active = provider == active_provider

        # Determine if configured (has API key)
        is_configured = False
        current_model_display = "—"

        if provider == "openai":
            is_configured = settings.has_openai
            if is_active and current_config:
                current_model_display = current_config["model_name"]
            elif settings.openai_api_key:
                current_model_display = os.environ.get("OPENAI_MODEL", "gpt-4o")

        elif provider == "anthropic":
            is_configured = settings.has_anthropic
            if is_active and current_config:
                current_model_display = current_config["model_name"]
            elif settings.anthropic_api_key:
                current_model_display = os.environ.get(
                    "ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"
                )

        elif provider == "google":
            is_configured = settings.has_google
            if is_active and current_config:
                current_model_display = current_config["model_name"]
            elif settings.google_api_key:
                current_model_display = os.environ.get("GOOGLE_MODEL", "gemini-2.5-pro")

        elif provider == "custom":
            is_configured = settings.has_custom
            if is_active and current_config:
                current_model_display = (
                    f"{current_config['model_name']} ({current_config.get('api_base', 'local')})"
                )
            elif settings.custom_model_name:
                current_model_display = settings.custom_model_name

        active_str = "[green]●[/green]" if is_active else ""
        configured_str = "[green]✓[/green]" if is_configured else "[dim]—[/dim]"

        table.add_row(provider, active_str, current_model_display, configured_str)

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Use /models switch to change provider/model.[/dim]")
    console.print()


def _prompt_provider_choice() -> str:
    """Display numbered provider choices and return the selected provider."""
    providers = [
        ("OpenAI", "openai"),
        ("Anthropic", "anthropic"),
        ("Google", "google"),
        ("Custom (OpenAI-compatible)", "custom"),
    ]

    console.print()
    console.print(f"  [{COLORS['primary']}]Available providers:[/{COLORS['primary']}]")
    for i, (label, _) in enumerate(providers, 1):
        # Show configured status
        provider_id = providers[i - 1][1]
        is_configured = _is_provider_configured(provider_id)
        status = "[green]✓[/green]" if is_configured else "[dim]—[/dim]"
        console.print(f"    [{COLORS['primary']}]{i}[/{COLORS['primary']}]) {label}  {status}")
    console.print()

    while True:
        choice = Prompt.ask(
            f"  [{COLORS['primary']}]Select provider[/{COLORS['primary']}]", default="1"
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(providers):
                return providers[idx][1]
            console.print(f"  [red]Please enter a number between 1 and {len(providers)}[/red]")
        except ValueError:
            # Maybe they typed the provider name directly
            for label, provider_id in providers:
                if choice.lower() in (label.lower(), provider_id.lower()):
                    return provider_id
            console.print(f"  [red]Please enter a number between 1 and {len(providers)}[/red]")


def _prompt_model_choice(provider: str) -> str:
    """Display numbered model choices and return the selected model name."""
    choices = MODEL_CHOICES.get(provider, [])
    if not choices:
        return ""

    console.print()
    console.print(f"  [{COLORS['primary']}]Available models:[/{COLORS['primary']}]")
    for i, (label, model_id) in enumerate(choices, 1):
        console.print(
            f"    [{COLORS['primary']}]{i}[/{COLORS['primary']}]) {label} [dim]({model_id})[/dim]"
        )
    console.print()

    while True:
        choice = Prompt.ask(
            f"  [{COLORS['primary']}]Select model[/{COLORS['primary']}]", default="1"
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(choices):
                return choices[idx][1]  # Return the model_id
            console.print(f"  [red]Please enter a number between 1 and {len(choices)}[/red]")
        except ValueError:
            # Maybe they typed the model name directly
            for label, model_id in choices:
                if choice.lower() in (label.lower(), model_id.lower()):
                    return model_id
            console.print(f"  [red]Please enter a number between 1 and {len(choices)}[/red]")


def _is_provider_configured(provider: str) -> bool:
    """Check if a provider has the required configuration (API key)."""
    if provider == "openai":
        return settings.has_openai
    elif provider == "anthropic":
        return settings.has_anthropic
    elif provider == "google":
        return settings.has_google
    elif provider == "custom":
        return settings.has_custom
    return False


def _switch_model() -> str | bool:
    """Interactive wizard to switch provider and model.

    Mimics the setup wizard flow:
    1. Ask for provider
    2. Ask for model
    3. If provider not configured, ask for API key

    If provider is already configured, skips the API key prompt.
    """
    console.print(f"[{COLORS['primary']}]Switch LLM Provider/Model[/{COLORS['primary']}]")

    # Step 1: Choose provider
    provider = _prompt_provider_choice()

    # Step 2: Check if provider is configured
    is_configured = _is_provider_configured(provider)

    from sdrbot_cli.setup_wizard import _get_or_prompt, save_env_vars

    env_vars = {}
    model_name_to_save = ""
    api_base_to_save = None

    if provider == "custom":
        # Custom always needs base URL and model name
        if is_configured:
            # Use existing values as defaults
            default_base = os.environ.get("CUSTOM_API_BASE", "http://localhost:11434/v1")
            default_model = os.environ.get("CUSTOM_MODEL_NAME", "")
            console.print(f"  [dim]Current: {default_model} @ {default_base}[/dim]")

            # Ask if they want to change
            change = Prompt.ask(
                f"  [{COLORS['primary']}]Change configuration?[/{COLORS['primary']}]",
                choices=["y", "n"],
                default="n",
            )
            if change == "n":
                # Just reload with current config
                save_model_config("custom", default_model, default_base)
                console.print(f"[green]✓ Switched to custom ({default_model})[/green]")
                console.print("[dim]Reloading agent...[/dim]")
                return "reload"

        # Need to configure custom endpoint
        api_base = _get_or_prompt(
            "CUSTOM_API_BASE",
            "API Base URL",
            required=True,
            force=True,
            default="http://localhost:11434/v1",
        )
        model_name = _get_or_prompt("CUSTOM_MODEL_NAME", "Model Name", required=True, force=True)
        api_key = _get_or_prompt(
            "CUSTOM_API_KEY", "API Key (Optional)", is_secret=True, required=False, force=True
        )

        if api_key:
            env_vars["CUSTOM_API_KEY"] = api_key
        model_name_to_save = model_name
        api_base_to_save = api_base

    else:
        # Standard provider (openai, anthropic, google)
        if not is_configured:
            # Need API key first
            key_env_var = f"{provider.upper()}_API_KEY"
            key_label = f"{provider.title()} API Key"
            key = _get_or_prompt(key_env_var, key_label, is_secret=True, required=True, force=True)
            if key:
                env_vars[key_env_var] = key

        # Step 3: Choose model
        model_name_to_save = _prompt_model_choice(provider)

    # Save env vars if any
    if env_vars:
        save_env_vars(env_vars)
        # Reload settings to pick up new keys
        settings.reload()

    # Save model config
    if model_name_to_save:
        save_model_config(provider, model_name_to_save, api_base_to_save)
        console.print(f"[green]✓ Switched to {provider} ({model_name_to_save})[/green]")
        console.print("[dim]Reloading agent...[/dim]")
        return "reload"

    return True


def _configure_model(provider: str) -> str | bool:
    """Run full configuration for a specific provider (API key and model selection).

    Always prompts for API key, even if already configured.
    """
    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print(f"[dim]Available: {', '.join(PROVIDERS)}[/dim]")
        return True

    console.print(f"[{COLORS['primary']}]Configuring {provider}...[/{COLORS['primary']}]")

    from sdrbot_cli.setup_wizard import _get_or_prompt, save_env_vars

    env_vars = {}
    model_name_to_save = ""
    api_base_to_save = None

    if provider == "openai":
        key = _get_or_prompt(
            "OPENAI_API_KEY", "OpenAI API Key", is_secret=True, required=True, force=True
        )
        if key:
            env_vars["OPENAI_API_KEY"] = key
        model_name_to_save = _prompt_model_choice("openai")

    elif provider == "anthropic":
        key = _get_or_prompt(
            "ANTHROPIC_API_KEY", "Anthropic API Key", is_secret=True, required=True, force=True
        )
        if key:
            env_vars["ANTHROPIC_API_KEY"] = key
        model_name_to_save = _prompt_model_choice("anthropic")

    elif provider == "google":
        key = _get_or_prompt(
            "GOOGLE_API_KEY", "Google API Key", is_secret=True, required=True, force=True
        )
        if key:
            env_vars["GOOGLE_API_KEY"] = key
        model_name_to_save = _prompt_model_choice("google")

    elif provider == "custom":
        api_base = _get_or_prompt(
            "CUSTOM_API_BASE",
            "API Base URL",
            required=True,
            force=True,
            default="http://localhost:11434/v1",
        )
        model_name = _get_or_prompt("CUSTOM_MODEL_NAME", "Model Name", required=True, force=True)
        api_key = _get_or_prompt(
            "CUSTOM_API_KEY", "API Key (Optional)", is_secret=True, required=False, force=True
        )

        if api_key:
            env_vars["CUSTOM_API_KEY"] = api_key
        model_name_to_save = model_name
        api_base_to_save = api_base

    # Save keys
    if env_vars:
        save_env_vars(env_vars)
        settings.reload()

    # Save active config
    if model_name_to_save:
        save_model_config(provider, model_name_to_save, api_base_to_save)
        console.print(f"[green]✓ Switched to {provider} ({model_name_to_save})[/green]")
        console.print("[dim]Reloading agent...[/dim]")
        return "reload"

    return True
