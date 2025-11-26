"""Tests for HubSpot association tools."""

from unittest.mock import MagicMock, patch

import pytest


class TestAssociationToolsUnit:
    """Unit tests for association tools (mocked API)."""

    def test_create_association_uses_correct_params(self, patch_hubspot_client):
        """create_association should use object_type/object_id params."""
        from sdrbot_cli.services.hubspot.tools import hubspot_create_association, reset_client
        reset_client()

        result = hubspot_create_association.invoke({
            "from_object_type": "contacts",
            "from_object_id": "123",
            "to_object_type": "deals",
            "to_object_id": "456",
        })

        # Verify the correct parameter names were used
        patch_hubspot_client.crm.associations.v4.basic_api.create.assert_called_once()
        call_kwargs = patch_hubspot_client.crm.associations.v4.basic_api.create.call_args.kwargs

        # Should use object_type/object_id, NOT from_object_type/from_object_id
        assert "object_type" in call_kwargs
        assert "object_id" in call_kwargs
        assert call_kwargs["object_type"] == "contacts"
        assert call_kwargs["object_id"] == "123"
        assert call_kwargs["to_object_type"] == "deals"
        assert call_kwargs["to_object_id"] == "456"

    def test_create_association_success_message(self, patch_hubspot_client):
        """create_association should return success message."""
        from sdrbot_cli.services.hubspot.tools import hubspot_create_association, reset_client
        reset_client()

        result = hubspot_create_association.invoke({
            "from_object_type": "contacts",
            "from_object_id": "123",
            "to_object_type": "deals",
            "to_object_id": "456",
        })

        assert "Successfully associated" in result
        assert "contacts/123" in result
        assert "deals/456" in result

    def test_create_association_no_types_found(self, patch_hubspot_client):
        """create_association should handle missing association types."""
        # Override the default mock to return empty results
        patch_hubspot_client.crm.associations.v4.schema.definitions_api.get_all.return_value = MagicMock(
            results=[]
        )

        from sdrbot_cli.services.hubspot.tools import hubspot_create_association, reset_client
        reset_client()  # Clear cached client to use mock

        result = hubspot_create_association.invoke({
            "from_object_type": "contacts",
            "from_object_id": "123",
            "to_object_type": "widgets",  # Fake object type
            "to_object_id": "456",
        })

        assert "No association types found" in result

    def test_list_associations_uses_correct_params(self, patch_hubspot_client):
        """list_associations should use object_type/object_id params."""
        patch_hubspot_client.crm.associations.v4.basic_api.get_page.return_value = MagicMock(
            results=[]
        )

        from sdrbot_cli.services.hubspot.tools import hubspot_list_associations, reset_client
        reset_client()

        result = hubspot_list_associations.invoke({
            "from_object_type": "contacts",
            "from_object_id": "123",
            "to_object_type": "deals",
        })

        call_kwargs = patch_hubspot_client.crm.associations.v4.basic_api.get_page.call_args.kwargs

        # Should use object_type/object_id
        assert "object_type" in call_kwargs
        assert "object_id" in call_kwargs
        assert call_kwargs["object_type"] == "contacts"
        assert call_kwargs["object_id"] == "123"

    def test_list_associations_returns_ids(self, patch_hubspot_client):
        """list_associations should return associated record IDs."""
        patch_hubspot_client.crm.associations.v4.basic_api.get_page.return_value = MagicMock(
            results=[
                MagicMock(to_object_id="deal1"),
                MagicMock(to_object_id="deal2"),
            ]
        )

        from sdrbot_cli.services.hubspot.tools import hubspot_list_associations, reset_client
        reset_client()

        result = hubspot_list_associations.invoke({
            "from_object_type": "contacts",
            "from_object_id": "123",
            "to_object_type": "deals",
        })

        assert "deal1" in result
        assert "deal2" in result
        assert "Associated deals records" in result

    def test_list_associations_empty(self, patch_hubspot_client):
        """list_associations should handle no associations."""
        patch_hubspot_client.crm.associations.v4.basic_api.get_page.return_value = MagicMock(
            results=[]
        )

        from sdrbot_cli.services.hubspot.tools import hubspot_list_associations, reset_client
        reset_client()

        result = hubspot_list_associations.invoke({
            "from_object_type": "contacts",
            "from_object_id": "123",
            "to_object_type": "deals",
        })

        assert "No deals associated" in result

    def test_delete_association_uses_correct_params(self, patch_hubspot_client):
        """delete_association should use object_type/object_id params."""
        from sdrbot_cli.services.hubspot.tools import hubspot_delete_association, reset_client
        reset_client()

        result = hubspot_delete_association.invoke({
            "from_object_type": "contacts",
            "from_object_id": "123",
            "to_object_type": "deals",
            "to_object_id": "456",
        })

        call_kwargs = patch_hubspot_client.crm.associations.v4.basic_api.archive.call_args.kwargs

        # Should use object_type/object_id
        assert "object_type" in call_kwargs
        assert "object_id" in call_kwargs
        assert call_kwargs["object_type"] == "contacts"
        assert call_kwargs["object_id"] == "123"

    def test_delete_association_success(self, patch_hubspot_client):
        """delete_association should return success message."""
        from sdrbot_cli.services.hubspot.tools import hubspot_delete_association, reset_client
        reset_client()

        result = hubspot_delete_association.invoke({
            "from_object_type": "contacts",
            "from_object_id": "123",
            "to_object_type": "deals",
            "to_object_id": "456",
        })

        assert "Successfully removed association" in result


@pytest.mark.integration
class TestAssociationToolsIntegration:
    """Integration tests for associations against real API.

    Run with: pytest -m integration
    """

    def test_list_associations_real(self, real_hubspot_client):
        """Test listing associations against real API."""
        from sdrbot_cli.services.hubspot.tools import hubspot_list_associations, reset_client
        from sdrbot_cli.services.hubspot.tools_generated import hubspot_search_contacts
        import json

        reset_client()

        import sdrbot_cli.services.hubspot.tools_generated as gen_module
        gen_module._hs_client = None

        # Find a contact to test with
        search_result = hubspot_search_contacts.invoke({"limit": 1})

        if "No contacts found" in search_result:
            pytest.skip("No contacts in HubSpot to test with")

        try:
            json_start = search_result.find("[")
            if json_start != -1:
                contacts = json.loads(search_result[json_start:])
                contact_id = contacts[0]["id"]

                # Reset client for the association tool
                reset_client()

                result = hubspot_list_associations.invoke({
                    "from_object_type": "contacts",
                    "from_object_id": contact_id,
                    "to_object_type": "deals",
                })

                # Should either list associations or say none found
                assert "deals" in result.lower() or "associated" in result.lower()
        except (json.JSONDecodeError, KeyError, IndexError):
            pytest.skip("Could not parse contact ID from search result")
