import os
from pathlib import Path
from rich.prompt import Prompt, Confirm
from sdrbot_cli.config import console, COLORS

def _get_or_prompt(env_var_name: str, display_name: str, is_secret: bool = False, required: bool = False, force: bool = False) -> str | None:
    """Gets an environment variable or prompts the user for it."""
    # If force is True, ignore existing env var and prompt anyway
    if not force:
        value = os.getenv(env_var_name)
        if value:
            console.print(f"[{COLORS['dim']}][✓] {display_name} already set. Masked: {'*' * 8 if is_secret else value}[/{COLORS['dim']}]")
            return value
    
    if required:
        console.print(f"[{COLORS['primary']}]Missing {display_name}.[/]")
        return Prompt.ask(f"  Please enter your {display_name}", password=is_secret, default=None)
    else:
        if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure {display_name}?[/", default=False):
            return Prompt.ask(f"  Please enter your {display_name}", password=is_secret, default=None)
    return None

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
    console.print(f"[{COLORS['dim']}]Values will be saved to your project's .env file.[/]{COLORS['dim']}\n")

    env_vars = {}

    # LLM Provider
    console.print(f"[{COLORS['primary']}]--- Large Language Model (LLM) Configuration ---[/{COLORS['primary']}]")
    llm_choice = Prompt.ask(
        f"[{COLORS['primary']}]Choose your LLM provider[/] (openai/anthropic/google)",
        choices=["openai", "anthropic", "google"],
        default="openai"
    )

    if llm_choice == "openai":
        openai_key = _get_or_prompt("OPENAI_API_KEY", "OpenAI API Key", is_secret=True, required=True, force=force)
        if openai_key:
            env_vars["OPENAI_API_KEY"] = openai_key
    elif llm_choice == "anthropic":
        anthropic_key = _get_or_prompt("ANTHROPIC_API_KEY", "Anthropic API Key", is_secret=True, required=True, force=force)
        if anthropic_key:
            env_vars["ANTHROPIC_API_KEY"] = anthropic_key
    elif llm_choice == "google":
        google_key = _get_or_prompt("GOOGLE_API_KEY", "Google API Key", is_secret=True, required=True, force=force)
        if google_key:
            env_vars["GOOGLE_API_KEY"] = google_key
    
    console.print("\n")

    # Tavily
    console.print(f"[{COLORS['primary']}]--- Web Search Configuration (Tavily) ---[/{COLORS['primary']}]")
    tavily_key = _get_or_prompt("TAVILY_API_KEY", "Tavily API Key", is_secret=True, required=False, force=force)
    if tavily_key:
        env_vars["TAVILY_API_KEY"] = tavily_key
    console.print("\n")

    # Salesforce
    console.print(f"[{COLORS['primary']}]--- Salesforce Configuration (Optional) ---[/{COLORS['primary']}]")
    if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure Salesforce?[/", default=False):
        sf_client_id = _get_or_prompt("SF_CLIENT_ID", "Salesforce Client ID", required=True, force=force)
        sf_client_secret = _get_or_prompt("SF_CLIENT_SECRET", "Salesforce Client Secret", is_secret=True, required=True, force=force)
        if sf_client_id: env_vars["SF_CLIENT_ID"] = sf_client_id
        if sf_client_secret: env_vars["SF_CLIENT_SECRET"] = sf_client_secret
    console.print("\n")

    # HubSpot
    console.print(f"[{COLORS['primary']}]--- HubSpot Configuration (Optional) ---[/{COLORS['primary']}]")
    if Confirm.ask(f"[{COLORS['primary']}]Do you want to configure HubSpot?[/", default=False):
        hubspot_auth_choice = Prompt.ask(
            f"  [{COLORS['primary']}]Choose HubSpot authentication method[/] (1: OAuth - Client ID/Secret, 2: Personal Access Token)",
            choices=["1", "2"],
            default="1"
        )
        if hubspot_auth_choice == "1":
            hubspot_client_id = _get_or_prompt("HUBSPOT_CLIENT_ID", "HubSpot Client ID", required=True, force=force)
            hubspot_client_secret = _get_or_prompt("HUBSPOT_CLIENT_SECRET", "HubSpot Client Secret", is_secret=True, required=True, force=force)
            if hubspot_client_id: env_vars["HUBSPOT_CLIENT_ID"] = hubspot_client_id
            if hubspot_client_secret: env_vars["HUBSPOT_CLIENT_SECRET"] = hubspot_client_secret
        else:
            hubspot_access_token = _get_or_prompt("HUBSPOT_ACCESS_TOKEN", "HubSpot Personal Access Token", is_secret=True, required=True, force=force)
            if hubspot_access_token: env_vars["HUBSPOT_ACCESS_TOKEN"] = hubspot_access_token
    console.print("\n")

    # Save to .env
    # Use current working directory for .env file
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
    
    console.print(f"[{COLORS['primary']}][bold]Setup Complete![/bold][/]")
    console.print(f"[{COLORS['dim']}]Your credentials have been saved to {env_file}[/{COLORS['dim']}]")
    console.print(f"[{COLORS['dim']}]You can now run SDRbot.[/]{COLORS['dim']}\n")

if __name__ == "__main__":
    run_setup_wizard()
