"""Tests for config persistence functions."""

import json
from unittest.mock import patch

import pytest

from sdrbot_cli.config import (
    load_model_config,
    load_provider_config,
    save_model_config,
)


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory and patch get_config_dir."""
    config_dir = tmp_path / ".sdrbot"
    config_dir.mkdir()

    with patch("sdrbot_cli.config.get_config_dir", return_value=config_dir):
        yield config_dir


class TestSaveModelConfig:
    """Tests for save_model_config function."""

    def test_save_basic_provider(self, temp_config_dir):
        """Test saving a basic provider config."""
        save_model_config("openai", "gpt-4")

        config_file = temp_config_dir / "model.json"
        assert config_file.exists()

        data = json.loads(config_file.read_text())
        assert data["active_provider"] == "openai"
        assert data["providers"]["openai"]["model_name"] == "gpt-4"

    def test_save_with_api_base(self, temp_config_dir):
        """Test saving a provider with custom api_base."""
        save_model_config("ollama", "llama2", api_base="http://localhost:11434/v1")

        data = json.loads((temp_config_dir / "model.json").read_text())
        assert data["providers"]["ollama"]["api_base"] == "http://localhost:11434/v1"

    def test_save_azure_config(self, temp_config_dir):
        """Test saving Azure-specific configuration."""
        save_model_config(
            "azure",
            "gpt-4",
            azure_endpoint="https://myresource.openai.azure.com",
            azure_deployment="my-deployment",
            azure_api_version="2024-02-01",
        )

        data = json.loads((temp_config_dir / "model.json").read_text())
        azure_config = data["providers"]["azure"]
        assert azure_config["model_name"] == "gpt-4"
        assert azure_config["azure_endpoint"] == "https://myresource.openai.azure.com"
        assert azure_config["azure_deployment"] == "my-deployment"
        assert azure_config["azure_api_version"] == "2024-02-01"

    def test_save_preserves_other_providers(self, temp_config_dir):
        """Test that saving a new provider preserves existing configs."""
        # Save first provider
        save_model_config("openai", "gpt-4")
        # Save second provider
        save_model_config("anthropic", "claude-3-opus")

        data = json.loads((temp_config_dir / "model.json").read_text())
        # Active should be the last saved
        assert data["active_provider"] == "anthropic"
        # But openai should still be preserved
        assert "openai" in data["providers"]
        assert data["providers"]["openai"]["model_name"] == "gpt-4"
        assert data["providers"]["anthropic"]["model_name"] == "claude-3-opus"

    def test_save_overwrites_same_provider(self, temp_config_dir):
        """Test that saving the same provider updates its config."""
        save_model_config("openai", "gpt-3.5")
        save_model_config("openai", "gpt-4")

        data = json.loads((temp_config_dir / "model.json").read_text())
        assert data["providers"]["openai"]["model_name"] == "gpt-4"


class TestLoadModelConfig:
    """Tests for load_model_config function."""

    def test_load_nonexistent_returns_none(self, temp_config_dir):
        """Test loading when no config file exists."""
        result = load_model_config()
        assert result is None

    def test_load_empty_active_provider_returns_none(self, temp_config_dir):
        """Test loading when active_provider is None."""
        config_file = temp_config_dir / "model.json"
        config_file.write_text(json.dumps({"active_provider": None, "providers": {}}))

        result = load_model_config()
        assert result is None

    def test_load_missing_provider_config_returns_none(self, temp_config_dir):
        """Test loading when provider config doesn't exist."""
        config_file = temp_config_dir / "model.json"
        config_file.write_text(json.dumps({"active_provider": "openai", "providers": {}}))

        result = load_model_config()
        assert result is None

    def test_load_valid_config(self, temp_config_dir):
        """Test loading a valid configuration."""
        save_model_config("openai", "gpt-4")

        result = load_model_config()
        assert result is not None
        assert result["provider"] == "openai"
        assert result["model_name"] == "gpt-4"

    def test_load_azure_config(self, temp_config_dir):
        """Test loading Azure configuration with all fields."""
        save_model_config(
            "azure",
            "gpt-4",
            azure_endpoint="https://test.openai.azure.com",
            azure_deployment="deploy-1",
            azure_api_version="2024-02-01",
        )

        result = load_model_config()
        assert result["provider"] == "azure"
        assert result["azure_endpoint"] == "https://test.openai.azure.com"
        assert result["azure_deployment"] == "deploy-1"
        assert result["azure_api_version"] == "2024-02-01"

    def test_load_invalid_json_returns_none(self, temp_config_dir):
        """Test loading when config file has invalid JSON."""
        config_file = temp_config_dir / "model.json"
        config_file.write_text("not valid json {")

        result = load_model_config()
        assert result is None


class TestLoadProviderConfig:
    """Tests for load_provider_config function."""

    def test_load_nonexistent_provider(self, temp_config_dir):
        """Test loading config for a provider that doesn't exist."""
        result = load_provider_config("openai")
        assert result == {}

    def test_load_existing_provider(self, temp_config_dir):
        """Test loading config for a saved provider."""
        save_model_config("openai", "gpt-4")

        result = load_provider_config("openai")
        assert result["model_name"] == "gpt-4"

    def test_load_inactive_provider(self, temp_config_dir):
        """Test loading config for a provider that's not active."""
        save_model_config("openai", "gpt-4")
        save_model_config("anthropic", "claude-3")  # This becomes active

        # OpenAI is no longer active but config should still be retrievable
        result = load_provider_config("openai")
        assert result["model_name"] == "gpt-4"

    def test_load_provider_with_api_base(self, temp_config_dir):
        """Test loading provider config includes api_base."""
        save_model_config("custom", "llama2", api_base="http://localhost:8000/v1")

        result = load_provider_config("custom")
        assert result["model_name"] == "llama2"
        assert result["api_base"] == "http://localhost:8000/v1"
