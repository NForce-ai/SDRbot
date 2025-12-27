"""Configuration, constants, and model creation for the CLI."""

import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

import dotenv
from langchain_core.language_models import BaseChatModel
from rich.console import Console
from rich.theme import Theme

# Load .env ONLY from current working directory to avoid accidental parent config inheritance
dotenv.load_dotenv(Path.cwd() / ".env")

# Color scheme
COLORS = {
    "primary": "#10b981",
    "dim": "#9ca3af",  # Lighter gray for better visibility on Windows/macOS terminals
    "user": "#ffffff",
    "agent": "#10b981",
    "thinking": "#34d399",
    "tool": "#fbbf24",
    "command": "#60a5fa",
}

# ASCII art banner
DEEP_AGENTS_ASCII = """
 ███████╗██████╗ ██████╗ ██████╗  ██████╗ ████████╗
 ██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝
 ███████╗██║  ██║██████╔╝██████╔╝██║   ██║   ██║
 ╚════██║██║  ██║██╔══██╗██╔══██╗██║   ██║   ██║
 ███████║██████╔╝██║  ██║██████╔╝╚██████╔╝   ██║
 ╚══════╝╚═════╝ ╚═╝  ╚═╝╚═════╝  ╚═════╝    ╚═╝

[VERSION_PLACEHOLDER]
"""

# Interactive commands (shared between CLI and TUI)
COMMANDS = {
    "clear": "Clear screen and reset conversation",
    "help": "Show help information",
    "tokens": "Show token usage for current session",
    "quit": "Exit the CLI",
    "exit": "Exit the CLI",
    "setup": "Re-run the setup wizard",
    "sync": "Re-sync service schemas (hubspot, salesforce, attio)",
}

# TUI-specific commands (superset of COMMANDS)
TUI_COMMANDS = {
    "help": "Show help information",
    "tokens": "Show token usage for current session",
    "tools": "Show tools management screen",
    "models": "Open model configuration",
    "services": "Open services setup screen",
    "mcp": "Open MCP server configuration",
    "setup": "Re-run the setup wizard",
    "tracing": "Open tracing setup screen",
    "agents": "Open agents management screen",
    "skills": "Open skills management screen",
    "sync": "Sync service schemas",
    "clear": "Clear screen and reset conversation",
    "quit": "Exit the application",
    "exit": "Exit the application",
}


# Maximum argument length for display
MAX_ARG_LENGTH = 150

# Agent configuration
config = {"recursion_limit": 1000}

# Custom theme to override dim style for better visibility on Windows/macOS terminals
_theme = Theme({"dim": COLORS["dim"]})

# Rich console instance
console = Console(highlight=False, theme=_theme)


class ModelConfig(TypedDict, total=False):
    """Structure for the active model configuration file.

    Providers:
    - openai, anthropic, google: Cloud providers with API keys
    - ollama: Local Ollama server
    - vllm: Local vLLM server
    - azure: Azure OpenAI Service
    - custom: Generic OpenAI-compatible endpoint
    """

    provider: str  # Required: openai, anthropic, google, ollama, vllm, azure, custom
    model_name: str  # Required: model identifier
    api_base: str | None  # Base URL for custom/vllm endpoints
    # Azure-specific fields
    azure_endpoint: str | None  # Azure OpenAI endpoint URL
    azure_deployment: str | None  # Azure deployment name
    azure_api_version: str | None  # Azure API version


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    config_dir = Path.cwd() / ".sdrbot"
    config_dir.mkdir(exist_ok=True)
    return config_dir


def _load_raw_model_config() -> dict:
    """Load raw model config file."""
    config_file = get_config_dir() / "model.json"
    if not config_file.exists():
        return {"active_provider": None, "providers": {}}

    try:
        return json.loads(config_file.read_text())
    except Exception:
        return {"active_provider": None, "providers": {}}


def load_model_config() -> ModelConfig | None:
    """Load the active model configuration from .sdrbot/model.json."""
    data = _load_raw_model_config()
    active_provider = data.get("active_provider")
    if not active_provider:
        return None

    providers = data.get("providers", {})
    provider_config = providers.get(active_provider, {})

    if not provider_config:
        return None

    # Build ModelConfig with provider included
    config: ModelConfig = {"provider": active_provider, **provider_config}
    return config


def load_provider_config(provider: str) -> dict:
    """Load saved configuration for a specific provider (for pre-filling forms).

    Returns empty dict if no saved config exists for that provider.
    """
    data = _load_raw_model_config()
    return data.get("providers", {}).get(provider, {})


