"""Tests for Hunter.io tools."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestHunterToolLoading:
    """Test that Hunter tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.hunter.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "hunter_domain_search" in tool_names
        assert "hunter_email_finder" in tool_names
        assert "hunter_email_verifier" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.hunter.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.hunter.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"


class TestHunterToolsUnit:
    """Unit tests for Hunter tools with mocked API."""

    @pytest.fixture
    def mock_hunter_client(self):
        """Create a mock Hunter client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_hunter_client(self, mock_hunter_client):
        """Patch Hunter client."""
        import sdrbot_cli.services.hunter.tools as tools_module

        original_client = tools_module._hunter_client
        tools_module._hunter_client = None

        with patch("sdrbot_cli.services.hunter.tools.HunterClient", return_value=mock_hunter_client):
            yield mock_hunter_client

        tools_module._hunter_client = original_client

    def test_domain_search_success(self, patch_hunter_client):
        """domain_search should return formatted results."""
        patch_hunter_client.request.return_value = {
            "data": {
                "emails": [
                    {
                        "value": "john@example.com",
                        "type": "personal",
                        "first_name": "John",
                        "last_name": "Doe",
                        "position": "CEO"
                    },
                    {
                        "value": "jane@example.com",
                        "type": "generic",
                        "first_name": "Jane",
                        "last_name": "Smith",
                        "position": "CTO"
                    }
                ]
            }
        }

        from sdrbot_cli.services.hunter.tools import hunter_domain_search

        import sdrbot_cli.services.hunter.tools as tools_module
        tools_module._hunter_client = None

        result = hunter_domain_search.invoke({"domain": "example.com", "limit": 10})

        assert "john@example.com" in result
        assert "jane@example.com" in result
        assert "CEO" in result
        assert "2 found" in result

    def test_domain_search_no_results(self, patch_hunter_client):
        """domain_search should handle empty results."""
        patch_hunter_client.request.return_value = {
            "data": {"emails": []}
        }

        from sdrbot_cli.services.hunter.tools import hunter_domain_search

        import sdrbot_cli.services.hunter.tools as tools_module
        tools_module._hunter_client = None

        result = hunter_domain_search.invoke({"domain": "unknown.com", "limit": 10})

        assert "No emails found" in result

    def test_domain_search_error(self, patch_hunter_client):
        """domain_search should handle API errors."""
        patch_hunter_client.request.side_effect = Exception("API Error")

        from sdrbot_cli.services.hunter.tools import hunter_domain_search

        import sdrbot_cli.services.hunter.tools as tools_module
        tools_module._hunter_client = None

        result = hunter_domain_search.invoke({"domain": "error.com", "limit": 10})

        assert "Error" in result
        assert "API Error" in result

    def test_email_finder_success(self, patch_hunter_client):
        """email_finder should return found email."""
        patch_hunter_client.request.return_value = {
            "data": {
                "email": "john.doe@example.com",
                "score": 95
            }
        }

        from sdrbot_cli.services.hunter.tools import hunter_email_finder

        import sdrbot_cli.services.hunter.tools as tools_module
        tools_module._hunter_client = None

        result = hunter_email_finder.invoke({
            "domain": "example.com",
            "first_name": "John",
            "last_name": "Doe"
        })

        assert "john.doe@example.com" in result
        assert "95%" in result

    def test_email_finder_not_found(self, patch_hunter_client):
        """email_finder should handle not found."""
        patch_hunter_client.request.return_value = {
            "data": {"email": None}
        }

        from sdrbot_cli.services.hunter.tools import hunter_email_finder

        import sdrbot_cli.services.hunter.tools as tools_module
        tools_module._hunter_client = None

        result = hunter_email_finder.invoke({
            "domain": "example.com",
            "first_name": "Unknown",
            "last_name": "Person"
        })

        assert "not found" in result.lower()

    def test_email_verifier_success(self, patch_hunter_client):
        """email_verifier should return verification status."""
        patch_hunter_client.request.return_value = {
            "data": {
                "status": "valid",
                "score": 98
            }
        }

        from sdrbot_cli.services.hunter.tools import hunter_email_verifier

        import sdrbot_cli.services.hunter.tools as tools_module
        tools_module._hunter_client = None

        result = hunter_email_verifier.invoke({"email": "test@example.com"})

        assert "valid" in result
        assert "98%" in result


@pytest.mark.integration
class TestHunterToolsIntegration:
    """Integration tests for Hunter tools.

    Run with: pytest -m integration
    Requires HUNTER_API_KEY in environment.
    """

    @pytest.fixture
    def check_hunter_key(self):
        """Skip if Hunter API key not available."""
        if not os.getenv("HUNTER_API_KEY"):
            pytest.skip("HUNTER_API_KEY not set - skipping integration test")

    def test_domain_search_real(self, check_hunter_key):
        """Test domain search against real API."""
        from sdrbot_cli.services.hunter.tools import hunter_domain_search

        import sdrbot_cli.services.hunter.tools as tools_module
        tools_module._hunter_client = None

        result = hunter_domain_search.invoke({"domain": "stripe.com", "limit": 3})

        # Should either find emails or handle gracefully
        assert "stripe.com" in result.lower() or "error" in result.lower()

    def test_email_verifier_real(self, check_hunter_key):
        """Test email verification against real API."""
        from sdrbot_cli.services.hunter.tools import hunter_email_verifier

        import sdrbot_cli.services.hunter.tools as tools_module
        tools_module._hunter_client = None

        result = hunter_email_verifier.invoke({"email": "test@gmail.com"})

        # Should return some verification result
        assert "status" in result.lower() or "error" in result.lower()
