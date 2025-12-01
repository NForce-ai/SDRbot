import os
from pathlib import Path

from dotenv import load_dotenv
from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import HTML, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from rich.prompt import Confirm

from sdrbot_cli.config import COLORS, console, load_model_config, save_model_config
from sdrbot_cli.services import disable_service, enable_service
from sdrbot_cli.services.registry import load_config


class CancelledError(Exception):
    """Raised when user cancels input with ESC."""

    pass


async def show_choice_menu(
    options: list[tuple[str, str]], title: str = "Select an option", allow_cancel: bool = True
) -> str | None:
    """
    Show an interactive choice menu using keyboard navigation.

    Args:
        options: List of tuples (value, label)
        title: Title of the menu
        allow_cancel: If True (default), pressing ESC raises CancelledError.
                      If False, ESC returns None.

    Returns:
        The selected value, or None if cancelled and allow_cancel=False.

    Raises:
        CancelledError: If user presses ESC and allow_cancel=True.
    """
    # Convert to the format show_menu expects: (id, label, status)
    menu_options = [(value, label, "") for value, label in options]
    result = await show_menu(menu_options, title=title)
    if result is None and allow_cancel:
        raise CancelledError()
    return result


async def _get_or_prompt(
    env_var_name: str,
    display_name: str,
    is_secret: bool = False,
    required: bool = False,
    force: bool = False,
    default: str | None = None,
) -> str | None:
    """Gets an environment variable or prompts the user for it.

    Raises:
        CancelledError: If user presses ESC or Ctrl+C to cancel.
    """
    from prompt_toolkit import PromptSession

    # If force is True, ignore existing env var and prompt anyway
    if not force:
        value = os.getenv(env_var_name)
        if value:
            console.print(
                f"[{COLORS['dim']}][✓] {display_name} already set. Masked: {'*' * 8 if is_secret else value}[/{COLORS['dim']}]"
            )
            return value

    # Create key bindings that support ESC to cancel
    bindings = KeyBindings()

    @bindings.add("escape")
    def _(event):
        event.app.exit(exception=CancelledError())

    @bindings.add("c-c")
    def _(event):
        event.app.exit(exception=CancelledError())

    session: PromptSession = PromptSession(key_bindings=bindings)

    if required:
        console.print(f"[{COLORS['primary']}]Missing {display_name}.[/]")
        console.print(f"[{COLORS['dim']}](Press ESC to cancel)[/{COLORS['dim']}]")
        return await session.prompt_async(
            f"  Please enter your {display_name}: ",
            is_password=is_secret,
            default=default or "",
        )
    else:
        if Confirm.ask(
            f"[{COLORS['primary']}]Do you want to configure {display_name}?[/", default=False
        ):
            console.print(f"[{COLORS['dim']}](Press ESC to cancel)[/{COLORS['dim']}]")
            return await session.prompt_async(
                f"  Please enter your {display_name}: ",
                is_password=is_secret,
                default=default or "",
            )
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
            key_val = line.split("=", 1)
            if len(key_val) == 2 and key_val[0] not in env_vars:
                f.write(line + "\n")
            elif not line.strip().startswith("#") and not line.strip() == "":
                # Also write back non-comment, non-empty lines that aren't being overwritten
                if key_val[0] not in env_vars:
                    f.write(line + "\n")

        for key, value in env_vars.items():
            # Only write if value is not None (user provided something)
            if value is not None:
                f.write(f'{key}="{value}"\n')

    console.print(f"[{COLORS['dim']}]Credentials saved to {env_file}[/{COLORS['dim']}]")


async def setup_service(service_name: str, force: bool = False) -> bool:
    """
    Run setup for a specific service.
    Returns True if configuration was updated.

    User can press ESC at any prompt to cancel and return to the menu.
    """
    try:
        return await _setup_service_impl(service_name, force)
    except CancelledError:
        console.print(f"\n[{COLORS['dim']}]Configuration cancelled.[/{COLORS['dim']}]")
        return False


