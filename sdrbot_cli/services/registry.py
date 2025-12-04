"""Service registry and configuration management.

This module handles:
- Loading and saving service configuration from .sdrbot/services.json
- Tracking which services are enabled
- Tracking sync state for syncable services
- Providing service-level settings storage
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sdrbot_cli.services import SYNCABLE_SERVICES


class ServiceState:
    """State for a single service."""

    def __init__(
        self,
        enabled: bool = False,
        synced_at: str | None = None,
        schema_hash: str | None = None,
        objects: list[str] | None = None,
        settings: dict[str, Any] | None = None,
    ):
        self.enabled = enabled
        self.synced_at = synced_at
        self.schema_hash = schema_hash
        self.objects = objects or []
        self.settings = settings or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data: dict[str, Any] = {"enabled": self.enabled}
        if self.synced_at:
            data["synced_at"] = self.synced_at
        if self.schema_hash:
            data["schema_hash"] = self.schema_hash
        if self.objects:
            data["objects"] = self.objects
        if self.settings:
            data["settings"] = self.settings
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceState:
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            synced_at=data.get("synced_at"),
            schema_hash=data.get("schema_hash"),
            objects=data.get("objects", []),
            settings=data.get("settings", {}),
        )


@dataclass
class ServiceConfig:
    """Configuration for all services.

    This is the main configuration object that tracks:
    - Which services are enabled
    - Sync state for syncable services
    - Service-specific settings
    """

    version: int = 1
    services: dict[str, ServiceState] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: Path) -> ServiceConfig:
        """Load config from .sdrbot/services.json.

        Args:
            config_path: Path to the services.json file.

        Returns:
            ServiceConfig instance (empty if file doesn't exist).
        """
        if not config_path.exists():
            return cls()

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            services = {}
            for name, state_data in data.get("services", {}).items():
                services[name] = ServiceState.from_dict(state_data)

            return cls(
                version=data.get("version", 1),
                services=services,
            )
        except (json.JSONDecodeError, OSError):
            # Return empty config if file is corrupted
            return cls()

    def save(self, config_path: Path) -> None:
        """Save config to .sdrbot/services.json.

        Args:
            config_path: Path to the services.json file.
        """
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self.version,
            "services": {name: state.to_dict() for name, state in self.services.items()},
        }

        config_path.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get_state(self, service_name: str) -> ServiceState:
        """Get state for a service, creating default if not exists.

        Args:
            service_name: Name of the service.

        Returns:
            ServiceState for the service.
        """
        if service_name not in self.services:
            self.services[service_name] = ServiceState()
        return self.services[service_name]

    def is_enabled(self, service_name: str) -> bool:
        """Check if a service is enabled.

        Args:
            service_name: Name of the service.

        Returns:
            True if the service is enabled.
        """
        return self.services.get(service_name, ServiceState()).enabled

    def needs_sync(self, service_name: str) -> bool:
        """Check if a service needs initial sync.

        A service needs sync if:
        - It's a syncable service (has user-specific schema)
        - It's enabled
        - It has never been synced (synced_at is None)

        Args:
            service_name: Name of the service.

        Returns:
            True if the service needs to be synced.
        """
        if service_name not in SYNCABLE_SERVICES:
            return False

        state = self.services.get(service_name, ServiceState())
        return state.enabled and state.synced_at is None

    def is_synced(self, service_name: str) -> bool:
        """Check if a syncable service has been synced.

        Args:
            service_name: Name of the service.

        Returns:
            True if the service has been synced (has synced_at timestamp).
        """
        state = self.services.get(service_name, ServiceState())
        return state.synced_at is not None

    def enable(self, service_name: str) -> None:
        """Enable a service.

        Args:
            service_name: Name of the service to enable.
        """
        state = self.get_state(service_name)
        state.enabled = True

    def disable(self, service_name: str) -> None:
        """Disable a service.

        Args:
            service_name: Name of the service to disable.
        """
        if service_name in self.services:
            self.services[service_name].enabled = False

    def mark_synced(
        self,
        service_name: str,
        schema_hash: str,
        objects: list[str],
    ) -> None:
        """Mark a service as synced.

        Args:
            service_name: Name of the service.
            schema_hash: Hash of the schema at sync time.
            objects: List of objects that were synced.
        """
        state = self.get_state(service_name)
        state.synced_at = datetime.now(UTC).isoformat()
        state.schema_hash = schema_hash
        state.objects = objects

    def get_setting(
        self,
        service_name: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """Get a service-specific setting.

        Args:
            service_name: Name of the service.
            key: Setting key.
            default: Default value if not set.

        Returns:
            Setting value or default.
        """
        state = self.services.get(service_name, ServiceState())
        return state.settings.get(key, default)

    def set_setting(
        self,
        service_name: str,
        key: str,
        value: Any,
    ) -> None:
        """Set a service-specific setting.

        Args:
            service_name: Name of the service.
            key: Setting key.
            value: Setting value.
        """
        state = self.get_state(service_name)
        state.settings[key] = value


# Default config path relative to current working directory
_CONFIG_DIR = ".sdrbot"
_CONFIG_FILE = "services.json"

# Cached config instance
_cached_config: ServiceConfig | None = None
_cached_config_path: Path | None = None


def get_config_path() -> Path:
    """Get path to services.json in current project.

    Returns:
        Path to .sdrbot/services.json
    """
    return Path.cwd() / _CONFIG_DIR / _CONFIG_FILE


def load_config(force_reload: bool = False) -> ServiceConfig:
    """Load the service configuration.

    Uses a simple cache to avoid re-reading the file on every call.

    Args:
        force_reload: Force reload from disk even if cached.

    Returns:
        ServiceConfig instance.
    """
    global _cached_config, _cached_config_path

    config_path = get_config_path()

    # Return cached if path matches and not forcing reload
    if not force_reload and _cached_config is not None and _cached_config_path == config_path:
        return _cached_config

    _cached_config = ServiceConfig.load(config_path)
    _cached_config_path = config_path
    return _cached_config


def save_config(config: ServiceConfig) -> None:
    """Save the service configuration.

    Also updates the cache.

    Args:
        config: ServiceConfig to save.
    """
    global _cached_config, _cached_config_path

    config_path = get_config_path()
    config.save(config_path)

    _cached_config = config
    _cached_config_path = config_path


def clear_config_cache() -> None:
    """Clear the configuration cache.

    Useful for testing or when you know the file has changed externally.
    """
    global _cached_config, _cached_config_path
    _cached_config = None
    _cached_config_path = None


def compute_schema_hash(schema: dict[str, Any]) -> str:
    """Compute a hash of a schema for change detection.

    Args:
        schema: Schema dictionary to hash.

    Returns:
        16-character hex hash string.
    """
    schema_str = json.dumps(schema, sort_keys=True)
    return hashlib.sha256(schema_str.encode()).hexdigest()[:16]
