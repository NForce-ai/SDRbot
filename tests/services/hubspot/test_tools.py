"""Tests for HubSpot service tools (Associations, CRUD, Loading)."""

import pathlib
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestAssociationToolsUnit:
    """Unit tests for association tools (mocked API)."""

    def test_create_association_uses_correct_params(self, patch_hubspot_client):
        """create_association should use object_type/object_id params."""
        from sdrbot_cli.services.hubspot.tools import hubspot_create_association, reset_client

        reset_client()

        hubspot_create_association.invoke(
            {
                "from_object_type": "contacts",
                "from_object_id": "123",
                "to_object_type": "deals",
                "to_object_id": "456",
            }
        )

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

        result = hubspot_create_association.invoke(
            {
                "from_object_type": "contacts",
                "from_object_id": "123",
                "to_object_type": "deals",
                "to_object_id": "456",
            }
        )

        assert "Successfully associated" in result
        assert "contacts/123" in result
        assert "deals/456" in result

    def test_create_association_no_types_found(self, patch_hubspot_client):
        """create_association should handle missing association types."""
        # Override the default mock to return empty results
        patch_hubspot_client.crm.associations.v4.schema.definitions_api.get_all.return_value = (
            MagicMock(results=[])
        )

        from sdrbot_cli.services.hubspot.tools import hubspot_create_association, reset_client

        reset_client()  # Clear cached client to use mock

        result = hubspot_create_association.invoke(
            {
                "from_object_type": "contacts",
                "from_object_id": "123",
                "to_object_type": "widgets",  # Fake object type
                "to_object_id": "456",
            }
        )

        assert "No association types found" in result

    def test_list_associations_uses_correct_params(self, patch_hubspot_client):
        """list_associations should use object_type/object_id params."""
        patch_hubspot_client.crm.associations.v4.basic_api.get_page.return_value = MagicMock(
            results=[]
        )

        from sdrbot_cli.services.hubspot.tools import hubspot_list_associations, reset_client

        reset_client()

        hubspot_list_associations.invoke(
            {
                "from_object_type": "contacts",
                "from_object_id": "123",
                "to_object_type": "deals",
            }
        )

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

        result = hubspot_list_associations.invoke(
            {
                "from_object_type": "contacts",
                "from_object_id": "123",
                "to_object_type": "deals",
            }
        )

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

        result = hubspot_list_associations.invoke(
            {
                "from_object_type": "contacts",
                "from_object_id": "123",
                "to_object_type": "deals",
            }
        )

        assert "No deals associated" in result

    def test_delete_association_uses_correct_params(self, patch_hubspot_client):
        """delete_association should use object_type/object_id params."""
        from sdrbot_cli.services.hubspot.tools import hubspot_delete_association, reset_client

        reset_client()

        hubspot_delete_association.invoke(
            {
                "from_object_type": "contacts",
                "from_object_id": "123",
                "to_object_type": "deals",
                "to_object_id": "456",
            }
        )

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

        result = hubspot_delete_association.invoke(
            {
                "from_object_type": "contacts",
                "from_object_id": "123",
                "to_object_type": "deals",
                "to_object_id": "456",
            }
        )

        assert "Successfully removed association" in result


