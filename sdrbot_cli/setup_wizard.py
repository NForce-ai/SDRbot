import os
from pathlib import Path
from rich.prompt import Prompt, Confirm
from dotenv import load_dotenv
from sdrbot_cli.config import console, COLORS, save_model_config

def _get_or_prompt(env_var_name: str, display_name: str, is_secret: bool = False, required: bool = False, force: bool = False, default: str | None = None) -> str | None:
    """Gets an environment variable or prompts the user for it."""
    # If force is True, ignore existing env var and prompt anyway
    if not force:
        value = os.getenv(env_var_name)
        if value:
            console.print(f"[{COLORS['dim']}][✓] {display_name} already set. Masked: {'*' * 8 if is_secret else value}[/{COLORS['dim']}]")
            return value
    
    if required:
        console.print(f"[{COLORS['primary']}]Missing {display_name}.[/]")
        return Prompt.ask(f"  Please enter your {display_name}", password=is_secret, default=default)
    else:
        if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure {display_name}?[/", default=False):
            return Prompt.ask(f"  Please enter your {display_name}", password=is_secret, default=default)
    return None

def save_env_vars(env_vars: dict) -> None:
    """Save dictionary of env vars to .env file."""
    project_root = Path.cwd()
    env_file = project_root / ".env"
    
    current_env_content = ""
    if env_file.exists():
        current_env_content = env_file.read_text()

    with open(env_file, "w") as f:
        # Preserve existing comments and lines not being overwritten
        for line in current_env_content.splitlines():
            key_val = line.split('=', 1)
            if len(key_val) == 2 and key_val[0] not in env_vars:
                f.write(line + "\n")
            elif not line.strip().startswith("#") and not line.strip() == "":
                # Also write back non-comment, non-empty lines that aren't being overwritten
                if key_val[0] not in env_vars:
                    f.write(line + "\n")
        
        for key, value in env_vars.items():
            # Only write if value is not None (user provided something)
            if value is not None:
                f.write(f"{key}=\"{value}\"\n")
    
    console.print(f"[{COLORS['dim']}]Credentials saved to {env_file}[/{COLORS['dim']}]")


def setup_service(service_name: str, force: bool = False) -> bool:
    """
    Run setup for a specific service.
    Returns True if configuration was updated.
    """
    env_vars = {}
    
    if service_name == "salesforce":
        console.print(f"[{COLORS['primary']}]--- Salesforce Configuration ---[/{COLORS['primary']}]")
        sf_client_id = _get_or_prompt("SF_CLIENT_ID", "Salesforce Client ID", required=True, force=force)
        sf_client_secret = _get_or_prompt("SF_CLIENT_SECRET", "Salesforce Client Secret", is_secret=True, required=True, force=force)
        if sf_client_id: env_vars["SF_CLIENT_ID"] = sf_client_id
        if sf_client_secret: env_vars["SF_CLIENT_SECRET"] = sf_client_secret

        # Trigger OAuth flow if we have credentials
        if sf_client_id and sf_client_secret:
            save_env_vars(env_vars)
            # Reload env vars so the auth module picks them up
            load_dotenv(override=True)

            if Confirm.ask(f"[{COLORS['primary']}]Do you want to authenticate with Salesforce now?[/]", default=True):
                try:
                    # Import here to pick up fresh env vars
                    import importlib
                    import sdrbot_cli.auth.salesforce as sf_auth
                    importlib.reload(sf_auth)
                    sf_auth.login()
                    console.print(f"[{COLORS['primary']}]Salesforce authentication complete![/{COLORS['primary']}]")
                except Exception as e:
                    console.print(f"[red]Salesforce authentication failed: {e}[/red]")
                    console.print(f"[{COLORS['dim']}]You can authenticate later when you first use Salesforce.[/{COLORS['dim']}]")
            return True
        
    elif service_name == "hubspot":
        console.print(f"[{COLORS['primary']}]--- HubSpot Configuration ---[/{COLORS['primary']}]")
        hubspot_auth_choice = Prompt.ask(
            f"  [{COLORS['primary']}]Choose HubSpot authentication method[/] (1: Personal Access Token, 2: OAuth - Client ID/Secret)",
            choices=["1", "2"],
            default="1"
        )
        if hubspot_auth_choice == "1":
            hubspot_access_token = _get_or_prompt("HUBSPOT_ACCESS_TOKEN", "HubSpot Personal Access Token", is_secret=True, required=True, force=force)
            if hubspot_access_token: env_vars["HUBSPOT_ACCESS_TOKEN"] = hubspot_access_token
        else:
            hubspot_client_id = _get_or_prompt("HUBSPOT_CLIENT_ID", "HubSpot Client ID", required=True, force=force)
            hubspot_client_secret = _get_or_prompt("HUBSPOT_CLIENT_SECRET", "HubSpot Client Secret", is_secret=True, required=True, force=force)
            if hubspot_client_id: env_vars["HUBSPOT_CLIENT_ID"] = hubspot_client_id
            if hubspot_client_secret: env_vars["HUBSPOT_CLIENT_SECRET"] = hubspot_client_secret

            # Trigger OAuth flow if we have credentials
            if hubspot_client_id and hubspot_client_secret:
                save_env_vars(env_vars)
                # Reload env vars so the auth module picks them up
                load_dotenv(override=True)

                if Confirm.ask(f"[{COLORS['primary']}]Do you want to authenticate with HubSpot now?[/]", default=True):
                    try:
                        # Import here to pick up fresh env vars
                        import importlib
                        import sdrbot_cli.auth.hubspot as hs_auth
                        importlib.reload(hs_auth)
                        hs_auth.login()
                        console.print(f"[{COLORS['primary']}]HubSpot authentication complete![/{COLORS['primary']}]")
                    except Exception as e:
                        console.print(f"[red]HubSpot authentication failed: {e}[/red]")
                        console.print(f"[{COLORS['dim']}]You can authenticate later when you first use HubSpot.[/{COLORS['dim']}]")
                return True
            
    elif service_name == "attio":
        console.print(f"[{COLORS['primary']}]--- Attio Configuration ---[/{COLORS['primary']}]")
        attio_key = _get_or_prompt("ATTIO_API_KEY", "Attio API Key", is_secret=True, required=True, force=force)
        if attio_key: env_vars["ATTIO_API_KEY"] = attio_key
        
    elif service_name == "lusha":
        console.print(f"[{COLORS['primary']}]--- Lusha Configuration ---[/{COLORS['primary']}]")
        lusha_key = _get_or_prompt("LUSHA_API_KEY", "Lusha API Key", is_secret=True, required=True, force=force)
        if lusha_key: env_vars["LUSHA_API_KEY"] = lusha_key
        
    elif service_name == "hunter":
        console.print(f"[{COLORS['primary']}]--- Hunter.io Configuration ---[/{COLORS['primary']}]")
        hunter_key = _get_or_prompt("HUNTER_API_KEY", "Hunter.io API Key", is_secret=True, required=True, force=force)
        if hunter_key: env_vars["HUNTER_API_KEY"] = hunter_key
        
    elif service_name == "tavily":
        console.print(f"[{COLORS['primary']}]--- Tavily Configuration ---[/{COLORS['primary']}]")
        tavily_key = _get_or_prompt("TAVILY_API_KEY", "Tavily API Key", is_secret=True, required=True, force=force)
        if tavily_key: env_vars["TAVILY_API_KEY"] = tavily_key
        
    else:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        return False
        
    if env_vars:
        save_env_vars(env_vars)
        return True
    return False


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
    ]
}