async def _setup_service_impl(service_name: str, force: bool = False) -> bool:
    """Implementation of setup_service that may raise CancelledError."""
    env_vars = {}

    if service_name == "salesforce":
        console.print(
            f"[{COLORS['primary']}]--- Salesforce Configuration ---[/{COLORS['primary']}]"
        )
        sf_client_id = await _get_or_prompt(
            "SF_CLIENT_ID", "Salesforce Client ID", required=True, force=force
        )
        sf_client_secret = await _get_or_prompt(
            "SF_CLIENT_SECRET",
            "Salesforce Client Secret",
            is_secret=True,
            required=True,
            force=force,
        )
        if sf_client_id:
            env_vars["SF_CLIENT_ID"] = sf_client_id
        if sf_client_secret:
            env_vars["SF_CLIENT_SECRET"] = sf_client_secret

        # Trigger OAuth flow if we have credentials
        if sf_client_id and sf_client_secret:
            save_env_vars(env_vars)
            # Reload env vars AND settings so the auth module picks them up
            load_dotenv(override=True)
            from sdrbot_cli.config import settings

            settings.reload()

            try:
                # Import here to pick up fresh env vars
                import importlib

                import sdrbot_cli.auth.salesforce as sf_auth

                importlib.reload(sf_auth)
                sf_auth.login()
                console.print(
                    f"[{COLORS['primary']}]Salesforce authentication complete![/{COLORS['primary']}]"
                )
            except Exception as e:
                console.print(f"[red]Salesforce authentication failed: {e}[/red]")
                console.print(
                    f"[{COLORS['dim']}]You can authenticate later when you first use Salesforce.[/{COLORS['dim']}]"
                )  # Enable and sync the service
            from sdrbot_cli.services import enable_service

            enable_service("salesforce", sync=True, verbose=True)
            return True

    elif service_name == "hubspot":
        console.print(f"[{COLORS['primary']}]--- HubSpot Configuration ---[/{COLORS['primary']}]")
        hubspot_auth_choice = await show_choice_menu(
            [
                ("pat", "Personal Access Token"),
                ("oauth", "OAuth (Client ID/Secret)"),
            ],
            title="Choose authentication method",
        )
        if hubspot_auth_choice == "pat":
            hubspot_access_token = await _get_or_prompt(
                "HUBSPOT_ACCESS_TOKEN",
                "HubSpot Personal Access Token",
                is_secret=True,
                required=True,
                force=force,
            )
            if hubspot_access_token:
                env_vars["HUBSPOT_ACCESS_TOKEN"] = hubspot_access_token
        else:
            hubspot_client_id = await _get_or_prompt(
                "HUBSPOT_CLIENT_ID", "HubSpot Client ID", required=True, force=force
            )
            hubspot_client_secret = await _get_or_prompt(
                "HUBSPOT_CLIENT_SECRET",
                "HubSpot Client Secret",
                is_secret=True,
                required=True,
                force=force,
            )
            if hubspot_client_id:
                env_vars["HUBSPOT_CLIENT_ID"] = hubspot_client_id
            if hubspot_client_secret:
                env_vars["HUBSPOT_CLIENT_SECRET"] = hubspot_client_secret

            # Trigger OAuth flow if we have credentials
            if hubspot_client_id and hubspot_client_secret:
                save_env_vars(env_vars)
                # Reload env vars AND settings so the auth module picks them up
                load_dotenv(override=True)
                from sdrbot_cli.config import settings

                settings.reload()

                try:
                    # Import here to pick up fresh env vars
                    import importlib

                    import sdrbot_cli.auth.hubspot as hs_auth

                    importlib.reload(hs_auth)
                    hs_auth.login()
                    console.print(
                        f"[{COLORS['primary']}]HubSpot authentication complete![/{COLORS['primary']}]"
                    )
                except Exception as e:
                    console.print(f"[red]HubSpot authentication failed: {e}[/red]")
                    console.print(
                        f"[{COLORS['dim']}]You can authenticate later when you first use HubSpot.[/{COLORS['dim']}]"
                    )
                # Enable and sync the service
                from sdrbot_cli.services import enable_service

                enable_service("hubspot", sync=True, verbose=True)
                return True

    elif service_name == "attio":
        console.print(f"[{COLORS['primary']}]--- Attio Configuration ---[/{COLORS['primary']}]")
        attio_key = await _get_or_prompt(
            "ATTIO_API_KEY", "Attio API Key", is_secret=True, required=True, force=force
        )
        if attio_key:
            env_vars["ATTIO_API_KEY"] = attio_key

    elif service_name == "zohocrm":
        console.print(f"[{COLORS['primary']}]--- Zoho CRM Configuration ---[/{COLORS['primary']}]")
        zoho_client_id = await _get_or_prompt(
            "ZOHO_CLIENT_ID", "Zoho Client ID", required=True, force=force
        )
        zoho_client_secret = await _get_or_prompt(
            "ZOHO_CLIENT_SECRET",
            "Zoho Client Secret",
            is_secret=True,
            required=True,
            force=force,
        )
        zoho_region = await show_choice_menu(
            [
                ("us", "US (zoho.com)"),
                ("eu", "EU (zoho.eu)"),
                ("in", "India (zoho.in)"),
                ("au", "Australia (zoho.com.au)"),
                ("cn", "China (zoho.com.cn)"),
                ("jp", "Japan (zoho.jp)"),
            ],
            title="Select your Zoho data center region",
        )

        if zoho_client_id:
            env_vars["ZOHO_CLIENT_ID"] = zoho_client_id
        if zoho_client_secret:
            env_vars["ZOHO_CLIENT_SECRET"] = zoho_client_secret
        if zoho_region:
            env_vars["ZOHO_REGION"] = zoho_region

        # Trigger OAuth flow if we have credentials
        if zoho_client_id and zoho_client_secret and zoho_region:
            save_env_vars(env_vars)
            # Reload env vars AND settings so the auth module picks them up
            load_dotenv(override=True)
            from sdrbot_cli.config import settings

            settings.reload()

            try:
                # Import here to pick up fresh env vars
                import importlib

                import sdrbot_cli.auth.zohocrm as zoho_auth

                importlib.reload(zoho_auth)
                zoho_auth.login()
                console.print(
                    f"[{COLORS['primary']}]Zoho CRM authentication complete![/{COLORS['primary']}]"
                )
            except Exception as e:
                console.print(f"[red]Zoho CRM authentication failed: {e}[/red]")
                console.print(
                    f"[{COLORS['dim']}]You can authenticate later when you first use Zoho CRM.[/{COLORS['dim']}]"
                )
            # Enable and sync the service
            from sdrbot_cli.services import enable_service

            enable_service("zohocrm", sync=True, verbose=True)
            return True

    elif service_name == "pipedrive":
        console.print(f"[{COLORS['primary']}]--- Pipedrive Configuration ---[/{COLORS['primary']}]")
        pipedrive_auth_choice = await show_choice_menu(
            [
                ("api_token", "API Token"),
                ("oauth", "OAuth (Client ID/Secret)"),
            ],
            title="Choose authentication method",
        )
        if pipedrive_auth_choice == "api_token":
            pipedrive_api_token = await _get_or_prompt(
                "PIPEDRIVE_API_TOKEN",
                "Pipedrive API Token",
                is_secret=True,
                required=True,
                force=force,
            )
            if pipedrive_api_token:
                env_vars["PIPEDRIVE_API_TOKEN"] = pipedrive_api_token
        else:
            pipedrive_client_id = await _get_or_prompt(
                "PIPEDRIVE_CLIENT_ID", "Pipedrive Client ID", required=True, force=force
            )
            pipedrive_client_secret = await _get_or_prompt(
                "PIPEDRIVE_CLIENT_SECRET",
                "Pipedrive Client Secret",
                is_secret=True,
                required=True,
                force=force,
            )
            if pipedrive_client_id:
                env_vars["PIPEDRIVE_CLIENT_ID"] = pipedrive_client_id
            if pipedrive_client_secret:
                env_vars["PIPEDRIVE_CLIENT_SECRET"] = pipedrive_client_secret

            # Trigger OAuth flow if we have credentials
            if pipedrive_client_id and pipedrive_client_secret:
                save_env_vars(env_vars)
                # Reload env vars AND settings so the auth module picks them up
                load_dotenv(override=True)
                from sdrbot_cli.config import settings

                settings.reload()

                try:
                    # Import here to pick up fresh env vars
                    import importlib

                    import sdrbot_cli.auth.pipedrive as pd_auth

                    importlib.reload(pd_auth)
                    pd_auth.login()
                    console.print(
                        f"[{COLORS['primary']}]Pipedrive authentication complete![/{COLORS['primary']}]"
                    )
                except Exception as e:
                    console.print(f"[red]Pipedrive authentication failed: {e}[/red]")
                    console.print(
                        f"[{COLORS['dim']}]You can authenticate later when you first use Pipedrive.[/{COLORS['dim']}]"
                    )
                # Enable and sync the service
                from sdrbot_cli.services import enable_service

                enable_service("pipedrive", sync=True, verbose=True)
                return True

    elif service_name == "lusha":
        console.print(f"[{COLORS['primary']}]--- Lusha Configuration ---[/{COLORS['primary']}]")
        lusha_key = await _get_or_prompt(
            "LUSHA_API_KEY", "Lusha API Key", is_secret=True, required=True, force=force
        )
        if lusha_key:
            env_vars["LUSHA_API_KEY"] = lusha_key

    elif service_name == "hunter":
        console.print(f"[{COLORS['primary']}]--- Hunter.io Configuration ---[/{COLORS['primary']}]")
        hunter_key = await _get_or_prompt(
            "HUNTER_API_KEY", "Hunter.io API Key", is_secret=True, required=True, force=force
        )
        if hunter_key:
            env_vars["HUNTER_API_KEY"] = hunter_key

    elif service_name == "apollo":
        console.print(f"[{COLORS['primary']}]--- Apollo.io Configuration ---[/{COLORS['primary']}]")
        apollo_key = await _get_or_prompt(
            "APOLLO_API_KEY", "Apollo API Key", is_secret=True, required=True, force=force
        )
        if apollo_key:
            env_vars["APOLLO_API_KEY"] = apollo_key

    elif service_name == "tavily":
        console.print(f"[{COLORS['primary']}]--- Tavily Configuration ---[/{COLORS['primary']}]")
        tavily_key = await _get_or_prompt(
            "TAVILY_API_KEY", "Tavily API Key", is_secret=True, required=True, force=force
        )
        if tavily_key:
            env_vars["TAVILY_API_KEY"] = tavily_key

    elif service_name == "postgres":
        console.print(
            f"[{COLORS['primary']}]--- PostgreSQL Configuration ---[/{COLORS['primary']}]"
        )
        pg_host = await _get_or_prompt(
            "POSTGRES_HOST", "PostgreSQL Host", default="localhost", required=True, force=force
        )
        pg_port = await _get_or_prompt(
            "POSTGRES_PORT", "PostgreSQL Port", default="5432", required=True, force=force
        )
        pg_user = await _get_or_prompt(
            "POSTGRES_USER", "PostgreSQL User", required=True, force=force
        )
        pg_pass = await _get_or_prompt(
            "POSTGRES_PASSWORD", "PostgreSQL Password", is_secret=True, required=True, force=force
        )
        pg_db = await _get_or_prompt(
            "POSTGRES_DB", "PostgreSQL Database Name", required=True, force=force
        )
        pg_ssl = await show_choice_menu(
            [
                ("", "None (no SSL)"),
                ("require", "Require (encrypt, no verification)"),
                ("verify-ca", "Verify CA (encrypt, verify server cert)"),
                ("verify-full", "Verify Full (encrypt, verify server cert + hostname)"),
            ],
            title="SSL Mode",
        )

        if pg_host:
            env_vars["POSTGRES_HOST"] = pg_host
        if pg_port:
            env_vars["POSTGRES_PORT"] = pg_port
        if pg_user:
            env_vars["POSTGRES_USER"] = pg_user
        if pg_pass:
            env_vars["POSTGRES_PASSWORD"] = pg_pass
        if pg_db:
            env_vars["POSTGRES_DB"] = pg_db
        if pg_ssl:
            env_vars["POSTGRES_SSL_MODE"] = pg_ssl

    elif service_name == "mysql":
        console.print(f"[{COLORS['primary']}]--- MySQL Configuration ---[/{COLORS['primary']}]")
        mysql_host = await _get_or_prompt(
            "MYSQL_HOST", "MySQL Host", default="localhost", required=True, force=force
        )
        mysql_port = await _get_or_prompt(
            "MYSQL_PORT", "MySQL Port", default="3306", required=True, force=force
        )
        mysql_user = await _get_or_prompt("MYSQL_USER", "MySQL User", required=True, force=force)
        mysql_pass = await _get_or_prompt(
            "MYSQL_PASSWORD", "MySQL Password", is_secret=True, required=True, force=force
        )
        mysql_db = await _get_or_prompt(
            "MYSQL_DB", "MySQL Database Name", required=True, force=force
        )
        mysql_ssl = await show_choice_menu(
            [
                ("false", "Disabled"),
                ("true", "Enabled"),
            ],
            title="Enable SSL",
        )

        if mysql_host:
            env_vars["MYSQL_HOST"] = mysql_host
        if mysql_port:
            env_vars["MYSQL_PORT"] = mysql_port
        if mysql_user:
            env_vars["MYSQL_USER"] = mysql_user
        if mysql_pass:
            env_vars["MYSQL_PASSWORD"] = mysql_pass
        if mysql_db:
            env_vars["MYSQL_DB"] = mysql_db
        if mysql_ssl == "true":
            env_vars["MYSQL_SSL"] = "true"

    elif service_name == "mongodb":
        console.print(f"[{COLORS['primary']}]--- MongoDB Configuration ---[/{COLORS['primary']}]")
        mongo_uri = await _get_or_prompt(
            "MONGODB_URI",
            "MongoDB Connection URI",
            default="mongodb://localhost:27017",
            is_secret=True,
            required=True,
            force=force,
        )
        mongo_db = await _get_or_prompt(
            "MONGODB_DB", "MongoDB Database Name", required=True, force=force
        )
        mongo_tls = await show_choice_menu(
            [
                ("false", "Disabled"),
                ("true", "Enabled"),
            ],
            title="Enable TLS",
        )

        if mongo_uri:
            env_vars["MONGODB_URI"] = mongo_uri
        if mongo_db:
            env_vars["MONGODB_DB"] = mongo_db
        if mongo_tls == "true":
            env_vars["MONGODB_TLS"] = "true"

    else:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        return False

    if env_vars:
        save_env_vars(env_vars)
        # Reload env vars AND settings so they're available for sync
        load_dotenv(override=True)
        from sdrbot_cli.config import settings

        settings.reload()
        # Enable and sync the service
        from sdrbot_cli.services import enable_service

        enable_service(service_name, sync=True, verbose=True)
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
    ],
}


