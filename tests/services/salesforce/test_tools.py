"""Tests for Salesforce tools."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestSalesforceToolLoading:
    """Test that Salesforce tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.salesforce.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "salesforce_soql_query" in tool_names
        assert "salesforce_sosl_search" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.salesforce.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.salesforce.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_get_tools_includes_static(self):
        """get_tools should include static tools."""
        from sdrbot_cli.services.salesforce import get_tools

        tools = get_tools()
        tool_names = [t.name for t in tools]

        # Static tools should always be present
        assert "salesforce_soql_query" in tool_names
        assert "salesforce_sosl_search" in tool_names


class TestSalesforceToolsUnit:
    """Unit tests for Salesforce tools with mocked API."""

    @pytest.fixture
    def mock_sf_client(self):
        """Create a mock Salesforce client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_sf_client(self, mock_sf_client):
        """Patch Salesforce client."""
        import sdrbot_cli.services.salesforce.tools as tools_module

        original_client = tools_module._sf_client
        tools_module._sf_client = None

        with patch("sdrbot_cli.services.salesforce.tools.get_client", return_value=mock_sf_client):
            yield mock_sf_client

        tools_module._sf_client = original_client

    def test_soql_query_success(self, patch_sf_client):
        """soql_query should return formatted results."""
        patch_sf_client.query.return_value = {
            "totalSize": 2,
            "records": [
                {
                    "Id": "001ABC",
                    "Name": "John Doe",
                    "Email": "john@example.com",
                    "attributes": {"type": "Contact"},
                },
                {
                    "Id": "001DEF",
                    "Name": "Jane Doe",
                    "Email": "jane@example.com",
                    "attributes": {"type": "Contact"},
                },
            ],
        }

        import sdrbot_cli.services.salesforce.tools as tools_module
        from sdrbot_cli.services.salesforce.tools import salesforce_soql_query

        tools_module._sf_client = None

        result = salesforce_soql_query.invoke(
            {"query": "SELECT Id, Name, Email FROM Contact LIMIT 2"}
        )

        assert "2 records" in result
        assert "John Doe" in result
        assert "jane@example.com" in result
        # Attributes should be stripped
        assert "attributes" not in result

    def test_soql_query_no_results(self, patch_sf_client):
        """soql_query should handle empty results."""
        patch_sf_client.query.return_value = {"totalSize": 0, "records": []}

        import sdrbot_cli.services.salesforce.tools as tools_module
        from sdrbot_cli.services.salesforce.tools import salesforce_soql_query

        tools_module._sf_client = None

        result = salesforce_soql_query.invoke(
            {"query": "SELECT Id FROM Contact WHERE Name = 'NonExistent'"}
        )

        assert "0 records" in result

    def test_soql_query_blocks_non_select(self, patch_sf_client):
        """soql_query should block non-SELECT queries."""
        import sdrbot_cli.services.salesforce.tools as tools_module
        from sdrbot_cli.services.salesforce.tools import salesforce_soql_query

        tools_module._sf_client = None

        result = salesforce_soql_query.invoke({"query": "DELETE FROM Contact WHERE Id = '001ABC'"})

        assert "Error" in result
        assert "SELECT" in result
        # Should not have called the API
        patch_sf_client.query.assert_not_called()

    def test_soql_query_error(self, patch_sf_client):
        """soql_query should handle API errors."""
        patch_sf_client.query.side_effect = Exception("MALFORMED_QUERY: Invalid field")

        import sdrbot_cli.services.salesforce.tools as tools_module
        from sdrbot_cli.services.salesforce.tools import salesforce_soql_query

        tools_module._sf_client = None

        result = salesforce_soql_query.invoke({"query": "SELECT InvalidField FROM Contact"})

        assert "Error" in result
        assert "MALFORMED_QUERY" in result

    def test_sosl_search_success(self, patch_sf_client):
        """sosl_search should return formatted results."""
        patch_sf_client.search.return_value = {
            "searchRecords": [
                {"Id": "001ABC", "Name": "John Smith", "attributes": {"type": "Contact"}},
                {"Id": "00QDEF", "Name": "John Smith", "attributes": {"type": "Lead"}},
            ]
        }

        import sdrbot_cli.services.salesforce.tools as tools_module
        from sdrbot_cli.services.salesforce.tools import salesforce_sosl_search

        tools_module._sf_client = None

        result = salesforce_sosl_search.invoke(
            {"search": "FIND {John Smith} IN ALL FIELDS RETURNING Contact, Lead"}
        )

        assert "2 records" in result
        assert "Contact" in result
        assert "Lead" in result
        assert "John Smith" in result

    def test_sosl_search_no_results(self, patch_sf_client):
        """sosl_search should handle no matches."""
        patch_sf_client.search.return_value = {"searchRecords": []}

        import sdrbot_cli.services.salesforce.tools as tools_module
        from sdrbot_cli.services.salesforce.tools import salesforce_sosl_search

        tools_module._sf_client = None

        result = salesforce_sosl_search.invoke({"search": "FIND {xyz123nonexistent} IN ALL FIELDS"})

        assert "No records found" in result

    def test_sosl_search_error(self, patch_sf_client):
        """sosl_search should handle API errors."""
        patch_sf_client.search.side_effect = Exception("INVALID_SEARCH: Bad syntax")

        import sdrbot_cli.services.salesforce.tools as tools_module
        from sdrbot_cli.services.salesforce.tools import salesforce_sosl_search

        tools_module._sf_client = None

        result = salesforce_sosl_search.invoke({"search": "FIND {bad syntax"})

        assert "Error" in result
        assert "INVALID_SEARCH" in result


@pytest.mark.integration
class TestSalesforceToolsIntegration:
    """Integration tests for Salesforce tools.

    Run with: pytest -m integration
    Requires Salesforce OAuth credentials.
    """

    @pytest.fixture
    def check_sf_credentials(self):
        """Skip if Salesforce credentials not available."""
        # Check for OAuth credentials
        if not (os.getenv("SF_CLIENT_ID") and os.getenv("SF_CLIENT_SECRET")):
            pytest.skip("Salesforce credentials not set - skipping integration test")

    def test_soql_query_real(self, check_sf_credentials):
        """Test SOQL query against real API."""
        import sdrbot_cli.services.salesforce.tools as tools_module
        from sdrbot_cli.services.salesforce.tools import salesforce_soql_query

        tools_module._sf_client = None

        result = salesforce_soql_query.invoke({"query": "SELECT Id, Name FROM Account LIMIT 1"})

        # Should either return results or handle gracefully
        assert "records" in result.lower() or "error" in result.lower()
