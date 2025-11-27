"""Configuration, constants, and model creation for the CLI."""

import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, Optional

import dotenv
from langchain_core.language_models import BaseChatModel
from rich.console import Console

# Load .env ONLY from current working directory to avoid accidental parent config inheritance
dotenv.load_dotenv(Path.cwd() / ".env")

# Color scheme
COLORS = {
    "primary": "#10b981",
    "dim": "#6b7280",
    "user": "#ffffff",
    "agent": "#10b981",
    "thinking": "#34d399",
    "tool": "#fbbf24",
}

# ASCII art banner
DEEP_AGENTS_ASCII = """
 ███████╗██████╗ ██████╗ ██████╗  ██████╗ ████████╗
 ██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝
 ███████╗██║  ██║██████╔╝██████╔╝██║   ██║   ██║   
 ╚════██║██║  ██║██╔══██╗██╔══██╗██║   ██║   ██║   
 ███████║██████╔╝██║  ██║██████╔╝╚██████╔╝   ██║   
 ╚══════╝╚═════╝ ╚═╝  ╚═╝╚═════╝  ╚═════╝    ╚═╝   
                                                   
             [ REVOPS INTELLIGENCE ]
"""

# Interactive commands
COMMANDS = {
    "clear": "Clear screen and reset conversation",
    "help": "Show help information",
    "tokens": "Show token usage for current session",
    "quit": "Exit the CLI",
    "exit": "Exit the CLI",
    "setup": "Re-run full setup wizard",
    "models": "Manage LLM providers and models (list, switch, update)",
    "services": "Manage external services (enable, disable, update, sync, status)",
}


# Maximum argument length for display
MAX_ARG_LENGTH = 150

# Agent configuration
config = {"recursion_limit": 1000}

# Rich console instance
console = Console(highlight=False)


class ModelConfig(TypedDict):
    """Structure for the active model configuration file."""
    provider: str
    model_name: str
    api_base: Optional[str]


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    config_dir = Path.cwd() / ".sdrbot"
    config_dir.mkdir(exist_ok=True)
    return config_dir


def load_model_config() -> Optional[ModelConfig]:
    """Load the active model configuration from .sdrbot/model.json."""
    config_file = get_config_dir() / "model.json"
    if not config_file.exists():
        return None
    try:
        return json.loads(config_file.read_text())
    except Exception:
        return None


def save_model_config(provider: str, model_name: str, api_base: Optional[str] = None) -> None:
    """Save the active model configuration."""
    config: ModelConfig = {
        "provider": provider,
        "model_name": model_name,
        "api_base": api_base
    }
    config_file = get_config_dir() / "model.json"
    config_file.write_text(json.dumps(config, indent=2))


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