async def setup_llm(force: bool = False) -> bool:
    """
    Run setup for LLM configuration.
    Returns True if configuration was updated.

    User can press ESC at any prompt to cancel and return to the menu.
    """
    try:
        return await _setup_llm_impl(force)
    except CancelledError:
        console.print(f"\n[{COLORS['dim']}]Configuration cancelled.[/{COLORS['dim']}]")
        return False


async def _setup_llm_impl(force: bool = False) -> bool:
    """Implementation of setup_llm that may raise CancelledError."""
    # Provider definitions
    providers = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google Gemini"),
        ("custom", "Custom (OpenAI-compatible)"),
    ]

    while True:
        # Load current state
        current_config = load_model_config()
        active_provider = current_config.get("provider") if current_config else None

        menu_items = []
        for code, label in providers:
            # Check configuration
            is_configured = False
            if code == "openai":
                is_configured = bool(os.getenv("OPENAI_API_KEY"))
            elif code == "anthropic":
                is_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
            elif code == "google":
                is_configured = bool(os.getenv("GOOGLE_API_KEY"))
            elif code == "custom":
                # Custom is tricky to check without loading config,
                # but let's assume if it's active it's configured, or check config file for custom entries if needed.
                # For simplicity, we'll mark as configured if active, or just check if it was previously set.
                is_configured = active_provider == "custom"

            status_parts = []
            if code == active_provider:
                status_parts.append("[green]● Active[/green]")

            if is_configured:
                status_parts.append("[dim]Configured[/dim]")
            else:
                status_parts.append("[red]Missing Keys[/red]")

            status_str = " ".join(status_parts)
            menu_items.append((code, label, status_str))

        menu_items.append(("back", "Back to Main Menu", ""))

        selected_provider = await show_menu(menu_items, title="Select LLM Provider")

        if selected_provider == "back" or selected_provider is None:
            return False

        # Provider Selected - Show Actions
        # Determine if we can just activate it or need to configure
        provider_code = selected_provider

        # Check if configured again for logic
        is_configured = False
        if provider_code == "openai":
            is_configured = bool(os.getenv("OPENAI_API_KEY"))
        elif provider_code == "anthropic":
            is_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
        elif provider_code == "google":
            is_configured = bool(os.getenv("GOOGLE_API_KEY"))

        action = None
        if not is_configured:
            action = "configure"
        else:
            action_items = []
            if provider_code != "custom":
                action_items.append(("activate", "Activate / Switch Model", ""))

            action_items.append(("configure", "Configure Credentials", ""))
            action_items.append(("back", "Back", ""))

            action = await show_menu(action_items, title=f"Manage {provider_code.capitalize()}")

        if action == "back":
            continue

        env_vars = {}

        if action == "configure" or (action == "activate" and provider_code == "custom"):
            # Configuration Logic
            if provider_code == "openai":
                openai_key = await _get_or_prompt(
                    "OPENAI_API_KEY", "OpenAI API Key", is_secret=True, required=True, force=True
                )
                if openai_key:
                    env_vars["OPENAI_API_KEY"] = openai_key
                    # After setting key, prompt for model to activate immediately
                    model_value = await show_choice_menu(
                        [(v, label) for label, v in MODEL_CHOICES["openai"]],
                        title="Choose OpenAI model",
                    )
                    if model_value:
                        save_model_config("openai", model_value)

            elif provider_code == "anthropic":
                anthropic_key = await _get_or_prompt(
                    "ANTHROPIC_API_KEY",
                    "Anthropic API Key",
                    is_secret=True,
                    required=True,
                    force=True,
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
                google_key = await _get_or_prompt(
                    "GOOGLE_API_KEY", "Google API Key", is_secret=True, required=True, force=True
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
                    f"[{COLORS['dim']}]Configure a custom OpenAI-compatible endpoint (e.g., local Ollama, vLLM).[/]"
                )
                api_base = await _get_or_prompt(
                    "CUSTOM_API_BASE",
                    "API Base URL",
                    required=True,
                    force=True,
                    default="http://localhost:11434/v1",
                )
                model_name = await _get_or_prompt(
                    "CUSTOM_MODEL_NAME", "Model Name", required=True, force=True
                )
                api_key = await _get_or_prompt(
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
            if provider_code == "openai":
                model_value = await show_choice_menu(
                    [(v, label) for label, v in MODEL_CHOICES["openai"]],
                    title="Choose OpenAI model",
                )
                if model_value:
                    save_model_config("openai", model_value)
            elif provider_code == "anthropic":
                model_value = await show_choice_menu(
                    [(v, label) for label, v in MODEL_CHOICES["anthropic"]],
                    title="Choose Anthropic model",
                )
                if model_value:
                    save_model_config("anthropic", model_value)
            elif provider_code == "google":
                model_value = await show_choice_menu(
                    [(v, label) for label, v in MODEL_CHOICES["google"]],
                    title="Choose Google Gemini model",
                )
                if model_value:
                    save_model_config("google", model_value)

        if env_vars:
            save_env_vars(env_vars)
            load_dotenv(override=True)

        return True


def get_service_status(service_name: str) -> tuple[bool, bool]:
    """
    Check service status.
    Returns: (is_configured, is_enabled)
    """
    # Check configuration (env vars)
    configured = False
    if service_name == "salesforce":
        configured = bool(os.getenv("SF_CLIENT_ID") and os.getenv("SF_CLIENT_SECRET"))
    elif service_name == "hubspot":
        configured = bool(
            os.getenv("HUBSPOT_ACCESS_TOKEN")
            or (os.getenv("HUBSPOT_CLIENT_ID") and os.getenv("HUBSPOT_CLIENT_SECRET"))
        )
    elif service_name == "attio":
        configured = bool(os.getenv("ATTIO_API_KEY"))
    elif service_name == "zohocrm":
        configured = bool(
            os.getenv("ZOHO_CLIENT_ID")
            and os.getenv("ZOHO_CLIENT_SECRET")
            and os.getenv("ZOHO_REGION")
        )
    elif service_name == "pipedrive":
        configured = bool(
            os.getenv("PIPEDRIVE_API_TOKEN")
            or (os.getenv("PIPEDRIVE_CLIENT_ID") and os.getenv("PIPEDRIVE_CLIENT_SECRET"))
        )
    elif service_name == "lusha":
        configured = bool(os.getenv("LUSHA_API_KEY"))
    elif service_name == "hunter":
        configured = bool(os.getenv("HUNTER_API_KEY"))
    elif service_name == "apollo":
        configured = bool(os.getenv("APOLLO_API_KEY"))
    elif service_name == "tavily":
        configured = bool(os.getenv("TAVILY_API_KEY"))
    elif service_name == "postgres":
        configured = bool(os.getenv("POSTGRES_HOST"))
    elif service_name == "mysql":
        configured = bool(os.getenv("MYSQL_HOST"))
    elif service_name == "mongodb":
        configured = bool(os.getenv("MONGODB_URI"))

    # Check enabled state from registry
    try:
        config = load_config()
        enabled = config.is_enabled(service_name)
    except Exception:
        enabled = False

    return configured, enabled


async def show_menu(
    options: list[tuple[str, str, str]], title: str = "Select a service to configure"
) -> str | None:
    """
    Show an interactive menu in the terminal using prompt_toolkit.

    Args:
        options: List of tuples (id, label, status_markup)
        title: Title of the menu

    Returns:
        The selected id, or None if cancelled.
    """
    bindings = KeyBindings()
    selected_index = 0

    # Store the result to return
    result_id = None

    @bindings.add("up")
    def _(event):
        nonlocal selected_index
        selected_index = max(0, selected_index - 1)

    @bindings.add("down")
    def _(event):
        nonlocal selected_index
        selected_index = min(len(options) - 1, selected_index + 1)

    @bindings.add("enter")
    def _(event):
        nonlocal result_id
        result_id = options[selected_index][0]
        event.app.exit()

    @bindings.add("c-c")
    @bindings.add("q")
    @bindings.add("escape")
    def _(event):
        event.app.exit()

    def get_formatted_text():
        text = []
        text.extend(
            to_formatted_text(
                HTML(f"<b>{title}</b> <gray>(↑↓ Navigate, Enter Select, Esc Back)</gray>\n\n")
            )
        )

        for i, (_, label, status) in enumerate(options):
            # Convert rich-style markup in status to HTML-ish for prompt_toolkit
            pt_status = status.replace("[green]", "<style fg='green'>").replace(
                "[/green]", "</style>"
            )
            pt_status = pt_status.replace("[red]", "<style fg='red'>").replace("[/red]", "</style>")
            pt_status = pt_status.replace("[yellow]", "<style fg='yellow'>").replace(
                "[/yellow]", "</style>"
            )
            pt_status = pt_status.replace("[dim]", "<style fg='gray'>").replace(
                "[/dim]", "</style>"
            )

            # Allow raw HTML in status if no rich tags found (for submenu items with no status)
            if "[" not in status:
                pt_status = status

            if i == selected_index:
                # Highlighted row
                row_content = f"  > {label:<35} {pt_status}"
                # We need to render the inner HTML first, then apply the background style
                # But HTML() parser handles nested tags.
                text.extend(
                    to_formatted_text(
                        HTML(f"<style bg='#2e3440' fg='#ffffff'>{row_content}</style>")
                    )
                )
            else:
                # Normal row
                row_content = f"    {label:<35} {pt_status}"
                text.extend(to_formatted_text(HTML(row_content)))

            text.append(("", "\n"))
        return text

    # Height = header (2) + items + footer (0)
    window_height = len(options) + 3

    layout = Layout(Window(content=FormattedTextControl(get_formatted_text), height=window_height))

    app = Application(
        layout=layout,
        key_bindings=bindings,
        mouse_support=False,
        full_screen=False,
    )

    await app.run_async()
    return result_id


async def run_setup_wizard(force: bool = False) -> None:
    """
    Guides the user through setting up essential environment variables for SDRbot.
    Missing variables will be prompted for and saved to the .env file.

    Args:
        force: If True, run the wizard even if credentials already exist.
    """
    # Check if we already have what we need
    has_api_key = (
        os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("GOOGLE_API_KEY")
    )

    if has_api_key and not force:
        # Configuration exists, skip wizard
        return

    console.print(f"[{COLORS['primary']}][bold]SDRbot Setup Wizard[/bold][/{COLORS['primary']}]")
    console.print(
        f"[{COLORS['dim']}]This wizard will help you configure your API keys and credentials.[/]{COLORS['dim']}]"
    )
    console.print(
        f"[{COLORS['dim']}]Values will be saved to your working folders .env file.[/]{COLORS['dim']}\n"
    )

    while True:
        # Refresh env vars in case they changed
        load_dotenv(override=True)

        # Define available services with status
        service_definitions = [
            ("salesforce", "Salesforce (CRM)"),
            ("hubspot", "HubSpot (CRM)"),
            ("pipedrive", "Pipedrive (CRM)"),
            ("zohocrm", "Zoho CRM"),
            ("attio", "Attio (CRM)"),
            ("apollo", "Apollo.io (Data Provider)"),
            ("hunter", "Hunter.io (Data Provider)"),
            ("lusha", "Lusha (Data Provider)"),
            ("tavily", "Tavily (Web Search)"),
            ("postgres", "PostgreSQL (Database)"),
            ("mysql", "MySQL (Database)"),
            ("mongodb", "MongoDB (Database)"),
        ]

        # Build menu items
        # Format: (id, label, status_rich_markup)
        menu_items = []

        # LLM Item
        current_model_config = load_model_config()
        active_provider = current_model_config.get("provider") if current_model_config else None
        active_model = current_model_config.get("model_name") if current_model_config else None

        if active_provider:
            # Make it look nice, e.g. "OpenAI (gpt-5-mini)"
            provider_display = active_provider.capitalize()
            if active_provider == "openai":
                provider_display = "OpenAI"
            elif active_provider == "anthropic":
                provider_display = "Anthropic"
            elif active_provider == "google":
                provider_display = "Google"

            llm_status = f"[green]✓ {provider_display} ({active_model})[/green]"
        else:
            # Fallback check for legacy env vars if config file missing
            llm_configured = bool(
                os.getenv("OPENAI_API_KEY")
                or os.getenv("ANTHROPIC_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or os.getenv("CUSTOM_API_BASE")
            )
            llm_status = (
                "[green]✓ Configured[/green]" if llm_configured else "[red]Not Configured[/red]"
            )

        menu_items.append(("llm", "LLM Provider", llm_status))

        # Track service status to use in selection logic
        service_states = {}

        for code, label in service_definitions:
            configured, enabled = get_service_status(code)
            service_states[code] = (configured, enabled)

            if configured:
                if enabled:
                    status = "[green]✓ Enabled[/green]"
                else:
                    status = "[yellow]• Disabled[/yellow] [dim](Configured)[/dim]"
            else:
                status = "[dim]• Not Configured[/dim]"

            menu_items.append((code, label, status))

        menu_items.append(("done", "Done / Continue", ""))
        menu_items.append(("exit", "Exit", ""))

        # Show the inline menu
        selected_option = await show_menu(menu_items)

        if selected_option is None or selected_option == "exit":
            console.print(f"[{COLORS['dim']}]Exiting setup wizard.[/{COLORS['dim']}]")
            return

        if selected_option == "done":
            # Validate that an LLM provider is configured
            current_config = load_model_config()
            has_llm = current_config and current_config.get("provider")

            # Also check legacy env vars as fallback
            if not has_llm:
                has_llm = bool(
                    os.getenv("OPENAI_API_KEY")
                    or os.getenv("ANTHROPIC_API_KEY")
                    or os.getenv("GOOGLE_API_KEY")
                    or os.getenv("CUSTOM_API_BASE")
                )

            if not has_llm:
                console.print("\n[red][bold]LLM Provider Required[/bold][/red]")
                console.print(
                    "[red]You must configure at least one LLM provider before continuing.[/red]"
                )
                console.print(
                    f"[{COLORS['dim']}]Select 'LLM Provider' from the menu to configure one.[/{COLORS['dim']}]\n"
                )
                continue

            break

        if selected_option == "llm":
            await setup_llm(force=True)
        else:
            # Handle Service Selection
            configured, enabled = service_states[selected_option]

            if not configured:
                # Not configured -> offer to configure directly
                await setup_service(selected_option, force=True)
            else:
                # Configured -> offer toggle and reconfigure
                action_items = []
                if enabled:
                    action_items.append(("disable", "Disable Service", ""))
                else:
                    action_items.append(("enable", "Enable Service", ""))
                action_items.append(("reconfigure", "Reconfigure Credentials", ""))
                action_items.append(("back", "Back", ""))

                action = await show_menu(
                    action_items, title=f"Manage {selected_option.capitalize()}"
                )

                if action == "reconfigure":
                    await setup_service(selected_option, force=True)
                elif action == "enable":
                    enable_service(selected_option, verbose=True)
                elif action == "disable":
                    disable_service(selected_option, verbose=True)
            # "back" or None (escape) -> just continue to main menu

    console.print(f"[{COLORS['primary']}][bold]Setup Complete![/bold][/]")
    console.print(f"[{COLORS['dim']}]You can now run SDRbot.[/]{COLORS['dim']}\n")


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_setup_wizard())
