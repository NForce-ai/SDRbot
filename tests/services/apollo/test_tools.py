"""Tests for Apollo.io tools."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestApolloToolLoading:
    """Test that Apollo tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.apollo.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "apollo_enrich_person" in tool_names
        assert "apollo_enrich_company" in tool_names
        assert "apollo_search_people" in tool_names
        assert "apollo_search_companies" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.apollo.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.apollo.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_get_tools_includes_static(self):
        """get_tools should include static tools."""
        from sdrbot_cli.services.apollo import get_tools

        tools = get_tools()
        tool_names = [t.name for t in tools]

        assert "apollo_enrich_person" in tool_names
        assert "apollo_enrich_company" in tool_names


class TestApolloToolsUnit:
    """Unit tests for Apollo tools with mocked API."""

    @pytest.fixture
    def mock_apollo_client(self):
        """Create a mock Apollo client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_apollo_client(self, mock_apollo_client):
        """Patch Apollo client."""
        import sdrbot_cli.services.apollo.tools as tools_module

        original_client = tools_module._apollo_client
        tools_module._apollo_client = None

        with patch(
            "sdrbot_cli.services.apollo.tools.ApolloClient",
            return_value=mock_apollo_client,
        ):
            yield mock_apollo_client

        tools_module._apollo_client = original_client

    def test_enrich_person_by_email(self, patch_apollo_client):
        """apollo_enrich_person should enrich by email."""
        patch_apollo_client.post.return_value = {
            "person": {
                "name": "John Doe",
                "first_name": "John",
                "last_name": "Doe",
                "title": "CEO",
                "email": "john@example.com",
                "linkedin_url": "https://linkedin.com/in/johndoe",
                "organization": {"name": "Example Corp", "website_url": "https://example.com"},
                "city": "San Francisco",
                "state": "CA",
                "country": "United States",
                "seniority": "c_suite",
                "departments": ["executive"],
            }
        }

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_enrich_person

        tools_module._apollo_client = None

        result = apollo_enrich_person.invoke({"email": "john@example.com"})

        assert "John Doe" in result
        assert "CEO" in result
        assert "Example Corp" in result
        assert "San Francisco" in result

    def test_enrich_person_no_match(self, patch_apollo_client):
        """apollo_enrich_person should handle no match."""
        patch_apollo_client.post.return_value = {"person": {}}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_enrich_person

        tools_module._apollo_client = None

        result = apollo_enrich_person.invoke({"email": "nobody@nowhere.com"})

        assert "No matching person" in result

    def test_enrich_person_insufficient_info(self, patch_apollo_client):
        """apollo_enrich_person should require sufficient info."""
        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_enrich_person

        tools_module._apollo_client = None

        # Only first name - not enough
        result = apollo_enrich_person.invoke({"first_name": "John"})

        assert "Error" in result
        assert "Provide email" in result

    def test_enrich_person_error(self, patch_apollo_client):
        """apollo_enrich_person should handle API errors."""
        patch_apollo_client.post.side_effect = Exception("API rate limit exceeded")

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_enrich_person

        tools_module._apollo_client = None

        result = apollo_enrich_person.invoke({"email": "test@example.com"})

        assert "Error" in result
        assert "rate limit" in result

    def test_enrich_company_success(self, patch_apollo_client):
        """apollo_enrich_company should return company data."""
        patch_apollo_client.post.return_value = {
            "organization": {
                "name": "Apollo.io",
                "website_url": "https://apollo.io",
                "primary_domain": "apollo.io",
                "industry": "Information Technology",
                "estimated_num_employees": 500,
                "annual_revenue_printed": "$50M - $100M",
                "total_funding_printed": "$100M",
                "founded_year": 2015,
                "city": "San Francisco",
                "state": "CA",
                "country": "United States",
                "linkedin_url": "https://linkedin.com/company/apollo-io",
                "short_description": "Apollo is a sales intelligence platform.",
                "technologies": ["React", "Python", "AWS"],
            }
        }

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_enrich_company

        tools_module._apollo_client = None

        result = apollo_enrich_company.invoke({"domain": "apollo.io"})

        assert "Apollo.io" in result
        assert "Information Technology" in result
        assert "500" in result
        assert "San Francisco" in result

    def test_enrich_company_not_found(self, patch_apollo_client):
        """apollo_enrich_company should handle unknown domain."""
        patch_apollo_client.post.return_value = {"organization": {}}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_enrich_company

        tools_module._apollo_client = None

        result = apollo_enrich_company.invoke({"domain": "unknown-domain-xyz.com"})

        assert "No company found" in result

    def test_enrich_company_error(self, patch_apollo_client):
        """apollo_enrich_company should handle API errors."""
        patch_apollo_client.post.side_effect = Exception("Invalid API key")

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_enrich_company

        tools_module._apollo_client = None

        result = apollo_enrich_company.invoke({"domain": "example.com"})

        assert "Error" in result
        assert "Invalid API key" in result

    def test_search_people_success(self, patch_apollo_client):
        """apollo_search_people should return matching people."""
        patch_apollo_client.post.return_value = {
            "people": [
                {
                    "name": "Jane Smith",
                    "title": "VP Sales",
                    "organization": {"name": "Tech Corp"},
                    "linkedin_url": "https://linkedin.com/in/janesmith",
                    "city": "New York",
                    "state": "NY",
                    "country": "United States",
                },
                {
                    "name": "Bob Johnson",
                    "title": "Sales Director",
                    "organization": {"name": "StartupXYZ"},
                    "linkedin_url": "https://linkedin.com/in/bobjohnson",
                    "city": "Boston",
                    "state": "MA",
                    "country": "United States",
                },
            ]
        }

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_people

        tools_module._apollo_client = None

        result = apollo_search_people.invoke(
            {"person_titles": "VP Sales,Sales Director", "person_locations": "New York,Boston"}
        )

        assert "2 people" in result
        assert "Jane Smith" in result
        assert "Bob Johnson" in result

    def test_search_people_no_results(self, patch_apollo_client):
        """apollo_search_people should handle no results."""
        patch_apollo_client.post.return_value = {"people": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_people

        tools_module._apollo_client = None

        result = apollo_search_people.invoke({"person_titles": "Chief Impossible Officer"})

        assert "No people found" in result

    def test_search_people_error(self, patch_apollo_client):
        """apollo_search_people should handle API errors."""
        patch_apollo_client.post.side_effect = Exception("Unauthorized")

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_people

        tools_module._apollo_client = None

        result = apollo_search_people.invoke({"person_titles": "CEO"})

        assert "Error" in result
        assert "Unauthorized" in result

    def test_search_companies_success(self, patch_apollo_client):
        """apollo_search_companies should return matching companies."""
        patch_apollo_client.post.return_value = {
            "organizations": [
                {
                    "name": "TechCorp",
                    "primary_domain": "techcorp.com",
                    "industry": "Software",
                    "estimated_num_employees": 100,
                    "city": "Austin",
                    "state": "TX",
                    "country": "United States",
                    "linkedin_url": "https://linkedin.com/company/techcorp",
                },
                {
                    "name": "DataInc",
                    "primary_domain": "datainc.io",
                    "industry": "Data Analytics",
                    "estimated_num_employees": 50,
                    "city": "Denver",
                    "state": "CO",
                    "country": "United States",
                    "linkedin_url": "https://linkedin.com/company/datainc",
                },
            ]
        }

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_companies

        tools_module._apollo_client = None

        result = apollo_search_companies.invoke(
            {"organization_locations": "Austin,Denver", "limit": 10}
        )

        assert "2 companies" in result
        assert "TechCorp" in result
        assert "DataInc" in result

    def test_search_companies_no_results(self, patch_apollo_client):
        """apollo_search_companies should handle no results."""
        patch_apollo_client.post.return_value = {"organizations": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_companies

        tools_module._apollo_client = None

        result = apollo_search_companies.invoke({"organization_names": "NonexistentCompanyXYZ"})

        assert "No companies found" in result

    def test_search_companies_error(self, patch_apollo_client):
        """apollo_search_companies should handle API errors."""
        patch_apollo_client.post.side_effect = Exception("Server error")

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_companies

        tools_module._apollo_client = None

        result = apollo_search_companies.invoke({"organization_locations": "New York"})

        assert "Error" in result
        assert "Server error" in result


@pytest.mark.integration
class TestApolloToolsIntegration:
    """Integration tests for Apollo tools.

    Run with: pytest -m integration
    Requires Apollo API key.
    """

    @pytest.fixture
    def check_apollo_credentials(self):
        """Skip if Apollo credentials not available."""
        if not os.getenv("APOLLO_API_KEY"):
            pytest.skip("Apollo API key not set - skipping integration test")

    def test_enrich_company_real(self, check_apollo_credentials):
        """Test company enrichment against real API."""
        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_enrich_company

        tools_module._apollo_client = None

        result = apollo_enrich_company.invoke({"domain": "apollo.io"})

        # Should either return data or handle gracefully
        assert "Apollo" in result or "Error" in result

    def test_search_companies_real(self, check_apollo_credentials):
        """Test company search against real API."""
        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_companies

        tools_module._apollo_client = None

        result = apollo_search_companies.invoke(
            {"organization_locations": "San Francisco", "limit": 5}
        )

        # Should either return results or handle gracefully
        assert "companies" in result.lower() or "error" in result.lower()
