"""CLI commands for model management.

This module provides the implementation for model-related commands:
- models list: Show all available models and the active one
- models switch <provider>: Switch to a different provider (openai, anthropic, google, custom)
- models update <provider>: Reconfigure settings for a provider
"""

import sys
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from sdrbot_cli.config import (
    settings, 
    load_model_config, 
    save_model_config, 
    COLORS
)
from sdrbot_cli.setup_wizard import setup_llm, MODEL_CHOICES, _get_or_prompt

console = Console(highlight=False)

PROVIDERS = ["openai", "anthropic", "google", "custom"]

def handle_models_command(args: list[str]) -> str | bool:
    """Handle /models commands.

    Args:
        args: Command arguments (e.g., ["switch", "openai"])

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

    if action == "switch" and len(args) > 1:
        provider = args[1].lower()
        return _switch_model(provider)

    if action == "update" and len(args) > 1:
        provider = args[1].lower()
        return _update_model(provider)

    # Show usage
    console.print()
    console.print("[yellow]Usage:[/yellow]")
    console.print("  /models              - List active and available models")
    console.print("  /models switch <provider> - Switch provider (openai, anthropic, google, custom)")
    console.print("  /models update <provider> - Reconfigure model settings for a provider")
    console.print()
    return True


def _list_models() -> None:
    """List all models and their status."""
    # Load current config to see what's active
    current_config = load_model_config()
    active_provider = current_config["provider"] if current_config else None
    
    # If no config file, fallback to checking settings (legacy)
    if not active_provider:
        if settings.has_custom: active_provider = "custom"
        elif settings.has_openai: active_provider = "openai"
        elif settings.has_anthropic: active_provider = "anthropic"
        elif settings.has_google: active_provider = "google"

    table = Table(title="LLM Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Active", justify="center")
    table.add_column("Current Model", style="dim")
    table.add_column("Configured", justify="center")

    for provider in PROVIDERS:
        is_active = (provider == active_provider)
        
        # Determine if configured (has API key)
        is_configured = False
        current_model_display = "—"
        
        if provider == "openai":
            is_configured = settings.has_openai
            if is_active and current_config:
                current_model_display = current_config["model_name"]
            elif settings.openai_api_key:
                # Try to grab from env if not active but configured
                import os
                current_model_display = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
                
        elif provider == "anthropic":
            is_configured = settings.has_anthropic
            if is_active and current_config:
                current_model_display = current_config["model_name"]
            elif settings.anthropic_api_key:
                import os
                current_model_display = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

        elif provider == "google":
            is_configured = settings.has_google
            if is_active and current_config:
                current_model_display = current_config["model_name"]
            elif settings.google_api_key:
                import os
                current_model_display = os.environ.get("GOOGLE_MODEL", "gemini-2.5-pro")

        elif provider == "custom":
            is_configured = settings.has_custom
            if is_active and current_config:
                current_model_display = f"{current_config['model_name']} ({current_config.get('api_base', 'local')})"
            elif settings.custom_model_name:
                current_model_display = settings.custom_model_name

        active_str = "[green]●[/green]" if is_active else ""
        configured_str = "[green]✓[/green]" if is_configured else "[dim]—[/dim]"

        table.add_row(provider, active_str, current_model_display, configured_str)

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Use /models switch <provider> to change.[/dim]")
    console.print()


def _switch_model(provider: str) -> str | bool:
    """Switch to a different provider.
    
    If the provider is not configured, triggers the update/setup flow.
    If it is configured, simply updates model.json to point to it.
    """
    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print(f"[dim]Available: {', '.join(PROVIDERS)}[/dim]")
        return True

    # Check if configured
    needs_setup = False
    if provider == "openai" and not settings.has_openai: needs_setup = True
    elif provider == "anthropic" and not settings.has_anthropic: needs_setup = True
    elif provider == "google" and not settings.has_google: needs_setup = True
    elif provider == "custom" and not settings.has_custom: needs_setup = True
    
    # If explicit model.json config is missing for this provider (even if env vars exist), 
    # we might want to prompt to ensure we have the right model selected, 
    # but for now let's assume if env vars exist we can just switch.
    # However, for "custom", we really need the base_url which might not be in settings if we rely purely on env vars fallback?
    # Actually settings.has_custom checks env vars.
    
    if needs_setup:
        console.print(f"[yellow]{provider} is not configured. Starting setup...[/yellow]")
        return _update_model(provider)

    # If already configured, just update model.json
    # We need to know WHICH model to use. If we just switch, we might default to whatever is in env or default.
    # For better UX, let's ask the user to confirm the model if they are switching, 
    # OR just switch if we can infer a good default.
    # Given the requirement "if switching to a model that doesnt have params it asks you to configure it",
    # let's try to just switch, but if we don't know the model name (e.g. only API key is set), prompt.
    
    # Simple approach: triggering _update_model allows selection. 
    # But if I already have it set up, I might just want to switch back.
    # Let's check if we have a saved config for this provider? We don't really have separate saved configs per provider yet, just one active config.
    # So we should probably prompt for the model choice when switching, to be safe and clear.
    
    return _update_model(provider)


def _update_model(provider: str) -> str | bool:
    """Run configuration for a specific provider."""
    if provider not in PROVIDERS:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        return True

    console.print(f"[{COLORS['primary']}]Configuring {provider}...[/{COLORS['primary']}]")
    
    # Reuse logic from setup_llm but targeted
    # We can't easily reuse setup_llm exactly because it asks for the provider first.
    # So we'll implement specific logic here using the shared MODEL_CHOICES and helpers.
    
    from sdrbot_cli.setup_wizard import save_env_vars
    
    env_vars = {}
    model_name_to_save = ""
    api_base_to_save = None

    if provider == "openai":
        key = _get_or_prompt("OPENAI_API_KEY", "OpenAI API Key", is_secret=True, required=True, force=True)
        if key: env_vars["OPENAI_API_KEY"] = key
        
        choices = [label for label, _ in MODEL_CHOICES["openai"]]
        model_label = Prompt.ask(f"  [{COLORS['primary']}]Choose Model[/]", choices=choices, default=choices[0])
        model_name_to_save = next(val for label, val in MODEL_CHOICES["openai"] if label == model_label)

    elif provider == "anthropic":
        key = _get_or_prompt("ANTHROPIC_API_KEY", "Anthropic API Key", is_secret=True, required=True, force=True)
        if key: env_vars["ANTHROPIC_API_KEY"] = key
        
        choices = [label for label, _ in MODEL_CHOICES["anthropic"]]
        model_label = Prompt.ask(f"  [{COLORS['primary']}]Choose Model[/]", choices=choices, default=choices[0])
        model_name_to_save = next(val for label, val in MODEL_CHOICES["anthropic"] if label == model_label)

    elif provider == "google":
        key = _get_or_prompt("GOOGLE_API_KEY", "Google API Key", is_secret=True, required=True, force=True)
        if key: env_vars["GOOGLE_API_KEY"] = key
        
        choices = [label for label, _ in MODEL_CHOICES["google"]]
        model_label = Prompt.ask(f"  [{COLORS['primary']}]Choose Model[/]", choices=choices, default=choices[0])
        model_name_to_save = next(val for label, val in MODEL_CHOICES["google"] if label == model_label)

    elif provider == "custom":
        api_base = _get_or_prompt("CUSTOM_API_BASE", "API Base URL", required=True, force=True, default="http://localhost:11434/v1")
        model_name = _get_or_prompt("CUSTOM_MODEL_NAME", "Model Name", required=True, force=True)
        api_key = _get_or_prompt("CUSTOM_API_KEY", "API Key (Optional)", is_secret=True, required=False, force=True)
        
        if api_key: env_vars["CUSTOM_API_KEY"] = api_key
        model_name_to_save = model_name
        api_base_to_save = api_base

    # Save keys
    if env_vars:
        save_env_vars(env_vars)
    
    # Save active config
    if model_name_to_save:
        save_model_config(provider, model_name_to_save, api_base_to_save)
        console.print(f"[green]✓ Switched to {provider} ({model_name_to_save})[/green]")
        console.print("[dim]Reloading agent...[/dim]")
        return "reload"
    
    return True
