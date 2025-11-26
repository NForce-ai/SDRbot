"""Tests for service tool loading (services/__init__.py)."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.tools import BaseTool

from sdrbot_cli.services import SERVICES, SYNCABLE_SERVICES, get_enabled_tools
from sdrbot_cli.services.registry import ServiceConfig, clear_config_cache


class TestServiceConstants:
    """Test service constants."""

    def test_services_list(self):
        """SERVICES should contain expected services."""
        assert "hubspot" in SERVICES
        assert "salesforce" in SERVICES
        assert "attio" in SERVICES
        assert "lusha" in SERVICES
        assert "hunter" in SERVICES

    def test_syncable_services(self):
        """SYNCABLE_SERVICES should be subset of SERVICES."""
        for service in SYNCABLE_SERVICES:
            assert service in SERVICES

        # These should be syncable (have user-specific schemas)
        assert "hubspot" in SYNCABLE_SERVICES
        assert "salesforce" in SYNCABLE_SERVICES
        assert "attio" in SYNCABLE_SERVICES

        # These should NOT be syncable (static APIs)
        assert "hunter" not in SYNCABLE_SERVICES
        assert "lusha" not in SYNCABLE_SERVICES


class TestGetEnabledTools:
    """Tests for get_enabled_tools function."""

    def test_returns_base_tools(self):
        """All returned tools should be BaseTool instances."""
        tools = get_enabled_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_names(self):
        """All tools should have names."""
        tools = get_enabled_tools()

        for tool in tools:
            assert tool.name, f"Tool has no name: {tool}"
            assert len(tool.name) > 0

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        tools = get_enabled_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_no_duplicate_tool_names(self):
        """Tool names should be unique."""
        tools = get_enabled_tools()
        names = [t.name for t in tools]

        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_only_enabled_services_loaded(self):
        """Only tools from enabled services should be loaded."""
        from sdrbot_cli.services.registry import load_config

        config = load_config()
        tools = get_enabled_tools()
        tool_names = [t.name for t in tools]

        # Check each service
        for service in SERVICES:
            prefix = f"{service}_"
            has_tools = any(name.startswith(prefix) for name in tool_names)

            if config.is_enabled(service):
                # Enabled services should have tools (if they have any)
                pass  # Can't assert has_tools since some may have 0 tools
            else:
                # Disabled services should NOT have tools
                assert not has_tools, f"Disabled service {service} has tools loaded"

    def test_import_error_handled_gracefully(self):
        """Import errors should be handled without crashing."""
        # This tests that if a service module fails to import,
        # the function continues with other services

        with patch.dict("sys.modules", {"sdrbot_cli.services.fake_service": None}):
            # Should not raise even if a module import fails
            tools = get_enabled_tools()
            assert isinstance(tools, list)


class TestToolLoadingWithConfig:
    """Tests for tool loading with different configurations."""

    @pytest.fixture
    def temp_config(self):
        """Create a temporary config directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".sdrbot" / "services.json"

            # Patch get_config_path to use temp directory
            with patch(
                "sdrbot_cli.services.registry.get_config_path",
                return_value=config_path
            ):
                clear_config_cache()
                yield config_path

    def test_no_config_file(self, temp_config):
        """With no config file, no service-specific tools should load."""
        clear_config_cache()
        tools = get_enabled_tools()

        # Without config, no services are enabled
        # So only tools from services enabled by default (none) should load
        tool_names = [t.name for t in tools]

        # Services should not have tools loaded
        for service in ["hubspot", "salesforce", "attio", "lusha", "hunter"]:
            prefix = f"{service}_"
            service_tools = [n for n in tool_names if n.startswith(prefix)]
            assert len(service_tools) == 0, f"{service} tools loaded without config"

    def test_hunter_enabled(self, temp_config):
        """When Hunter is enabled, Hunter tools should load."""
        # Create config with Hunter enabled
        config = ServiceConfig()
        config.enable("hunter")
        config.save(temp_config)
        clear_config_cache()

        tools = get_enabled_tools()
        tool_names = [t.name for t in tools]

        hunter_tools = [n for n in tool_names if n.startswith("hunter_")]
        assert len(hunter_tools) == 3, f"Expected 3 Hunter tools, got {hunter_tools}"


class TestToolNaming:
    """Tests for tool naming conventions."""

    def test_tool_names_are_snake_case(self):
        """Tool names should be snake_case."""
        tools = get_enabled_tools()

        for tool in tools:
            # Should be lowercase with underscores
            assert tool.name.islower() or "_" in tool.name, (
                f"Tool name not snake_case: {tool.name}"
            )
            # Should not contain spaces or dashes
            assert " " not in tool.name, f"Tool name contains space: {tool.name}"
            assert "-" not in tool.name, f"Tool name contains dash: {tool.name}"

    def test_tool_names_have_service_prefix(self):
        """Tool names should start with service name."""
        tools = get_enabled_tools()

        valid_prefixes = [f"{s}_" for s in SERVICES]

        for tool in tools:
            has_valid_prefix = any(
                tool.name.startswith(prefix) for prefix in valid_prefixes
            )
            assert has_valid_prefix, (
                f"Tool {tool.name} doesn't have a valid service prefix"
            )