def save_model_config(
    provider: str,
    model_name: str,
    api_base: str | None = None,
    *,
    azure_endpoint: str | None = None,
    azure_deployment: str | None = None,
    azure_api_version: str | None = None,
) -> None:
    """Save the active model configuration.

    Saves the config for this provider and sets it as active.
    Previously saved configs for other providers are preserved.

    Args:
        provider: Provider name (openai, anthropic, google, ollama, vllm, azure, custom)
        model_name: Model identifier
        api_base: Base URL for custom/vllm/ollama endpoints
        azure_endpoint: Azure OpenAI endpoint URL
        azure_deployment: Azure deployment name
        azure_api_version: Azure API version
    """
    # Load existing config to preserve other providers
    data = _load_raw_model_config()

    # Build provider config (without provider key - that's stored separately)
    provider_config: dict = {"model_name": model_name}
    if api_base:
        provider_config["api_base"] = api_base
    if azure_endpoint:
        provider_config["azure_endpoint"] = azure_endpoint
    if azure_deployment:
        provider_config["azure_deployment"] = azure_deployment
    if azure_api_version:
        provider_config["azure_api_version"] = azure_api_version

    # Update the providers dict
    if "providers" not in data:
        data["providers"] = {}
    data["providers"][provider] = provider_config
    data["active_provider"] = provider

    config_file = get_config_dir() / "model.json"
    config_file.write_text(json.dumps(data, indent=2))


def _find_project_root(start_path: Path | None = None) -> Path | None:
    """Find the project root by looking for .git directory.

    Walks up the directory tree from start_path (or cwd) looking for a .git
    directory, which indicates the project root.

    Args:
        start_path: Directory to start searching from. Defaults to current working directory.

    Returns:
        Path to the project root if found, None otherwise.
    """
    current = Path(start_path or Path.cwd()).resolve()

    # Walk up the directory tree
    for parent in [current, *list(current.parents)]:
        git_dir = parent / ".git"
        if git_dir.exists():
            return parent

    return None