def setup_llm(force: bool = False) -> bool:
    """
    Run setup for LLM configuration.
    Returns True if configuration was updated.
    """
    console.print(f"[{COLORS['primary']}]--- Large Language Model (LLM) Configuration ---[/{COLORS['primary']}]")
    llm_choice = Prompt.ask(
        f"[{COLORS['primary']}]Choose your LLM provider[/] (openai/anthropic/google/custom)",
        choices=["openai", "anthropic", "google", "custom"],
        default="openai"
    )

    env_vars = {}
    if llm_choice == "openai":
        openai_key = _get_or_prompt("OPENAI_API_KEY", "OpenAI API Key", is_secret=True, required=True, force=force)
        if openai_key:
            env_vars["OPENAI_API_KEY"] = openai_key
            
        # Select Model
        choices = [label for label, _ in MODEL_CHOICES["openai"]]
        model_label = Prompt.ask(
            f"  [{COLORS['primary']}]Choose OpenAI Model[/]",
            choices=choices,
            default=choices[0]
        )
        # Find the API value for the selected label
        model_value = next(val for label, val in MODEL_CHOICES["openai"] if label == model_label)
        save_model_config("openai", model_value)

    elif llm_choice == "anthropic":
        anthropic_key = _get_or_prompt("ANTHROPIC_API_KEY", "Anthropic API Key", is_secret=True, required=True, force=force)
        if anthropic_key:
            env_vars["ANTHROPIC_API_KEY"] = anthropic_key
            
        # Select Model
        choices = [label for label, _ in MODEL_CHOICES["anthropic"]]
        model_label = Prompt.ask(
            f"  [{COLORS['primary']}]Choose Anthropic Model[/]",
            choices=choices,
            default=choices[0]
        )
        # Find the API value for the selected label
        model_value = next(val for label, val in MODEL_CHOICES["anthropic"] if label == model_label)
        save_model_config("anthropic", model_value)

    elif llm_choice == "google":
        google_key = _get_or_prompt("GOOGLE_API_KEY", "Google API Key", is_secret=True, required=True, force=force)
        if google_key:
            env_vars["GOOGLE_API_KEY"] = google_key

        # Select Model
        choices = [label for label, _ in MODEL_CHOICES["google"]]
        model_label = Prompt.ask(
            f"  [{COLORS['primary']}]Choose Google Gemini Model[/]",
            choices=choices,
            default=choices[0]
        )
        # Find the API value for the selected label
        model_value = next(val for label, val in MODEL_CHOICES["google"] if label == model_label)
        save_model_config("google", model_value)

    elif llm_choice == "custom":
        console.print(f"[{COLORS['dim']}]Configure a custom OpenAI-compatible endpoint (e.g., local Ollama, vLLM).[/]")
        
        api_base = _get_or_prompt("CUSTOM_API_BASE", "API Base URL", required=True, force=force, default="http://localhost:11434/v1")
        # Don't save base to env, saving to model config instead
        
        model_name = _get_or_prompt("CUSTOM_MODEL_NAME", "Model Name", required=True, force=force)
        # Don't save model name to env, saving to model config instead
            
        # Optional API Key for custom provider
        api_key = _get_or_prompt("CUSTOM_API_KEY", "API Key (Optional)", is_secret=True, required=False, force=force)
        if api_key:
            env_vars["CUSTOM_API_KEY"] = api_key

        if api_base and model_name:
            save_model_config("custom", model_name, api_base)

    if env_vars:
        save_env_vars(env_vars)
        return True
    
    # Return True if we saved model config even if no env vars changed
    # (e.g. just switched model but kept same key)
    return True


