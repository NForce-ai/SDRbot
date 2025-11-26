"""Tests for HubSpot CRUD tool operations."""

from unittest.mock import MagicMock, patch

import pytest


class TestHubSpotStaticToolsUnit:
    """Unit tests for static HubSpot tools (mocked API)."""

    def test_list_pipelines_success(self, patch_hubspot_client):
        """list_pipelines should return formatted pipeline info."""
        from sdrbot_cli.services.hubspot.tools import hubspot_list_pipelines

        result = hubspot_list_pipelines.invoke({"object_type": "deals"})

        assert "Sales Pipeline" in result
        assert "Prospecting" in result
        patch_hubspot_client.crm.pipelines.pipelines_api.get_all.assert_called_once()

    def test_list_pipelines_error_handling(self, patch_hubspot_client):
        """list_pipelines should handle errors gracefully."""
        patch_hubspot_client.crm.pipelines.pipelines_api.get_all.side_effect = Exception(
            "API Error"
        )
        from sdrbot_cli.services.hubspot.tools import hubspot_list_pipelines

        result = hubspot_list_pipelines.invoke({"object_type": "deals"})

        assert "Error" in result
        assert "API Error" in result


class TestHubSpotGeneratedToolsUnit:
    """Unit tests for generated HubSpot tools (mocked API)."""

    def test_search_contacts_returns_results(self, patch_hubspot_client):
        """search_contacts should return formatted results."""
        # Setup mock response
        patch_hubspot_client.crm.objects.search_api.do_search.return_value = MagicMock(
            total=1,
            results=[
                MagicMock(
                    id="123",
                    properties={"email": "test@example.com", "firstname": "Test"}
                )
            ]
        )

        from sdrbot_cli.services.hubspot.tools_generated import hubspot_search_contacts

        # Reset cached client to use mock
        import sdrbot_cli.services.hubspot.tools_generated as gen_module
        gen_module._hs_client = None

        with patch("sdrbot_cli.services.hubspot.tools_generated.get_client", return_value=patch_hubspot_client):
            result = hubspot_search_contacts.invoke({"limit": 10})

        assert "Found 1 contacts" in result
        assert "123" in result

    def test_search_contacts_no_results(self, patch_hubspot_client):
        """search_contacts should handle empty results."""
        patch_hubspot_client.crm.objects.search_api.do_search.return_value = MagicMock(
            total=0,
            results=[]
        )

        from sdrbot_cli.services.hubspot.tools_generated import hubspot_search_contacts

        import sdrbot_cli.services.hubspot.tools_generated as gen_module
        gen_module._hs_client = None

        with patch("sdrbot_cli.services.hubspot.tools_generated.get_client", return_value=patch_hubspot_client):
            result = hubspot_search_contacts.invoke({"limit": 10})

        assert "No contacts found" in result

    def test_create_contact_success(self, patch_hubspot_client):
        """create_contact should return success with new ID."""
        patch_hubspot_client.crm.objects.basic_api.create.return_value = MagicMock(id="456")

        from sdrbot_cli.services.hubspot.tools_generated import hubspot_create_contact

        import sdrbot_cli.services.hubspot.tools_generated as gen_module
        gen_module._hs_client = None

        with patch("sdrbot_cli.services.hubspot.tools_generated.get_client", return_value=patch_hubspot_client):
            result = hubspot_create_contact.invoke({
                "email": "new@example.com",
                "firstname": "New",
                "lastname": "Contact"
            })

        assert "Successfully created contact" in result
        assert "456" in result

    def test_create_contact_requires_properties(self, patch_hubspot_client):
        """create_contact should error if no properties provided."""
        from sdrbot_cli.services.hubspot.tools_generated import hubspot_create_contact

        import sdrbot_cli.services.hubspot.tools_generated as gen_module
        gen_module._hs_client = None

        with patch("sdrbot_cli.services.hubspot.tools_generated.get_client", return_value=patch_hubspot_client):
            result = hubspot_create_contact.invoke({})

        assert "Error" in result or "At least one property" in result


@pytest.mark.integration
class TestHubSpotCRUDIntegration:
    """Integration tests that hit real HubSpot API.

    Run with: pytest -m integration
    Requires HUBSPOT_ACCESS_TOKEN in environment.
    """

    def test_list_pipelines_real(self, real_hubspot_client):
        """Test listing pipelines against real API."""
        from sdrbot_cli.services.hubspot.tools import hubspot_list_pipelines, reset_client

        reset_client()  # Clear any cached client

        result = hubspot_list_pipelines.invoke({"object_type": "deals"})

        assert "Pipeline" in result or "Error" not in result

    def test_search_contacts_real(self, real_hubspot_client):
        """Test searching contacts against real API."""
        from sdrbot_cli.services.hubspot.tools_generated import hubspot_search_contacts

        import sdrbot_cli.services.hubspot.tools_generated as gen_module
        gen_module._hs_client = None

        result = hubspot_search_contacts.invoke({"limit": 1})

        # Should either find contacts or say none found
        assert "contacts" in result.lower() or "found" in result.lower()

    def test_get_contact_real(self, real_hubspot_client):
        """Test getting a specific contact."""
        from sdrbot_cli.services.hubspot.tools_generated import (
            hubspot_search_contacts,
            hubspot_get_contact,
        )
        import json

        import sdrbot_cli.services.hubspot.tools_generated as gen_module
        gen_module._hs_client = None

        # First find a contact
        search_result = hubspot_search_contacts.invoke({"limit": 1})

        if "No contacts found" in search_result:
            pytest.skip("No contacts in HubSpot to test with")

        # Extract ID from search result
        # Result format: "Found X contacts:\n[{id: ..., properties: ...}]"
        try:
            json_start = search_result.find("[")
            if json_start != -1:
                contacts = json.loads(search_result[json_start:])
                contact_id = contacts[0]["id"]

                result = hubspot_get_contact.invoke({"contact_id": contact_id})
                assert contact_id in result or "Contact" in result
        except (json.JSONDecodeError, KeyError, IndexError):
            pytest.skip("Could not parse contact ID from search result")
