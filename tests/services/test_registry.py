"""Tests for service registry and configuration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sdrbot_cli.services.registry import (
    ServiceConfig,
    ServiceState,
    compute_schema_hash,
    clear_config_cache,
)


class TestServiceState:
    """Tests for ServiceState class."""

    def test_default_state(self):
        """Default state should have enabled=False."""
        state = ServiceState()

        assert state.enabled is False
        assert state.synced_at is None
        assert state.schema_hash is None
        assert state.objects == []
        assert state.settings == {}

    def test_state_to_dict(self):
        """to_dict should serialize state correctly."""
        state = ServiceState(
            enabled=True,
            synced_at="2024-01-01T00:00:00Z",
            schema_hash="abc123",
            objects=["contacts", "deals"],
            settings={"key": "value"}
        )

        data = state.to_dict()

        assert data["enabled"] is True
        assert data["synced_at"] == "2024-01-01T00:00:00Z"
        assert data["schema_hash"] == "abc123"
        assert data["objects"] == ["contacts", "deals"]
        assert data["settings"] == {"key": "value"}

    def test_state_to_dict_minimal(self):
        """to_dict should omit None/empty values."""
        state = ServiceState(enabled=True)

        data = state.to_dict()

        assert data == {"enabled": True}
        assert "synced_at" not in data
        assert "schema_hash" not in data

    def test_state_from_dict(self):
        """from_dict should deserialize state correctly."""
        data = {
            "enabled": True,
            "synced_at": "2024-01-01T00:00:00Z",
            "schema_hash": "abc123",
            "objects": ["contacts"],
        }

        state = ServiceState.from_dict(data)

        assert state.enabled is True
        assert state.synced_at == "2024-01-01T00:00:00Z"
        assert state.schema_hash == "abc123"
        assert state.objects == ["contacts"]

    def test_state_from_dict_defaults(self):
        """from_dict should use defaults for missing keys."""
        state = ServiceState.from_dict({})

        assert state.enabled is False
        assert state.synced_at is None


class TestServiceConfig:
    """Tests for ServiceConfig class."""

    def test_empty_config(self):
        """Empty config should have no services."""
        config = ServiceConfig()

        assert config.version == 1
        assert config.services == {}

    def test_is_enabled_default(self):
        """is_enabled should return False for unknown services."""
        config = ServiceConfig()

        assert config.is_enabled("hubspot") is False
        assert config.is_enabled("unknown") is False

    def test_enable_service(self):
        """enable should set enabled=True."""
        config = ServiceConfig()

        config.enable("hubspot")

        assert config.is_enabled("hubspot") is True

    def test_disable_service(self):
        """disable should set enabled=False."""
        config = ServiceConfig()
        config.enable("hubspot")

        config.disable("hubspot")

        assert config.is_enabled("hubspot") is False

    def test_disable_unknown_service(self):
        """disable should handle unknown services gracefully."""
        config = ServiceConfig()

        # Should not raise
        config.disable("unknown")

        assert config.is_enabled("unknown") is False

    def test_needs_sync_syncable_enabled(self):
        """needs_sync should return True for enabled syncable services."""
        config = ServiceConfig()
        config.enable("hubspot")

        assert config.needs_sync("hubspot") is True

    def test_needs_sync_already_synced(self):
        """needs_sync should return False if already synced."""
        config = ServiceConfig()
        config.enable("hubspot")
        config.mark_synced("hubspot", "hash123", ["contacts"])

        assert config.needs_sync("hubspot") is False

    def test_needs_sync_non_syncable(self):
        """needs_sync should return False for non-syncable services."""
        config = ServiceConfig()
        config.enable("hunter")

        assert config.needs_sync("hunter") is False

    def test_is_synced(self):
        """is_synced should check synced_at presence."""
        config = ServiceConfig()
        config.enable("hubspot")

        assert config.is_synced("hubspot") is False

        config.mark_synced("hubspot", "hash123", ["contacts"])

        assert config.is_synced("hubspot") is True

    def test_mark_synced(self):
        """mark_synced should set sync metadata."""
        config = ServiceConfig()
        config.enable("hubspot")

        config.mark_synced("hubspot", "hash123", ["contacts", "deals"])

        state = config.get_state("hubspot")
        assert state.synced_at is not None
        assert state.schema_hash == "hash123"
        assert state.objects == ["contacts", "deals"]

    def test_settings(self):
        """get_setting and set_setting should work."""
        config = ServiceConfig()

        config.set_setting("hubspot", "custom_field", "value123")

        assert config.get_setting("hubspot", "custom_field") == "value123"
        assert config.get_setting("hubspot", "unknown", "default") == "default"


class TestServiceConfigPersistence:
    """Tests for loading/saving ServiceConfig."""

    def test_save_and_load(self):
        """Config should round-trip through save/load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".sdrbot" / "services.json"

            # Create and save config
            config = ServiceConfig()
            config.enable("hubspot")
            config.mark_synced("hubspot", "hash123", ["contacts"])
            config.enable("hunter")
            config.save(config_path)

            # Load and verify
            loaded = ServiceConfig.load(config_path)

            assert loaded.is_enabled("hubspot") is True
            assert loaded.is_enabled("hunter") is True
            assert loaded.is_synced("hubspot") is True
            assert loaded.get_state("hubspot").schema_hash == "hash123"

    def test_load_missing_file(self):
        """Loading missing file should return empty config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent" / "services.json"

            config = ServiceConfig.load(config_path)

            assert config.services == {}

    def test_load_corrupted_file(self):
        """Loading corrupted file should return empty config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "services.json"
            config_path.write_text("not valid json {{{")

            config = ServiceConfig.load(config_path)

            assert config.services == {}

    def test_save_creates_directory(self):
        """save should create parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nested" / "dir" / "services.json"

            config = ServiceConfig()
            config.enable("hubspot")
            config.save(config_path)

            assert config_path.exists()


class TestComputeSchemaHash:
    """Tests for schema hashing."""

    def test_deterministic(self):
        """Same schema should produce same hash."""
        schema = {"contacts": {"name": "string"}, "deals": {"amount": "number"}}

        hash1 = compute_schema_hash(schema)
        hash2 = compute_schema_hash(schema)

        assert hash1 == hash2

    def test_order_independent(self):
        """Hash should be independent of key order."""
        schema1 = {"a": 1, "b": 2}
        schema2 = {"b": 2, "a": 1}

        assert compute_schema_hash(schema1) == compute_schema_hash(schema2)

    def test_different_schemas_different_hash(self):
        """Different schemas should produce different hashes."""
        schema1 = {"contacts": {"name": "string"}}
        schema2 = {"contacts": {"email": "string"}}

        assert compute_schema_hash(schema1) != compute_schema_hash(schema2)

    def test_hash_length(self):
        """Hash should be 16 characters."""
        schema = {"test": "data"}

        hash_value = compute_schema_hash(schema)

        assert len(hash_value) == 16


class TestConfigCache:
    """Tests for configuration caching."""

    def test_clear_cache(self):
        """clear_config_cache should reset cached values."""
        # This mainly tests that clear_config_cache doesn't crash
        clear_config_cache()

        # After clearing, load_config should read from disk
        from sdrbot_cli.services.registry import load_config

        # Should not raise
        config = load_config(force_reload=True)
        assert config is not None