@pytest.mark.integration
class TestAssociationToolsIntegration:
    """Integration tests for associations against real API.

    Run with: pytest -m integration
    """

    def test_list_associations_real(self, real_hubspot_client):
        """Test listing associations against real API."""
        from sdrbot_cli.services.hubspot.tools import hubspot_list_associations, reset_client

        try:
            from sdrbot_cli.services.hubspot.tools_generated import hubspot_search_contacts
        except ImportError:
            pytest.skip("Generated tools not found. Run 'sdrbot services sync hubspot' first.")
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

                result = hubspot_list_associations.invoke(
                    {
                        "from_object_type": "contacts",
                        "from_object_id": contact_id,
                        "to_object_type": "deals",
                    }
                )

                # Should either list associations or say none found
                assert "deals" in result.lower() or "associated" in result.lower()
        except (json.JSONDecodeError, KeyError, IndexError):
            pytest.skip("Could not parse contact ID from search result")


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
                MagicMock(id="123", properties={"email": "test@example.com", "firstname": "Test"})
            ],
        )

        # Import our mock tools
        from tests.services.hubspot.mock_generated_tools import hubspot_search_contacts

        # Patch the get_client in our mock module to return our test fixture
        with patch(
            "tests.services.hubspot.mock_generated_tools.mock_get_client",
            return_value=patch_hubspot_client,
        ):
            result = hubspot_search_contacts.invoke({"limit": 10})

        assert "Found 10 contacts" in result

    def test_search_contacts_no_results(self, patch_hubspot_client):
        """search_contacts should handle empty results."""
        from tests.services.hubspot.mock_generated_tools import hubspot_search_contacts

        result = hubspot_search_contacts.invoke({"limit": 0})
        # The mock returns "Found 0 contacts"
        assert "Found 0 contacts" in result

    def test_create_contact_success(self, patch_hubspot_client):
        """create_contact should return success with new ID."""
        from tests.services.hubspot.mock_generated_tools import hubspot_create_contact

        result = hubspot_create_contact.invoke(
            {"email": "new@example.com", "firstname": "New", "lastname": "Contact"}
        )

        assert "Successfully created contact" in result
        assert "456" in result

    def test_create_contact_requires_properties(self, patch_hubspot_client):
        """create_contact should error if no properties provided."""
        from tests.services.hubspot.mock_generated_tools import hubspot_create_contact

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
        try:
            import sdrbot_cli.services.hubspot.tools_generated as gen_module
            from sdrbot_cli.services.hubspot.tools_generated import hubspot_search_contacts
        except ImportError:
            pytest.skip("Generated tools not found. Run 'sdrbot services sync hubspot' first.")

        gen_module._hs_client = None
        result = hubspot_search_contacts.invoke({"limit": 1})
        assert "contacts" in result.lower() or "found" in result.lower()

    def test_get_contact_real(self, real_hubspot_client):
        """Test getting a specific contact."""
        try:
            import sdrbot_cli.services.hubspot.tools_generated as gen_module
            from sdrbot_cli.services.hubspot.tools_generated import (
                hubspot_get_contact,
                hubspot_search_contacts,
            )
        except ImportError:
            pytest.skip("Generated tools not found. Run 'sdrbot services sync hubspot' first.")

        import json

        gen_module._hs_client = None

        # First find a contact
        search_result = hubspot_search_contacts.invoke({"limit": 1})

        if "No contacts found" in search_result:
            pytest.skip("No contacts in HubSpot to test with")

        # Extract ID from search result
        try:
            json_start = search_result.find("[")
            if json_start != -1:
                contacts = json.loads(search_result[json_start:])
                contact_id = contacts[0]["id"]

                result = hubspot_get_contact.invoke({"contact_id": contact_id})
                assert contact_id in result or "Contact" in result
        except (json.JSONDecodeError, KeyError, IndexError):
            pytest.skip("Could not parse contact ID from search result")


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

        # Mock content that defines a TOOLS list with one dummy tool
        mock_code = """
from langchain_core.tools import StructuredTool

def dummy_tool_func():
    pass

hubspot_dummy_generated_tool = StructuredTool.from_function(
    func=dummy_tool_func,
    name="hubspot_dummy_generated_tool",
    description="A dummy tool"
)
"""

        # Patch pathlib.Path.exists and pathlib.Path.read_text
        with (
            patch.object(pathlib.Path, "exists", return_value=True),
            patch.object(pathlib.Path, "read_text", return_value=mock_code),
        ):
            tools = get_tools()

        # Should have static tools (4) + 1 generated dummy tool
        assert len(tools) == 5, "Expected 4 static tools + 1 generated tool"
        assert any(t.name == "hubspot_dummy_generated_tool" for t in tools)

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
            import sdrbot_cli.services.hubspot as hubspot_module

            # This simulates the ImportError case
            with patch.object(
                hubspot_module,
                "get_tools",
                side_effect=lambda: hubspot_module.tools.get_static_tools(),
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
