"""Services setup for the setup wizard."""

import importlib
import os

from sdrbot_cli.config import COLORS, console
from sdrbot_cli.services import disable_service, enable_service
from sdrbot_cli.services.registry import load_config

from .env import get_or_prompt, reload_env_and_settings, save_env_vars
from .menu import CancelledError, show_choice_menu, show_menu

# Service categories and definitions
SERVICE_CATEGORIES = {
    "crms": {
        "label": "CRMs",
        "services": [
            ("salesforce", "Salesforce"),
            ("hubspot", "HubSpot"),
            ("pipedrive", "Pipedrive"),
            ("zohocrm", "Zoho CRM"),
            ("attio", "Attio"),
            ("twenty", "Twenty"),
        ],
    },
    "prospecting": {
        "label": "Prospecting & Enrichment",
        "services": [
            ("apollo", "Apollo.io"),
            ("hunter", "Hunter.io"),
            ("lusha", "Lusha"),
            ("tavily", "Tavily (Web Search)"),
        ],
    },
    "databases": {
        "label": "Databases",
        "services": [
            ("postgres", "PostgreSQL"),
            ("mysql", "MySQL"),
            ("mongodb", "MongoDB"),
        ],
    },
    "email": {
        "label": "Email Services",
        "services": [
            ("gmail", "Gmail"),
        ],
    },
}