@dataclass
class Settings:
    """Global settings and environment detection for deepagents-cli.

    This class is initialized once at startup and provides access to:
    - Available models and API keys
    - Current project information
    - Tool availability (e.g., Tavily)
    - File system paths

    Attributes:
        project_root: Current project root directory (if in a git project)

        openai_api_key: OpenAI API key if available
        anthropic_api_key: Anthropic API key if available
        tavily_api_key: Tavily API key if available
    """

    # API keys
    openai_api_key: str | None
    anthropic_api_key: str | None
    google_api_key: str | None
    tavily_api_key: str | None

    # Salesforce Config
    sf_client_id: str | None
    sf_client_secret: str | None

    # HubSpot Config
    hubspot_client_id: str | None
    hubspot_client_secret: str | None
    hubspot_access_token: str | None

    # Zoho CRM Config
    zoho_client_id: str | None
    zoho_client_secret: str | None
    zoho_region: str | None

    # Pipedrive Config
    pipedrive_api_token: str | None
    pipedrive_client_id: str | None
    pipedrive_client_secret: str | None

    # Attio Config
    attio_api_key: str | None

    # Twenty Config
    twenty_api_key: str | None
    twenty_api_url: str | None  # For self-hosted instances

    # Lusha Config
    lusha_api_key: str | None

    # Hunter Config
    hunter_api_key: str | None

    # Apollo Config
    apollo_api_key: str | None

    # PostgreSQL Config
    postgres_host: str | None
    postgres_port: str | None
    postgres_user: str | None
    postgres_password: str | None
    postgres_db: str | None
    postgres_ssl_mode: str | None  # disable, require, verify-ca, verify-full

    # MySQL Config
    mysql_host: str | None
    mysql_port: str | None
    mysql_user: str | None
    mysql_password: str | None
    mysql_db: str | None
    mysql_ssl: bool  # Enable SSL (default: False)

    # MongoDB Config
    mongodb_uri: str | None
    mongodb_db: str | None
    mongodb_tls: bool  # Enable TLS (default: False)

    # Tracing Config
    langsmith_api_key: str | None
    langsmith_project: str | None
    langfuse_public_key: str | None
    langfuse_secret_key: str | None
    langfuse_host: str | None  # Optional, defaults to cloud
    opik_api_key: str | None
    opik_workspace: str | None
    opik_project: str | None

    # Custom Model Config
    custom_api_base: str | None
    custom_api_key: str | None
    custom_model_name: str | None

    # Azure OpenAI
    azure_api_key: str | None

    # HuggingFace
    huggingface_api_key: str | None

    # Project information
    project_root: Path | None

    @classmethod
    def from_environment(cls, *, start_path: Path | None = None) -> "Settings":
        """Create settings by detecting the current environment.

        Args:
            start_path: Directory to start project detection from (defaults to cwd)

        Returns:
            Settings instance with detected configuration
        """
        # Detect API keys
        openai_key = os.environ.get("OPENAI_API_KEY")
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        google_key = os.environ.get("GOOGLE_API_KEY")
        tavily_key = os.environ.get("TAVILY_API_KEY")

        # Custom Model Config
        custom_base = os.environ.get("CUSTOM_API_BASE")
        custom_key = os.environ.get("CUSTOM_API_KEY")
        custom_model = os.environ.get("CUSTOM_MODEL_NAME")

        # Azure OpenAI
        azure_key = os.environ.get("AZURE_OPENAI_API_KEY")

        # HuggingFace
        huggingface_key = os.environ.get("HUGGINGFACE_API_KEY")

        sf_client_id = os.environ.get("SF_CLIENT_ID")
        sf_client_secret = os.environ.get("SF_CLIENT_SECRET")

        hubspot_client_id = os.environ.get("HUBSPOT_CLIENT_ID")
        hubspot_client_secret = os.environ.get("HUBSPOT_CLIENT_SECRET")
        hubspot_access_token = os.environ.get("HUBSPOT_ACCESS_TOKEN")

        zoho_client_id = os.environ.get("ZOHO_CLIENT_ID")
        zoho_client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
        zoho_region = os.environ.get("ZOHO_REGION")

        pipedrive_api_token = os.environ.get("PIPEDRIVE_API_TOKEN")
        pipedrive_client_id = os.environ.get("PIPEDRIVE_CLIENT_ID")
        pipedrive_client_secret = os.environ.get("PIPEDRIVE_CLIENT_SECRET")

        attio_api_key = os.environ.get("ATTIO_API_KEY")
        twenty_api_key = os.environ.get("TWENTY_API_KEY")
        twenty_api_url = os.environ.get("TWENTY_API_URL")
        lusha_api_key = os.environ.get("LUSHA_API_KEY")
        hunter_api_key = os.environ.get("HUNTER_API_KEY")
        apollo_api_key = os.environ.get("APOLLO_API_KEY")

        # Postgres
        postgres_host = os.environ.get("POSTGRES_HOST")
        postgres_port = os.environ.get("POSTGRES_PORT")
        postgres_user = os.environ.get("POSTGRES_USER")
        postgres_password = os.environ.get("POSTGRES_PASSWORD")
        postgres_db = os.environ.get("POSTGRES_DB")
        postgres_ssl_mode = os.environ.get("POSTGRES_SSL_MODE")

        # MySQL
        mysql_host = os.environ.get("MYSQL_HOST")
        mysql_port = os.environ.get("MYSQL_PORT")
        mysql_user = os.environ.get("MYSQL_USER")
        mysql_password = os.environ.get("MYSQL_PASSWORD")
        mysql_db = os.environ.get("MYSQL_DB")
        mysql_ssl = os.environ.get("MYSQL_SSL", "").lower() == "true"

        # MongoDB
        mongodb_uri = os.environ.get("MONGODB_URI")
        mongodb_db = os.environ.get("MONGODB_DB")
        mongodb_tls = os.environ.get("MONGODB_TLS", "").lower() == "true"

        # Tracing
        langsmith_api_key = os.environ.get("LANGSMITH_API_KEY")
        langsmith_project = os.environ.get("LANGSMITH_PROJECT")
        langfuse_public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        langfuse_secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        langfuse_host = os.environ.get("LANGFUSE_HOST")
        opik_api_key = os.environ.get("OPIK_API_KEY")
        opik_workspace = os.environ.get("OPIK_WORKSPACE")
        opik_project = os.environ.get("OPIK_PROJECT")

        # Detect project
        project_root = _find_project_root(start_path)

        return cls(
            openai_api_key=openai_key,
            anthropic_api_key=anthropic_key,
            google_api_key=google_key,
            tavily_api_key=tavily_key,
            sf_client_id=sf_client_id,
            sf_client_secret=sf_client_secret,
            hubspot_client_id=hubspot_client_id,
            hubspot_client_secret=hubspot_client_secret,
            hubspot_access_token=hubspot_access_token,
            zoho_client_id=zoho_client_id,
            zoho_client_secret=zoho_client_secret,
            zoho_region=zoho_region,
            pipedrive_api_token=pipedrive_api_token,
            pipedrive_client_id=pipedrive_client_id,
            pipedrive_client_secret=pipedrive_client_secret,
            attio_api_key=attio_api_key,
            twenty_api_key=twenty_api_key,
            twenty_api_url=twenty_api_url,
            lusha_api_key=lusha_api_key,
            hunter_api_key=hunter_api_key,
            apollo_api_key=apollo_api_key,
            postgres_host=postgres_host,
            postgres_port=postgres_port,
            postgres_user=postgres_user,
            postgres_password=postgres_password,
            postgres_db=postgres_db,
            postgres_ssl_mode=postgres_ssl_mode,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_password=mysql_password,
            mysql_db=mysql_db,
            mysql_ssl=mysql_ssl,
            mongodb_uri=mongodb_uri,
            mongodb_db=mongodb_db,
            mongodb_tls=mongodb_tls,
            langsmith_api_key=langsmith_api_key,
            langsmith_project=langsmith_project,
            langfuse_public_key=langfuse_public_key,
            langfuse_secret_key=langfuse_secret_key,
            langfuse_host=langfuse_host,
            opik_api_key=opik_api_key,
            opik_workspace=opik_workspace,
            opik_project=opik_project,
            custom_api_base=custom_base,
            custom_api_key=custom_key,
            custom_model_name=custom_model,
            azure_api_key=azure_key,
            huggingface_api_key=huggingface_key,
            project_root=project_root,
        )

    def reload(self) -> None:
        """Reload settings from current environment variables."""
        new_settings = Settings.from_environment()
        self.openai_api_key = new_settings.openai_api_key
        self.anthropic_api_key = new_settings.anthropic_api_key
        self.google_api_key = new_settings.google_api_key
        self.tavily_api_key = new_settings.tavily_api_key
        self.sf_client_id = new_settings.sf_client_id
        self.sf_client_secret = new_settings.sf_client_secret
        self.hubspot_client_id = new_settings.hubspot_client_id
        self.hubspot_client_secret = new_settings.hubspot_client_secret
        self.hubspot_access_token = new_settings.hubspot_access_token
        self.zoho_client_id = new_settings.zoho_client_id
        self.zoho_client_secret = new_settings.zoho_client_secret
        self.zoho_region = new_settings.zoho_region
        self.pipedrive_api_token = new_settings.pipedrive_api_token
        self.pipedrive_client_id = new_settings.pipedrive_client_id
        self.pipedrive_client_secret = new_settings.pipedrive_client_secret
        self.attio_api_key = new_settings.attio_api_key
        self.twenty_api_key = new_settings.twenty_api_key
        self.twenty_api_url = new_settings.twenty_api_url
        self.lusha_api_key = new_settings.lusha_api_key
        self.hunter_api_key = new_settings.hunter_api_key
        self.apollo_api_key = new_settings.apollo_api_key
        self.postgres_host = new_settings.postgres_host
        self.postgres_port = new_settings.postgres_port
        self.postgres_user = new_settings.postgres_user
        self.postgres_password = new_settings.postgres_password
        self.postgres_db = new_settings.postgres_db
        self.postgres_ssl_mode = new_settings.postgres_ssl_mode
        self.mysql_host = new_settings.mysql_host
        self.mysql_port = new_settings.mysql_port
        self.mysql_user = new_settings.mysql_user
        self.mysql_password = new_settings.mysql_password
        self.mysql_db = new_settings.mysql_db
        self.mysql_ssl = new_settings.mysql_ssl
        self.mongodb_uri = new_settings.mongodb_uri
        self.mongodb_db = new_settings.mongodb_db
        self.mongodb_tls = new_settings.mongodb_tls
        self.langsmith_api_key = new_settings.langsmith_api_key
        self.langsmith_project = new_settings.langsmith_project
        self.langfuse_public_key = new_settings.langfuse_public_key
        self.langfuse_secret_key = new_settings.langfuse_secret_key
        self.langfuse_host = new_settings.langfuse_host
        self.opik_api_key = new_settings.opik_api_key
        self.opik_workspace = new_settings.opik_workspace
        self.opik_project = new_settings.opik_project
        self.custom_api_base = new_settings.custom_api_base
        self.custom_api_key = new_settings.custom_api_key
        self.custom_model_name = new_settings.custom_model_name
        self.azure_api_key = new_settings.azure_api_key
        self.huggingface_api_key = new_settings.huggingface_api_key
        self.project_root = new_settings.project_root

    @property
    def has_openai(self) -> bool:
        """Check if OpenAI API key is configured."""
        return self.openai_api_key is not None

    @property
    def has_anthropic(self) -> bool:
        """Check if Anthropic API key is configured."""
        return self.anthropic_api_key is not None

    @property
    def has_google(self) -> bool:
        """Check if Google API key is configured."""
        return self.google_api_key is not None

    @property
    def has_custom(self) -> bool:
        """Check if Custom Model is configured."""
        return self.custom_api_base is not None and self.custom_model_name is not None

    @property
    def has_tavily(self) -> bool:
        """Check if Tavily API key is configured."""
        return self.tavily_api_key is not None

    @property
    def has_salesforce(self) -> bool:
        """Check if Salesforce credentials are configured."""
        return self.sf_client_id is not None

    @property
    def has_hubspot(self) -> bool:
        """Check if HubSpot credentials are configured."""
        return self.hubspot_access_token is not None or self.hubspot_client_id is not None

    @property
    def has_zohocrm(self) -> bool:
        """Check if Zoho CRM credentials are configured."""
        return (
            self.zoho_client_id is not None
            and self.zoho_client_secret is not None
            and self.zoho_region is not None
        )

    @property
    def has_pipedrive(self) -> bool:
        """Check if Pipedrive credentials are configured."""
        return self.pipedrive_api_token is not None or (
            self.pipedrive_client_id is not None and self.pipedrive_client_secret is not None
        )

    @property
    def has_attio(self) -> bool:
        """Check if Attio API key is configured."""
        return self.attio_api_key is not None

    @property
    def has_twenty(self) -> bool:
        """Check if Twenty API key is configured."""
        return self.twenty_api_key is not None

    @property
    def has_lusha(self) -> bool:
        """Check if Lusha API key is configured."""
        return self.lusha_api_key is not None

    @property
    def has_hunter(self) -> bool:
        """Check if Hunter API key is configured."""
        return self.hunter_api_key is not None

    @property
    def has_apollo(self) -> bool:
        """Check if Apollo API key is configured."""
        return self.apollo_api_key is not None

    @property
    def has_postgres(self) -> bool:
        """Check if PostgreSQL credentials are configured."""
        return self.postgres_host is not None and self.postgres_db is not None

    @property
    def has_mysql(self) -> bool:
        """Check if MySQL credentials are configured."""
        return self.mysql_host is not None and self.mysql_db is not None

    @property
    def has_mongodb(self) -> bool:
        """Check if MongoDB credentials are configured."""
        return self.mongodb_uri is not None and self.mongodb_db is not None

    @property
    def has_langsmith(self) -> bool:
        """Check if LangSmith API key is configured."""
        return self.langsmith_api_key is not None

    @property
    def has_langfuse(self) -> bool:
        """Check if Langfuse credentials are configured."""
        return self.langfuse_public_key is not None and self.langfuse_secret_key is not None

    @property
    def has_opik(self) -> bool:
        """Check if Opik API key is configured."""
        return self.opik_api_key is not None

    def has_service_credentials(self, service_name: str) -> bool:
        """Check if credentials exist for a specific service.

        Args:
            service_name: Name of the service to check.

        Returns:
            True if credentials are configured for the service.
        """
        checks = {
            "hubspot": self.has_hubspot,
            "salesforce": self.has_salesforce,
            "attio": self.has_attio,
            "twenty": self.has_twenty,
            "zohocrm": self.has_zohocrm,
            "pipedrive": self.has_pipedrive,
            "lusha": self.has_lusha,
            "hunter": self.has_hunter,
            "apollo": self.has_apollo,
            "postgres": self.has_postgres,
            "mysql": self.has_mysql,
            "mongodb": self.has_mongodb,
            "tavily": self.has_tavily,
            "langsmith": self.has_langsmith,
            "langfuse": self.has_langfuse,
            "opik": self.has_opik,
        }
        return checks.get(service_name, False)

    @property
    def has_project(self) -> bool:
        """Check if currently in a git project."""
        return self.project_root is not None

    @property
    def agents_dir(self) -> Path:
        """Get the agents directory in current working directory.

        Returns:
            Path to ./agents/
        """
        return Path.cwd() / "agents"

    @staticmethod
    def _is_valid_agent_name(agent_name: str) -> bool:
        """Validate prevent invalid filesystem paths and security issues."""
        if not agent_name or not agent_name.strip():
            return False
        # Allow only alphanumeric, hyphens, underscores, and whitespace
        return bool(re.match(r"^[a-zA-Z0-9_\-\s]+$", agent_name))

    def get_agent_dir(self, agent_name: str) -> Path:
        """Get the directory for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ./agents/{agent_name}/
        """
        if not self._is_valid_agent_name(agent_name):
            msg = (
                f"Invalid agent name: {agent_name!r}. "
                "Agent names can only contain letters, numbers, hyphens, underscores, and spaces."
            )
            raise ValueError(msg)
        return self.agents_dir / agent_name

    def get_agent_prompt_path(self, agent_name: str) -> Path:
        """Get the path to an agent's prompt file.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ./agents/{agent_name}/prompt.md
        """
        return self.get_agent_dir(agent_name) / "prompt.md"

    def get_agent_memory_path(self, agent_name: str) -> Path:
        """Get the path to an agent's memory file.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ./agents/{agent_name}/memory.md
        """
        return self.get_agent_dir(agent_name) / "memory.md"

    def ensure_agent_dir(self, agent_name: str) -> Path:
        """Ensure agent directory exists.

        Creates ./agents/{agent_name}/ if it doesn't exist.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ./agents/{agent_name}/
        """
        agent_dir = self.get_agent_dir(agent_name)
        agent_dir.mkdir(parents=True, exist_ok=True)
        return agent_dir

    def ensure_agent_prompt(self, agent_name: str, default_content: str) -> Path:
        """Ensure agent prompt file exists, creating with default content if needed.

        Creates ./agents/{agent_name}/ directory and prompt.md if they don't exist.

        Args:
            agent_name: Name of the agent
            default_content: Content to write if file doesn't exist

        Returns:
            Path to ./agents/{agent_name}/prompt.md
        """
        self.ensure_agent_dir(agent_name)
        prompt_path = self.get_agent_prompt_path(agent_name)
        if not prompt_path.exists():
            prompt_path.write_text(default_content)
        return prompt_path

    def ensure_agent_memory(self, agent_name: str, default_content: str = "") -> Path:
        """Ensure agent memory file exists, creating with default content if needed.

        Creates ./agents/{agent_name}/ directory and memory.md if they don't exist.

        Args:
            agent_name: Name of the agent
            default_content: Content to write if file doesn't exist (default: empty)

        Returns:
            Path to ./agents/{agent_name}/memory.md
        """
        self.ensure_agent_dir(agent_name)
        memory_path = self.get_agent_memory_path(agent_name)
        if not memory_path.exists():
            memory_path.write_text(default_content)
        return memory_path

    def get_skills_dir(self) -> Path:
        """Get shared skills directory path.

        Returns:
            Path to ./skills/
        """
        return Path.cwd() / "skills"

    def get_user_skills_dir(self, agent: str | None = None) -> Path:
        """Get user skills directory path.

        For SDRbot, user skills are stored in ./skills/ (same as shared skills).
        The agent parameter is accepted for API compatibility but ignored.

        Args:
            agent: Agent identifier (ignored, kept for API compatibility)

        Returns:
            Path to ./skills/
        """
        return self.get_skills_dir()

    def ensure_skills_dir(self) -> Path:
        """Ensure shared skills directory exists.

        Returns:
            Path to ./skills/
        """
        skills_dir = self.get_skills_dir()
        skills_dir.mkdir(parents=True, exist_ok=True)
        return skills_dir

    def get_project_skills_dir(self) -> Path | None:
        """Get project-level skills directory path.

        Returns:
            Path to {project_root}/.deepagents/skills/, or None if not in a project
        """
        if not self.project_root:
            return None
        return self.project_root / ".deepagents" / "skills"

    def ensure_project_skills_dir(self) -> Path | None:
        """Ensure project-level skills directory exists and return its path.

        Returns:
            Path to {project_root}/.deepagents/skills/, or None if not in a project
        """
        if not self.project_root:
            return None
        skills_dir = self.get_project_skills_dir()
        skills_dir.mkdir(parents=True, exist_ok=True)
        return skills_dir

    def get_files_dir(self) -> Path:
        """Get agent-generated files directory path.

        This is where the agent should save exports, reports, and other generated files.

        Returns:
            Path to ./files/
        """
        return Path.cwd() / "files"

    def ensure_files_dir(self) -> Path:
        """Ensure agent-generated files directory exists.

        Returns:
            Path to ./files/
        """
        files_dir = self.get_files_dir()
        files_dir.mkdir(parents=True, exist_ok=True)
        return files_dir

    def get_generated_dir(self) -> Path:
        """Get generated tools directory path.

        This is where schema-synced tools are generated (e.g., hubspot_tools.py).

        Returns:
            Path to ./generated/
        """
        return Path.cwd() / "generated"

    def ensure_generated_dir(self) -> Path:
        """Ensure generated tools directory exists.

        Returns:
            Path to ./generated/
        """
        generated_dir = self.get_generated_dir()
        generated_dir.mkdir(parents=True, exist_ok=True)
        return generated_dir


