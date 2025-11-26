"""Tests for Lusha tools."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestLushaToolLoading:
    """Test that Lusha tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.lusha.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "lusha_enrich_person" in tool_names
        assert "lusha_enrich_company" in tool_names
        assert "lusha_prospect" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.lusha.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.lusha.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"


class TestLushaToolsUnit:
    """Unit tests for Lusha tools with mocked API."""

    @pytest.fixture
    def mock_lusha_client(self):
        """Create a mock Lusha client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_lusha_client(self, mock_lusha_client):
        """Patch Lusha client."""
        import sdrbot_cli.services.lusha.tools as tools_module

        original_client = tools_module._lusha_client
        tools_module._lusha_client = None

        with patch("sdrbot_cli.services.lusha.tools.LushaClient", return_value=mock_lusha_client):
            yield mock_lusha_client

        tools_module._lusha_client = original_client

    def test_enrich_person_success(self, patch_lusha_client):
        """enrich_person should return formatted results."""
        patch_lusha_client.request.return_value = {
            "data": {
                "fullName": "John Doe",
                "emailAddresses": [{"email": "john@example.com"}],
                "phoneNumbers": [{"internationalNumber": "+1234567890"}],
                "jobTitle": "CEO",
                "company": {"name": "Example Inc"}
            }
        }

        from sdrbot_cli.services.lusha.tools import lusha_enrich_person

        import sdrbot_cli.services.lusha.tools as tools_module
        tools_module._lusha_client = None

        result = lusha_enrich_person.invoke({
            "linkedin_url": "https://linkedin.com/in/johndoe"
        })

        assert "John Doe" in result
        assert "john@example.com" in result
        assert "+1234567890" in result
        assert "CEO" in result

    def test_enrich_person_requires_input(self, patch_lusha_client):
        """enrich_person should require linkedin_url or email."""
        from sdrbot_cli.services.lusha.tools import lusha_enrich_person

        import sdrbot_cli.services.lusha.tools as tools_module
        tools_module._lusha_client = None

        result = lusha_enrich_person.invoke({})

        assert "Must provide either" in result or "Error" in result

    def test_enrich_person_not_found(self, patch_lusha_client):
        """enrich_person should handle not found."""
        patch_lusha_client.request.return_value = {"data": None}

        from sdrbot_cli.services.lusha.tools import lusha_enrich_person

        import sdrbot_cli.services.lusha.tools as tools_module
        tools_module._lusha_client = None

        result = lusha_enrich_person.invoke({
            "email": "unknown@example.com"
        })

        assert "No data found" in result

    def test_enrich_company_success(self, patch_lusha_client):
        """enrich_company should return company info."""
        patch_lusha_client.request.return_value = {
            "data": {
                "name": "Example Inc",
                "industryPrimaryGroup": "Technology",
                "employeesSize": "100-500",
                "revenueRange": "$10M-$50M",
                "social": {"linkedin": "https://linkedin.com/company/example"},
                "description": "A great company doing great things."
            }
        }

        from sdrbot_cli.services.lusha.tools import lusha_enrich_company

        import sdrbot_cli.services.lusha.tools as tools_module
        tools_module._lusha_client = None

        result = lusha_enrich_company.invoke({"domain": "example.com"})

        assert "Example Inc" in result
        assert "Technology" in result
        assert "100-500" in result

    def test_prospect_success(self, patch_lusha_client):
        """prospect should return matching contacts."""
        patch_lusha_client.request.return_value = {
            "data": {
                "contacts": [
                    {
                        "fullName": "John Doe",
                        "jobTitle": "CTO",
                        "company": {"name": "Tech Corp"},
                        "social": {"linkedin": "https://linkedin.com/in/johndoe"}
                    },
                    {
                        "fullName": "Jane Smith",
                        "jobTitle": "CTO",
                        "company": {"name": "Other Corp"},
                        "social": {"linkedin": "https://linkedin.com/in/janesmith"}
                    }
                ]
            }
        }

        from sdrbot_cli.services.lusha.tools import lusha_prospect

        import sdrbot_cli.services.lusha.tools as tools_module
        tools_module._lusha_client = None

        result = lusha_prospect.invoke({
            "filters_json": '{"jobTitle": ["CTO"]}'
        })

        assert "John Doe" in result
        assert "Jane Smith" in result
        assert "2 prospects" in result

    def test_prospect_no_results(self, patch_lusha_client):
        """prospect should handle no matches."""
        patch_lusha_client.request.return_value = {
            "data": {"contacts": []}
        }

        from sdrbot_cli.services.lusha.tools import lusha_prospect

        import sdrbot_cli.services.lusha.tools as tools_module
        tools_module._lusha_client = None

        result = lusha_prospect.invoke({
            "filters_json": '{"jobTitle": ["NonexistentRole"]}'
        })

        assert "No prospects found" in result

    def test_prospect_invalid_json(self, patch_lusha_client):
        """prospect should handle invalid JSON."""
        from sdrbot_cli.services.lusha.tools import lusha_prospect

        import sdrbot_cli.services.lusha.tools as tools_module
        tools_module._lusha_client = None

        result = lusha_prospect.invoke({
            "filters_json": "not valid json"
        })

        assert "Error" in result
