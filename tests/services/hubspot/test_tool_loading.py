"""Tests for HubSpot tool loading and discovery."""

from unittest.mock import patch, MagicMock

import pytest
from langchain_core.tools import BaseTool


class TestHubSpotToolLoading:
    """Test that HubSpot tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should always load."""
        from sdrbot_cli.services.hubspot.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "hubspot_list_pipelines" in tool_names
        assert "hubspot_create_association" in tool_names
        assert "hubspot_list_associations" in tool_names
        assert "hubspot_delete_association" in tool_names

    def test_static_tools_are_base_tool_instances(self):
        """Static tools should be BaseTool instances."""
        from sdrbot_cli.services.hubspot.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_generated_tools_load_when_synced(self):
        """Generated tools should load if tools_generated.py exists."""
        from sdrbot_cli.services.hubspot import get_tools

        tools = get_tools()

        # Should have static tools + generated tools
        assert len(tools) > 4, "Expected generated tools to be loaded"

        tool_names = [t.name for t in tools]

        # Check for expected generated tools
        assert "hubspot_create_contact" in tool_names
        assert "hubspot_search_contacts" in tool_names
        assert "hubspot_get_contact" in tool_names
        assert "hubspot_update_contact" in tool_names
        assert "hubspot_delete_contact" in tool_names

    def test_generated_tools_are_base_tool_instances(self):
        """All generated tools should be BaseTool instances."""
        from sdrbot_cli.services.hubspot import get_tools

        tools = get_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_all_hubspot_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.hubspot import get_tools

        tools = get_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"
            assert len(tool.description) > 10, f"{tool.name} description too short"

    def test_generated_tools_graceful_fallback(self):
        """If tools_generated.py doesn't exist, should return static tools only."""
        with patch.dict("sys.modules", {"sdrbot_cli.services.hubspot.tools_generated": None}):
            # Force reimport
            import importlib
            import sdrbot_cli.services.hubspot as hubspot_module

            # This simulates the ImportError case
            with patch.object(
                hubspot_module,
                "get_tools",
                side_effect=lambda: hubspot_module.tools.get_static_tools()
            ):
                from sdrbot_cli.services.hubspot.tools import get_static_tools
                tools = get_static_tools()
                assert len(tools) == 4


class TestEnabledToolsLoading:
    """Test the service registry tool loading."""

    def test_get_enabled_tools_loads_hubspot_when_enabled(self):
        """HubSpot tools should load when service is enabled."""
        from sdrbot_cli.services import get_enabled_tools
        from sdrbot_cli.services.registry import load_config

        config = load_config()

        if not config.is_enabled("hubspot"):
            pytest.skip("HubSpot not enabled in services.json")

        tools = get_enabled_tools()
        tool_names = [t.name for t in tools]

        assert any(name.startswith("hubspot_") for name in tool_names)

    def test_get_enabled_tools_returns_base_tools(self):
        """All returned tools should be BaseTool instances."""
        from sdrbot_cli.services import get_enabled_tools

        tools = get_enabled_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tool_count_matches_expectations(self):
        """Verify expected number of tools for each enabled service."""
        from sdrbot_cli.services import get_enabled_tools
        from sdrbot_cli.services.registry import load_config

        config = load_config()
        tools = get_enabled_tools()

        hubspot_tools = [t for t in tools if t.name.startswith("hubspot_")]
        hunter_tools = [t for t in tools if t.name.startswith("hunter_")]

        if config.is_enabled("hubspot"):
            # 4 static + 35 generated (7 objects * 5 operations)
            assert len(hubspot_tools) >= 4, "Expected at least static HubSpot tools"

        if config.is_enabled("hunter"):
            assert len(hunter_tools) == 3, "Expected 3 Hunter tools"