def get_service_status(service_name: str) -> tuple[bool, bool]:
    """
    Check service status.

    Returns:
        (is_configured, is_enabled)
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
    elif service_name == "twenty":
        configured = bool(os.getenv("TWENTY_API_KEY"))
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
    elif service_name == "gmail":
        configured = bool(os.getenv("GMAIL_CLIENT_ID") and os.getenv("GMAIL_CLIENT_SECRET"))

    # Check enabled state from registry
    try:
        config = load_config()
        enabled = config.is_enabled(service_name)
    except Exception:
        enabled = False

    return configured, enabled


def get_services_status() -> str:
    """Get overall status string for services."""
    config = load_config()
    enabled_count = 0

    for category in SERVICE_CATEGORIES.values():
        for service_code, _ in category["services"]:
            if config.is_enabled(service_code):
                enabled_count += 1

    if enabled_count > 0:
        return f"[green]✓ {enabled_count} enabled[/green]"
    return "[dim]• None configured[/dim]"


async def setup_services() -> str | None:
    """
    Run the Services setup wizard with categories.

    Returns:
        "back" to return to main menu, None if exited
    """
    try:
        return await _setup_services_impl()
    except CancelledError:
        console.print(f"\n[{COLORS['dim']}]Configuration cancelled.[/{COLORS['dim']}]")
        return "back"


async def _setup_services_impl() -> str | None:
    """Implementation of services setup."""
    while True:
        # Build category menu
        menu_items = []

        for cat_code, cat_info in SERVICE_CATEGORIES.items():
            # Count enabled services in this category
            enabled_count = 0
            config = load_config()
            for service_code, _ in cat_info["services"]:
                if config.is_enabled(service_code):
                    enabled_count += 1

            if enabled_count > 0:
                status = f"[green]{enabled_count} enabled[/green]"
            else:
                status = "[dim]None enabled[/dim]"

            menu_items.append((cat_code, cat_info["label"], status))

        menu_items.append(("---", "──────────────", ""))
        menu_items.append(("back", "← Back", ""))

        selected = await show_menu(menu_items, title="Services")

        if selected == "back" or selected is None:
            return "back"

        # Show services in selected category
        await _setup_category(selected)


async def _setup_category(category_code: str) -> None:
    """Show services in a category."""
    cat_info = SERVICE_CATEGORIES[category_code]

    while True:
        menu_items = []

        for service_code, service_label in cat_info["services"]:
            configured, enabled = get_service_status(service_code)

            if configured:
                if enabled:
                    status = "[green]✓ Enabled[/green]"
                else:
                    status = "[yellow]• Disabled[/yellow]"
            else:
                status = "[dim]• Not Configured[/dim]"

            menu_items.append((service_code, service_label, status))

        menu_items.append(("---", "──────────────", ""))
        menu_items.append(("back", "← Back", ""))

        selected = await show_menu(menu_items, title=cat_info["label"])

        if selected == "back" or selected is None:
            return

        # Configure selected service
        await _configure_service(selected)


async def _configure_service(service_name: str) -> None:
    """Configure a specific service."""
    configured, enabled = get_service_status(service_name)

    if not configured:
        # Not configured -> configure directly
        await setup_service(service_name, force=True)
    else:
        # Configured -> offer toggle and reconfigure
        action_items = []
        if enabled:
            action_items.append(("disable", "Disable Service", ""))
        else:
            action_items.append(("enable", "Enable Service", ""))
        action_items.append(("reconfigure", "Reconfigure Credentials", ""))
        action_items.append(("back", "Back", ""))

        action = await show_menu(action_items, title=f"Manage {service_name.capitalize()}")

        if action == "reconfigure":
            await setup_service(service_name, force=True)
        elif action == "enable":
            enable_service(service_name, verbose=True)
        elif action == "disable":
            disable_service(service_name, verbose=True)


async def setup_service(service_name: str, force: bool = False) -> bool:
    """
    Run setup for a specific service.

    Returns:
        True if configuration was updated.
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
        sf_client_id = await get_or_prompt(
            "SF_CLIENT_ID", "Salesforce Client ID", required=True, force=force
        )
        sf_client_secret = await get_or_prompt(
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

        if sf_client_id and sf_client_secret:
            save_env_vars(env_vars)
            reload_env_and_settings()

            try:
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
                )

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
            hubspot_access_token = await get_or_prompt(
                "HUBSPOT_ACCESS_TOKEN",
                "HubSpot Personal Access Token",
                is_secret=True,
                required=True,
                force=force,
            )
            if hubspot_access_token:
                env_vars["HUBSPOT_ACCESS_TOKEN"] = hubspot_access_token
        else:
            hubspot_client_id = await get_or_prompt(
                "HUBSPOT_CLIENT_ID", "HubSpot Client ID", required=True, force=force
            )
            hubspot_client_secret = await get_or_prompt(
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

            if hubspot_client_id and hubspot_client_secret:
                save_env_vars(env_vars)
                reload_env_and_settings()

                try:
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

                enable_service("hubspot", sync=True, verbose=True)
                return True

    elif service_name == "attio":
        console.print(f"[{COLORS['primary']}]--- Attio Configuration ---[/{COLORS['primary']}]")
        attio_key = await get_or_prompt(
            "ATTIO_API_KEY", "Attio API Key", is_secret=True, required=True, force=force
        )
        if attio_key:
            env_vars["ATTIO_API_KEY"] = attio_key

    elif service_name == "twenty":
        console.print(
            f"[{COLORS['primary']}]--- Twenty CRM Configuration ---[/{COLORS['primary']}]"
        )
        console.print(
            f"[{COLORS['dim']}]Get your API key from Settings > Developers > API Keys in Twenty[/{COLORS['dim']}]"
        )
        twenty_key = await get_or_prompt(
            "TWENTY_API_KEY", "Twenty API Key", is_secret=True, required=True, force=force
        )
        if twenty_key:
            env_vars["TWENTY_API_KEY"] = twenty_key

        # Optional: For self-hosted, set TWENTY_API_URL in .env manually

    elif service_name == "zohocrm":
        console.print(f"[{COLORS['primary']}]--- Zoho CRM Configuration ---[/{COLORS['primary']}]")
        zoho_client_id = await get_or_prompt(
            "ZOHO_CLIENT_ID", "Zoho Client ID", required=True, force=force
        )
        zoho_client_secret = await get_or_prompt(
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

        if zoho_client_id and zoho_client_secret and zoho_region:
            save_env_vars(env_vars)
            reload_env_and_settings()

            try:
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
            pipedrive_api_token = await get_or_prompt(
                "PIPEDRIVE_API_TOKEN",
                "Pipedrive API Token",
                is_secret=True,
                required=True,
                force=force,
            )
            if pipedrive_api_token:
                env_vars["PIPEDRIVE_API_TOKEN"] = pipedrive_api_token
        else:
            pipedrive_client_id = await get_or_prompt(
                "PIPEDRIVE_CLIENT_ID", "Pipedrive Client ID", required=True, force=force
            )
            pipedrive_client_secret = await get_or_prompt(
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

            if pipedrive_client_id and pipedrive_client_secret:
                save_env_vars(env_vars)
                reload_env_and_settings()

                try:
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

                enable_service("pipedrive", sync=True, verbose=True)
                return True

    elif service_name == "lusha":
        console.print(f"[{COLORS['primary']}]--- Lusha Configuration ---[/{COLORS['primary']}]")
        lusha_key = await get_or_prompt(
            "LUSHA_API_KEY", "Lusha API Key", is_secret=True, required=True, force=force
        )
        if lusha_key:
            env_vars["LUSHA_API_KEY"] = lusha_key

    elif service_name == "hunter":
        console.print(f"[{COLORS['primary']}]--- Hunter.io Configuration ---[/{COLORS['primary']}]")
        hunter_key = await get_or_prompt(
            "HUNTER_API_KEY", "Hunter.io API Key", is_secret=True, required=True, force=force
        )
        if hunter_key:
            env_vars["HUNTER_API_KEY"] = hunter_key

    elif service_name == "apollo":
        console.print(f"[{COLORS['primary']}]--- Apollo.io Configuration ---[/{COLORS['primary']}]")
        apollo_key = await get_or_prompt(
            "APOLLO_API_KEY", "Apollo API Key", is_secret=True, required=True, force=force
        )
        if apollo_key:
            env_vars["APOLLO_API_KEY"] = apollo_key

    elif service_name == "tavily":
        console.print(f"[{COLORS['primary']}]--- Tavily Configuration ---[/{COLORS['primary']}]")
        tavily_key = await get_or_prompt(
            "TAVILY_API_KEY", "Tavily API Key", is_secret=True, required=True, force=force
        )
        if tavily_key:
            env_vars["TAVILY_API_KEY"] = tavily_key

    elif service_name == "postgres":
        console.print(
            f"[{COLORS['primary']}]--- PostgreSQL Configuration ---[/{COLORS['primary']}]"
        )
        pg_host = await get_or_prompt(
            "POSTGRES_HOST", "PostgreSQL Host", default="localhost", required=True, force=force
        )
        pg_port = await get_or_prompt(
            "POSTGRES_PORT", "PostgreSQL Port", default="5432", required=True, force=force
        )
        pg_user = await get_or_prompt(
            "POSTGRES_USER", "PostgreSQL User", required=True, force=force
        )
        pg_pass = await get_or_prompt(
            "POSTGRES_PASSWORD", "PostgreSQL Password", is_secret=True, required=True, force=force
        )
        pg_db = await get_or_prompt(
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
        mysql_host = await get_or_prompt(
            "MYSQL_HOST", "MySQL Host", default="localhost", required=True, force=force
        )
        mysql_port = await get_or_prompt(
            "MYSQL_PORT", "MySQL Port", default="3306", required=True, force=force
        )
        mysql_user = await get_or_prompt("MYSQL_USER", "MySQL User", required=True, force=force)
        mysql_pass = await get_or_prompt(
            "MYSQL_PASSWORD", "MySQL Password", is_secret=True, required=True, force=force
        )
        mysql_db = await get_or_prompt(
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
        mongo_uri = await get_or_prompt(
            "MONGODB_URI",
            "MongoDB Connection URI",
            default="mongodb://localhost:27017",
            is_secret=True,
            required=True,
            force=force,
        )
        mongo_db = await get_or_prompt(
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

    elif service_name == "gmail":
        console.print(f"[{COLORS['primary']}]--- Gmail Configuration ---[/{COLORS['primary']}]")
        console.print(
            f"[{COLORS['dim']}]Create OAuth credentials at console.cloud.google.com[/{COLORS['dim']}]"
        )
        console.print(
            f"[{COLORS['dim']}]Enable Gmail API and create a Desktop app OAuth client[/{COLORS['dim']}]"
        )
        gmail_client_id = await get_or_prompt(
            "GMAIL_CLIENT_ID", "Gmail Client ID", required=True, force=force
        )
        gmail_client_secret = await get_or_prompt(
            "GMAIL_CLIENT_SECRET",
            "Gmail Client Secret",
            is_secret=True,
            required=True,
            force=force,
        )

        if gmail_client_id:
            env_vars["GMAIL_CLIENT_ID"] = gmail_client_id
        if gmail_client_secret:
            env_vars["GMAIL_CLIENT_SECRET"] = gmail_client_secret

        if gmail_client_id and gmail_client_secret:
            save_env_vars(env_vars)
            reload_env_and_settings()

            try:
                import sdrbot_cli.auth.gmail as gmail_auth

                importlib.reload(gmail_auth)
                gmail_auth.login()
                console.print(
                    f"[{COLORS['primary']}]Gmail authentication complete![/{COLORS['primary']}]"
                )
            except Exception as e:
                console.print(f"[red]Gmail authentication failed: {e}[/red]")
                console.print(
                    f"[{COLORS['dim']}]You can authenticate later when you first use Gmail.[/{COLORS['dim']}]"
                )

            enable_service("gmail", sync=False, verbose=True)
            return True

    else:
        console.print(f"[red]Unknown service: {service_name}[/red]")
        return False

    if env_vars:
        save_env_vars(env_vars)
        reload_env_and_settings()
        enable_service(service_name, sync=True, verbose=True)
        return True

    return False
