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

    def test_search_companies_passes_technographic_filters(self, patch_apollo_client):
        """apollo_search_companies should forward technographic + revenue + funding filters."""
        patch_apollo_client.post.return_value = {"organizations": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_companies

        tools_module._apollo_client = None

        apollo_search_companies.invoke(
            {
                "organization_keywords": "solar installer",
                "organization_locations": "United States",
                "organization_not_locations": "California",
                "technologies": "hubspot,chili_piper",
                "revenue_min_usd": 1000000,
                "revenue_max_usd": 50000000,
                "total_funding_min_usd": 500000,
                "total_funding_max_usd": 25000000,
                "limit": 5,
            }
        )

        patch_apollo_client.post.assert_called_once()
        call = patch_apollo_client.post.call_args
        assert call.args[0] == "/mixed_companies/search"
        sent = call.kwargs["json"]

        assert sent["currently_using_any_of_technology_uids"] == ["hubspot", "chili_piper"]
        assert sent["organization_not_locations"] == ["California"]
        assert sent["revenue_range[min]"] == 1000000
        assert sent["revenue_range[max]"] == 50000000
        assert sent["total_funding_range[min]"] == 500000
        assert sent["total_funding_range[max]"] == 25000000
        assert sent["per_page"] == 5

    def test_search_companies_omits_unset_filters(self, patch_apollo_client):
        """Filters that are not provided should not appear in the request."""
        patch_apollo_client.post.return_value = {"organizations": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_companies

        tools_module._apollo_client = None

        apollo_search_companies.invoke({"organization_locations": "Austin"})

        sent = patch_apollo_client.post.call_args.kwargs["json"]
        assert "currently_using_any_of_technology_uids" not in sent
        assert "revenue_range[min]" not in sent
        assert "total_funding_range[max]" not in sent
        assert "organization_not_locations" not in sent

    def test_search_people_passes_technographic_filters(self, patch_apollo_client):
        """apollo_search_people should forward technographic + revenue filters."""
        patch_apollo_client.post.return_value = {"people": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_people

        tools_module._apollo_client = None

        apollo_search_people.invoke(
            {
                "person_titles": "VP Sales",
                "technologies": "salesforce",
                "technologies_all": "salesforce,marketo",
                "technologies_exclude": "hubspot",
                "revenue_min_usd": 10000000,
                "revenue_max_usd": 500000000,
            }
        )

        sent = patch_apollo_client.post.call_args.kwargs["json"]
        assert sent["currently_using_any_of_technology_uids"] == ["salesforce"]
        assert sent["currently_using_all_of_technology_uids"] == ["salesforce", "marketo"]
        assert sent["currently_not_using_any_of_technology_uids"] == ["hubspot"]
        assert sent["revenue_range[min]"] == 10000000
        assert sent["revenue_range[max]"] == 500000000

    def test_search_people_forwards_email_status_and_keywords(self, patch_apollo_client):
        """Email status + free-text keywords + exact-title mode should flow through."""
        patch_apollo_client.post.return_value = {"people": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_people

        tools_module._apollo_client = None

        apollo_search_people.invoke(
            {
                "person_titles": "VP Sales",
                "include_similar_titles": False,
                "contact_email_status": "verified,likely_to_engage",
                "q_keywords": "fintech sales leader",
            }
        )

        sent = patch_apollo_client.post.call_args.kwargs["json"]
        assert sent["include_similar_titles"] is False
        assert sent["contact_email_status"] == ["verified", "likely_to_engage"]
        assert sent["q_keywords"] == "fintech sales leader"

    def test_search_people_forwards_hiring_signals(self, patch_apollo_client):
        """Hiring-signal bundle should map to organization_job_* params."""
        patch_apollo_client.post.return_value = {"people": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_people

        tools_module._apollo_client = None

        apollo_search_people.invoke(
            {
                "org_hiring_job_titles": "VP Sales,Account Executive",
                "org_hiring_locations": "New York,Boston",
                "org_num_jobs_min": 5,
                "org_num_jobs_max": 100,
                "org_job_posted_after": "2026-03-01",
                "org_job_posted_before": "2026-04-13",
            }
        )

        sent = patch_apollo_client.post.call_args.kwargs["json"]
        assert sent["q_organization_job_titles"] == ["VP Sales", "Account Executive"]
        assert sent["organization_job_locations"] == ["New York", "Boston"]
        assert sent["organization_num_jobs_range[min]"] == 5
        assert sent["organization_num_jobs_range[max]"] == 100
        assert sent["organization_job_posted_at_range[min]"] == "2026-03-01"
        assert sent["organization_job_posted_at_range[max]"] == "2026-04-13"

    def test_search_people_uses_api_search_endpoint(self, patch_apollo_client):
        """People search must hit /mixed_people/api_search, not the deprecated path."""
        patch_apollo_client.post.return_value = {"people": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_people

        tools_module._apollo_client = None

        apollo_search_people.invoke({"person_titles": "CEO"})

        assert patch_apollo_client.post.call_args.args[0] == "/mixed_people/api_search"

    def test_search_people_employee_ranges_serialize_as_strings(self, patch_apollo_client):
        """Employee ranges must be sent as Apollo-format strings, not {min,max} dicts."""
        patch_apollo_client.post.return_value = {"people": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_people

        tools_module._apollo_client = None

        apollo_search_people.invoke(
            {"person_titles": "CEO", "organization_num_employees_ranges": "11,50;51,200"}
        )

        sent = patch_apollo_client.post.call_args.kwargs["json"]
        assert sent["organization_num_employees_ranges"] == ["11,50", "51,200"]

    def test_search_companies_employee_ranges_serialize_as_strings(self, patch_apollo_client):
        """Companies search must also send employee ranges as strings."""
        patch_apollo_client.post.return_value = {"organizations": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_companies

        tools_module._apollo_client = None

        apollo_search_companies.invoke(
            {
                "organization_locations": "United States",
                "organization_num_employees_ranges": "11,200",
            }
        )

        sent = patch_apollo_client.post.call_args.kwargs["json"]
        assert sent["organization_num_employees_ranges"] == ["11,200"]

    def test_search_companies_forwards_hiring_and_funding_bundle(self, patch_apollo_client):
        """Hiring-signal + latest-funding bundle should flow through."""
        patch_apollo_client.post.return_value = {"organizations": []}

        import sdrbot_cli.services.apollo.tools as tools_module
        from sdrbot_cli.services.apollo.tools import apollo_search_companies

        tools_module._apollo_client = None

        apollo_search_companies.invoke(
            {
                "technologies_all": "salesforce,marketo",
                "technologies_exclude": "mailchimp",
                "latest_funding_min_usd": 5000000,
                "latest_funding_max_usd": 100000000,
                "latest_funding_after": "2025-10-01",
                "latest_funding_before": "2026-04-13",
                "hiring_job_titles": "VP Engineering",
                "hiring_locations": "Remote,United States",
                "num_jobs_min": 3,
                "num_jobs_max": 50,
                "job_posted_after": "2026-03-15",
                "job_posted_before": "2026-04-13",
            }
        )

        sent = patch_apollo_client.post.call_args.kwargs["json"]
        assert sent["currently_using_all_of_technology_uids"] == ["salesforce", "marketo"]
        assert sent["currently_not_using_any_of_technology_uids"] == ["mailchimp"]
        assert sent["latest_funding_amount_range[min]"] == 5000000
        assert sent["latest_funding_amount_range[max]"] == 100000000
        assert sent["latest_funding_date_range[min]"] == "2025-10-01"
        assert sent["latest_funding_date_range[max]"] == "2026-04-13"
        assert sent["q_organization_job_titles"] == ["VP Engineering"]
        assert sent["organization_job_locations"] == ["Remote", "United States"]
        assert sent["organization_num_jobs_range[min]"] == 3
        assert sent["organization_num_jobs_range[max]"] == 50
        assert sent["organization_job_posted_at_range[min]"] == "2026-03-15"
        assert sent["organization_job_posted_at_range[max]"] == "2026-04-13"


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