# Global settings instance (initialized once)
settings = Settings.from_environment()


class SessionState:
    """Holds mutable session state (auto-approve mode, agent, etc)."""

    def __init__(
        self, auto_approve: bool = False, no_splash: bool = False, is_tui: bool = False
    ) -> None:
        self.auto_approve = auto_approve
        self.no_splash = no_splash
        self.is_tui = is_tui
        self.exit_hint_until: float | None = None
        self.exit_hint_handle = None
        self.thread_id = str(uuid.uuid4())
        # Agent and backend can be swapped at runtime for hot-reloading
        self.agent = None
        self.backend = None
        self.checkpointer = None  # Preserved across reloads to maintain conversation history
        self.tool_count = 0  # Number of tools loaded
        self.skill_count = 0  # Number of skills loaded
        # Reload callback - set by main.py to allow commands to trigger agent reload
        self._reload_callback = None
        # Post-reload callback - called after agent reload completes (for UI updates)
        self._post_reload_callback = None

    def toggle_auto_approve(self) -> bool:
        """Toggle auto-approve and return new state."""
        self.auto_approve = not self.auto_approve
        return self.auto_approve

    def set_reload_callback(self, callback) -> None:
        """Set the callback function for reloading the agent."""
        self._reload_callback = callback

    def set_post_reload_callback(self, callback) -> None:
        """Set the callback function called after agent reload completes."""
        self._post_reload_callback = callback

    async def reload_agent(self) -> bool:
        """Reload the agent with updated tools/config.

        Returns:
            True if reload succeeded, False if no callback set.
        """
        if self._reload_callback:
            import inspect

            if inspect.iscoroutinefunction(self._reload_callback):
                await self._reload_callback()
            else:
                self._reload_callback()

            # Call post-reload callback (e.g., to update tool count in UI)
            if self._post_reload_callback:
                self._post_reload_callback()

            return True
        return False