def _find_project_agent_md(project_root: Path) -> list[Path]:
    """Find project-specific agent.md file(s).

    Checks two locations and returns ALL that exist:
    1. project_root/.deepagents/agent.md
    2. project_root/agent.md

    Both files will be loaded and combined if both exist.

    Args:
        project_root: Path to the project root directory.

    Returns:
        List of paths to project agent.md files (may contain 0, 1, or 2 paths).
    """
    paths = []

    # Check .deepagents/agent.md (preferred)
    deepagents_md = project_root / ".deepagents" / "agent.md"
    if deepagents_md.exists():
        paths.append(deepagents_md)

    # Check root agent.md (fallback, but also include if both exist)
    root_md = project_root / "agent.md"
    if root_md.exists():
        paths.append(root_md)

    return paths


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

    # Attio Config
    attio_api_key: str | None

    # Lusha Config
    lusha_api_key: str | None

    # Hunter Config
    hunter_api_key: str | None

    # Custom Model Config
    custom_api_base: str | None
    custom_api_key: str | None
    custom_model_name: str | None

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
        
        sf_client_id = os.environ.get("SF_CLIENT_ID")
        sf_client_secret = os.environ.get("SF_CLIENT_SECRET")
        
        hubspot_client_id = os.environ.get("HUBSPOT_CLIENT_ID")
        hubspot_client_secret = os.environ.get("HUBSPOT_CLIENT_SECRET")
        hubspot_access_token = os.environ.get("HUBSPOT_ACCESS_TOKEN")

        attio_api_key = os.environ.get("ATTIO_API_KEY")
        lusha_api_key = os.environ.get("LUSHA_API_KEY")
        hunter_api_key = os.environ.get("HUNTER_API_KEY")

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
            attio_api_key=attio_api_key,
            lusha_api_key=lusha_api_key,
            hunter_api_key=hunter_api_key,
            custom_api_base=custom_base,
            custom_api_key=custom_key,
            custom_model_name=custom_model,
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
        self.attio_api_key = new_settings.attio_api_key
        self.lusha_api_key = new_settings.lusha_api_key
        self.hunter_api_key = new_settings.hunter_api_key
        self.custom_api_base = new_settings.custom_api_base
        self.custom_api_key = new_settings.custom_api_key
        self.custom_model_name = new_settings.custom_model_name
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
    def has_attio(self) -> bool:
        """Check if Attio API key is configured."""
        return self.attio_api_key is not None

    @property
    def has_lusha(self) -> bool:
        """Check if Lusha API key is configured."""
        return self.lusha_api_key is not None

    @property
    def has_hunter(self) -> bool:
        """Check if Hunter API key is configured."""
        return self.hunter_api_key is not None

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
            "lusha": self.has_lusha,
            "hunter": self.has_hunter,
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

    def get_agent_md_path(self, agent_name: str) -> Path:
        """Get the path to an agent's markdown file.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ./agents/{agent_name}.md
        """
        if not self._is_valid_agent_name(agent_name):
            msg = (
                f"Invalid agent name: {agent_name!r}. "
                "Agent names can only contain letters, numbers, hyphens, underscores, and spaces."
            )
            raise ValueError(msg)
        return self.agents_dir / f"{agent_name}.md"

    def get_agent_dir(self, agent_name: str) -> Path:
        """Get the data directory for an agent (for memory, tokens, etc.).

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ./.sdrbot/{agent_name}/
        """
        if not self._is_valid_agent_name(agent_name):
            msg = (
                f"Invalid agent name: {agent_name!r}. "
                "Agent names can only contain letters, numbers, hyphens, underscores, and spaces."
            )
            raise ValueError(msg)
        return Path.cwd() / ".sdrbot" / agent_name

    def ensure_agent_dir(self, agent_name: str) -> Path:
        """Ensure agent data directory exists.

        Args:
            agent_name: Name of the agent

        Returns:
            Path to ./.sdrbot/{agent_name}/
        """
        agent_dir = self.get_agent_dir(agent_name)
        agent_dir.mkdir(parents=True, exist_ok=True)
        return agent_dir

    def ensure_agent_md(self, agent_name: str, default_content: str) -> Path:
        """Ensure agent markdown file exists, creating with default content if needed.

        Creates ./agents/ directory and {agent_name}.md if they don't exist.

        Args:
            agent_name: Name of the agent
            default_content: Content to write if file doesn't exist

        Returns:
            Path to ./agents/{agent_name}.md
        """
        agent_md = self.get_agent_md_path(agent_name)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        if not agent_md.exists():
            agent_md.write_text(default_content)
        return agent_md

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


# Global settings instance (initialized once)
settings = Settings.from_environment()


class SessionState:
    """Holds mutable session state (auto-approve mode, agent, etc)."""

    def __init__(self, auto_approve: bool = False, no_splash: bool = False) -> None:
        self.auto_approve = auto_approve
        self.no_splash = no_splash
        self.exit_hint_until: float | None = None
        self.exit_hint_handle = None
        self.thread_id = str(uuid.uuid4())
        # Agent and backend can be swapped at runtime for hot-reloading
        self.agent = None
        self.backend = None
        # Reload callback - set by main.py to allow commands to trigger agent reload
        self._reload_callback = None

    def toggle_auto_approve(self) -> bool:
        """Toggle auto-approve and return new state."""
        self.auto_approve = not self.auto_approve
        return self.auto_approve

    def set_reload_callback(self, callback) -> None:
        """Set the callback function for reloading the agent."""
        self._reload_callback = callback

    def reload_agent(self) -> bool:
        """Reload the agent with updated tools/config.

        Returns:
            True if reload succeeded, False if no callback set.
        """
        if self._reload_callback:
            self._reload_callback()
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
        
        if provider == "custom":
            from langchain_openai import ChatOpenAI
            console.print(f"[dim]Using Custom Endpoint: {model_name}[/dim]")
            return ChatOpenAI(
                base_url=model_config.get("api_base"),
                api_key=settings.custom_api_key or "dummy",
                model=model_name,
            )
            
        if provider == "openai":
            if not settings.has_openai:
                console.print("[bold red]Error:[/bold red] OpenAI selected but OPENAI_API_KEY missing in .env")
                sys.exit(1)
            from langchain_openai import ChatOpenAI
            console.print(f"[dim]Using OpenAI model: {model_name}[/dim]")
            return ChatOpenAI(model=model_name)

        if provider == "anthropic":
            if not settings.has_anthropic:
                console.print("[bold red]Error:[/bold red] Anthropic selected but ANTHROPIC_API_KEY missing in .env")
                sys.exit(1)
            from langchain_anthropic import ChatAnthropic
            console.print(f"[dim]Using Anthropic model: {model_name}[/dim]")
            return ChatAnthropic(
                model_name=model_name,
                max_tokens=20_000,  # type: ignore[arg-type]
            )

        if provider == "google":
            if not settings.has_google:
                console.print("[bold red]Error:[/bold red] Google selected but GOOGLE_API_KEY missing in .env")
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
        )
    if settings.has_openai:
        from langchain_openai import ChatOpenAI

        model_name = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
        console.print(f"[dim]Using OpenAI model: {model_name}[/dim]")
        return ChatOpenAI(
            model=model_name,
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