def run_setup_wizard(force: bool = False) -> None:
    """
    Guides the user through setting up essential environment variables for SDRbot.
    Missing variables will be prompted for and saved to the .env file.

    Args:
        force: If True, run the wizard even if credentials already exist.
    """
    # Check if we already have what we need
    has_api_key = (
        os.getenv("OPENAI_API_KEY") or 
        os.getenv("ANTHROPIC_API_KEY") or 
        os.getenv("GOOGLE_API_KEY")
    )

    if has_api_key and not force:
        # Configuration exists, skip wizard
        return

    console.print(f"[{COLORS['primary']}][bold]SDRbot Setup Wizard[/bold][/{COLORS['primary']}]")
    console.print(f"[{COLORS['dim']}]This wizard will help you configure your API keys and credentials.[/]{COLORS['dim']}]")
    console.print(f"[{COLORS['dim']}]Values will be saved to your working folders .env file.[/]{COLORS['dim']}\n")

    # LLM Provider
    setup_llm(force=force)
    
    console.print("\n")

    # Optional services
    if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure Tavily (Web Search)?[/", default=False):
        setup_service("tavily", force)
    console.print("\n")

    if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure Salesforce?[/", default=False):
        setup_service("salesforce", force)
    console.print("\n")

    if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure HubSpot?[/", default=False):
        setup_service("hubspot", force)
    console.print("\n")

    if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure Hunter.io?[/", default=False):
        setup_service("hunter", force)
    console.print("\n")

    if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure Lusha?[/", default=False):
        setup_service("lusha", force)
    console.print("\n")

    if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure Attio?[/", default=False):
        setup_service("attio", force)
    console.print("\n")

    console.print(f"[{COLORS['primary']}][bold]Setup Complete![/bold][/]")
    console.print(f"[{COLORS['dim']}]You can now run SDRbot.[/]{COLORS['dim']}\n")

if __name__ == "__main__":
    run_setup_wizard()
