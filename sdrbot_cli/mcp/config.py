"""MCP server configuration management."""

import json
import os
from pathlib import Path
from typing import Any

from sdrbot_cli.config import get_config_dir


def get_mcp_config_path() -> Path:
    """Get the path to the MCP configuration file."""
    return get_config_dir() / "mcp_servers.json"


def load_mcp_config() -> dict[str, Any]:
    """
    Load MCP server configuration from file.

    Returns:
        Configuration dict with structure:
        {
            "version": 1,
            "servers": {
                "server_name": {
                    "enabled": bool,
                    "transport": "stdio" | "http" | "sse",
                    "command": str,  # for stdio
                    "args": list[str],  # for stdio
                    "env": dict[str, str],  # for stdio
                    "url": str,  # for http/sse
                    "auth": {  # for http/sse
                        "type": "none" | "bearer" | "apikey" | "custom",
                        "token": str,  # for bearer (supports ${VAR} syntax)
                        "api_key": str,  # for apikey (supports ${VAR} syntax)
                        "headers": dict[str, str],  # for custom
                    },
                    "tool_count": int,  # cached after connection
                }
            }
        }
    """
    config_path = get_mcp_config_path()

    if not config_path.exists():
        return {"version": 1, "servers": {}}

    try:
        with open(config_path) as f:
            config = json.load(f)
            # Ensure structure
            if "servers" not in config:
                config["servers"] = {}
            return config
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "servers": {}}


def save_mcp_config(config: dict[str, Any]) -> None:
    """Save MCP server configuration to file."""
    config_path = get_mcp_config_path()

    # Ensure config directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def add_mcp_server(
    name: str,
    transport: str,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    url: str | None = None,
    auth: dict[str, Any] | None = None,
    enabled: bool = True,
) -> None:
    """
    Add or update an MCP server configuration.

    Args:
        name: Unique server name
        transport: "stdio", "http", or "sse"
        command: Command to run (for stdio)
        args: Command arguments (for stdio)
        env: Environment variables (for stdio)
        url: Server URL (for http/sse)
        auth: Authentication config (for http/sse)
        enabled: Whether server is enabled
    """
    config = load_mcp_config()

    server_config: dict[str, Any] = {
        "enabled": enabled,
        "transport": transport,
    }

    if transport == "stdio":
        server_config["command"] = command
        server_config["args"] = args or []
        server_config["env"] = env or {}
    elif transport in ("http", "sse"):
        server_config["url"] = url
        if auth:
            server_config["auth"] = auth

    config["servers"][name] = server_config
    save_mcp_config(config)


def remove_mcp_server(name: str) -> bool:
    """
    Remove an MCP server configuration.

    Returns:
        True if server was removed, False if not found
    """
    config = load_mcp_config()

    if name in config["servers"]:
        del config["servers"][name]
        save_mcp_config(config)
        return True

    return False


def enable_mcp_server(name: str) -> bool:
    """Enable an MCP server."""
    config = load_mcp_config()

    if name in config["servers"]:
        config["servers"][name]["enabled"] = True
        save_mcp_config(config)
        return True

    return False


def disable_mcp_server(name: str) -> bool:
    """Disable an MCP server."""
    config = load_mcp_config()

    if name in config["servers"]:
        config["servers"][name]["enabled"] = False
        save_mcp_config(config)
        return True

    return False


def update_server_tool_count(name: str, tool_count: int) -> None:
    """Update the cached tool count for a server."""
    config = load_mcp_config()

    if name in config["servers"]:
        config["servers"][name]["tool_count"] = tool_count
        save_mcp_config(config)


def resolve_env_var(value: str) -> str:
    """
    Resolve a single environment variable reference.

    Supports ${VAR_NAME} syntax to reference environment variables.
    """
    if value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        return os.environ.get(var_name, "")
    return value


def resolve_env_vars(env: dict[str, str]) -> dict[str, str]:
    """
    Resolve environment variable references in env dict.

    Supports ${VAR_NAME} syntax to reference environment variables.
    """
    return {key: resolve_env_var(value) for key, value in env.items()}


def build_auth_headers(auth: dict[str, Any] | None) -> dict[str, str]:
    """
    Build HTTP headers from auth configuration.

    Args:
        auth: Auth config dict with "type" and type-specific fields

    Returns:
        Dict of headers to pass to the MCP client
    """
    if not auth:
        return {}

    auth_type = auth.get("type", "none")

    if auth_type == "bearer":
        token = auth.get("token", "")
        resolved_token = resolve_env_var(token)
        if resolved_token:
            return {"Authorization": f"Bearer {resolved_token}"}

    elif auth_type == "apikey":
        api_key = auth.get("api_key", "")
        resolved_key = resolve_env_var(api_key)
        if resolved_key:
            return {"X-API-Key": resolved_key}

    elif auth_type == "custom":
        custom_headers = auth.get("headers", {})
        return resolve_env_vars(custom_headers)

    return {}