def get_default_coding_instructions() -> str:
    """Get the default coding agent instructions.

    These are the immutable base instructions that cannot be modified by the agent.
    Long-term memory (agent.md) is handled separately by the middleware.
    """
    default_prompt_path = Path(__file__).parent / "default_agent_prompt.md"
    return default_prompt_path.read_text()


def create_model() -> BaseChatModel:
    """Create the appropriate model based on available API keys.

    Uses the global settings instance to determine which model to create.

    Returns:
        ChatModel instance (OpenAI or Anthropic)

    Raises:
        SystemExit if no API key is configured
    """
    # 1. Try to load explicit configuration from model.json
    model_config = load_model_config()

    if model_config:
        provider = model_config["provider"]
        model_name = model_config["model_name"]

        if provider == "ollama":
            from langchain_openai import ChatOpenAI

            api_base = model_config.get("api_base") or "http://localhost:11434/v1"
            console.print(f"[dim]Using Ollama: {model_name}[/dim]")
            return ChatOpenAI(
                base_url=api_base,
                api_key="ollama",  # Ollama doesn't require a real key
                model=model_name,
                stream_usage=True,
            )

        if provider == "vllm":
            from langchain_openai import ChatOpenAI

            api_base = model_config.get("api_base") or "http://localhost:8000/v1"
            console.print(f"[dim]Using vLLM: {model_name}[/dim]")
            return ChatOpenAI(
                base_url=api_base,
                api_key=settings.custom_api_key or "dummy",
                model=model_name,
                stream_usage=True,
            )

        if provider == "huggingface":
            from langchain_openai import ChatOpenAI

            api_base = model_config.get("api_base")
            console.print(f"[dim]Using HuggingFace: {model_name}[/dim]")
            return ChatOpenAI(
                base_url=api_base,
                api_key=settings.huggingface_api_key or "dummy",
                model=model_name,
                stream_usage=True,
            )

        if provider == "bedrock":
            from langchain_aws import ChatBedrock

            console.print(f"[dim]Using Amazon Bedrock: {model_name}[/dim]")
            return ChatBedrock(
                model_id=model_name,
                region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            )

        if provider == "azure":
            from langchain_openai import AzureChatOpenAI

            azure_endpoint = model_config.get("azure_endpoint")
            azure_deployment = model_config.get("azure_deployment")
            azure_api_version = model_config.get("azure_api_version") or "2024-02-15-preview"

            if not azure_endpoint or not azure_deployment:
                console.print(
                    "[bold red]Error:[/bold red] Azure selected but endpoint/deployment not configured"
                )
                sys.exit(1)
            if not settings.azure_api_key:
                console.print(
                    "[bold red]Error:[/bold red] Azure selected but AZURE_OPENAI_API_KEY missing in .env"
                )
                sys.exit(1)

            console.print(f"[dim]Using Azure OpenAI: {azure_deployment}[/dim]")
            return AzureChatOpenAI(
                azure_endpoint=azure_endpoint,
                azure_deployment=azure_deployment,
                api_version=azure_api_version,
                api_key=settings.azure_api_key,
                stream_usage=True,
            )

        if provider == "custom":
            from langchain_openai import ChatOpenAI

            console.print(f"[dim]Using Custom Endpoint: {model_name}[/dim]")
            return ChatOpenAI(
                base_url=model_config.get("api_base"),
                api_key=settings.custom_api_key or "dummy",
                model=model_name,
                stream_usage=True,
            )

        if provider == "openai":
            if not settings.has_openai:
                console.print(
                    "[bold red]Error:[/bold red] OpenAI selected but OPENAI_API_KEY missing in .env"
                )
                sys.exit(1)
            from langchain_openai import ChatOpenAI

            console.print(f"[dim]Using OpenAI model: {model_name}[/dim]")
            return ChatOpenAI(model=model_name, stream_usage=True)

        if provider == "anthropic":
            if not settings.has_anthropic:
                console.print(
                    "[bold red]Error:[/bold red] Anthropic selected but ANTHROPIC_API_KEY missing in .env"
                )
                sys.exit(1)
            from langchain_anthropic import ChatAnthropic

            console.print(f"[dim]Using Anthropic model: {model_name}[/dim]")
            return ChatAnthropic(
                model_name=model_name,
                max_tokens=20_000,  # type: ignore[arg-type]
                stream_usage=True,
            )

        if provider == "google":
            if not settings.has_google:
                console.print(
                    "[bold red]Error:[/bold red] Google selected but GOOGLE_API_KEY missing in .env"
                )
                sys.exit(1)
            from langchain_google_genai import ChatGoogleGenerativeAI

            console.print(f"[dim]Using Google Gemini model: {model_name}[/dim]")
            return ChatGoogleGenerativeAI(
                model=model_name,
                temperature=0,
                max_tokens=None,
            )

    # 2. Fallback: Legacy/Implicit detection based on env vars
    if settings.has_custom:
        from langchain_openai import ChatOpenAI

        console.print(f"[dim]Using Custom Endpoint: {settings.custom_model_name}[/dim]")
        return ChatOpenAI(
            base_url=settings.custom_api_base,
            api_key=settings.custom_api_key or "dummy",
            model=settings.custom_model_name,
            stream_usage=True,
        )
    if settings.has_openai:
        from langchain_openai import ChatOpenAI

        model_name = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
        console.print(f"[dim]Using OpenAI model: {model_name}[/dim]")
        return ChatOpenAI(
            model=model_name,
            stream_usage=True,
        )
    if settings.has_anthropic:
        from langchain_anthropic import ChatAnthropic

        model_name = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        console.print(f"[dim]Using Anthropic model: {model_name}[/dim]")
        return ChatAnthropic(
            model_name=model_name,
            # The attribute exists, but it has a Pydantic alias which
            # causes issues in IDEs/type checkers.
            max_tokens=20_000,  # type: ignore[arg-type]
            stream_usage=True,
        )
    if settings.has_google:
        from langchain_google_genai import ChatGoogleGenerativeAI

        model_name = os.environ.get("GOOGLE_MODEL", "gemini-2.5-pro")
        console.print(f"[dim]Using Google Gemini model: {model_name}[/dim]")
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            max_tokens=None,
        )
    console.print("[bold red]Error:[/bold red] No API key configured.")
    console.print("\nPlease set one of the following environment variables:")
    console.print("  - OPENAI_API_KEY     (for OpenAI models like gpt-5-mini)")
    console.print("  - ANTHROPIC_API_KEY  (for Claude models)")
    console.print("  - GOOGLE_API_KEY     (for Google Gemini models)")
    console.print("\nExample:")
    console.print("  export OPENAI_API_KEY=your_api_key_here")
    console.print("\nOr add it to your .env file.")
    sys.exit(1)
