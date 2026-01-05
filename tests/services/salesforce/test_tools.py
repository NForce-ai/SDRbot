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

        assert len(tools) == 9
        tool_names = [t.name for t in tools]
        # Query tools
        assert "salesforce_soql_query" in tool_names
        assert "salesforce_sosl_search" in tool_names
        assert "salesforce_count_records" in tool_names
        # Notes tools
        assert "salesforce_create_note_on_record" in tool_names
        assert "salesforce_list_notes_on_record" in tool_names
        # Tasks tools
        assert "salesforce_create_task_on_record" in tool_names
        assert "salesforce_list_tasks_on_record" in tool_names
        # Generic tools
        assert "salesforce_search_records" in tool_names
        assert "salesforce_get_record" in tool_names

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


class TestSalesforceAdminToolsUnit:
    """Unit tests for Salesforce admin tools (mocked API)."""

    def test_admin_list_objects_success(self, patch_salesforce_admin_client):
        """list_objects should return formatted object info."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_list_objects,
        )

        reset_admin_client()

        result = salesforce_admin_list_objects.invoke({})

        assert "Contact" in result
        assert "Account" in result
        assert "Custom_Object__c" in result
        patch_salesforce_admin_client.describe.assert_called_once()

    def test_admin_list_objects_error_handling(self, patch_salesforce_admin_client):
        """list_objects should handle errors gracefully."""
        patch_salesforce_admin_client.describe.side_effect = Exception("API Error")

        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_list_objects,
        )

        reset_admin_client()

        result = salesforce_admin_list_objects.invoke({})

        assert "Error" in result

    def test_admin_get_object_success(self, patch_salesforce_admin_client):
        """get_object should return detailed object info."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_get_object,
        )

        reset_admin_client()

        result = salesforce_admin_get_object.invoke({"object_name": "Contact"})

        assert "Contact" in result
        assert "FirstName" in result
        assert "Email" in result

    def test_admin_list_fields_success(self, patch_salesforce_admin_client):
        """list_fields should return formatted field info."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_list_fields,
        )

        reset_admin_client()

        result = salesforce_admin_list_fields.invoke({"object_name": "Contact"})

        assert "FirstName" in result
        assert "LastName" in result
        assert "Email" in result

    def test_admin_list_fields_with_picklist(self, patch_salesforce_admin_client):
        """list_fields should include picklist values."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_list_fields,
        )

        reset_admin_client()

        result = salesforce_admin_list_fields.invoke({"object_name": "Contact"})

        assert "LeadSource" in result
        assert "Web" in result

    def test_admin_get_field_success(self, patch_salesforce_admin_client):
        """get_field should return detailed field info."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_get_field,
        )

        reset_admin_client()

        result = salesforce_admin_get_field.invoke(
            {"object_name": "Contact", "field_name": "Email"}
        )

        assert "Email" in result
        assert "email" in result.lower()

    def test_admin_get_field_not_found(self, patch_salesforce_admin_client):
        """get_field should handle field not found."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_get_field,
        )

        reset_admin_client()

        result = salesforce_admin_get_field.invoke(
            {"object_name": "Contact", "field_name": "NonExistent__c"}
        )

        assert "not found" in result

    def test_admin_create_field_success(self, patch_salesforce_admin_client):
        """create_field should create a custom field."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_create_field,
        )

        reset_admin_client()

        result = salesforce_admin_create_field.invoke(
            {
                "object_name": "Contact",
                "field_name": "Test_Field",
                "field_label": "Test Field",
                "field_type": "Text",
                "length": 100,
            }
        )

        assert "Successfully created" in result or "Test_Field__c" in result

    def test_admin_update_field_requires_custom(self, patch_salesforce_admin_client):
        """update_field should reject non-custom fields."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_update_field,
        )

        reset_admin_client()

        result = salesforce_admin_update_field.invoke(
            {
                "object_name": "Contact",
                "field_name": "Email",  # Standard field
                "field_label": "New Label",
            }
        )

        assert "Error" in result
        assert "__c" in result

    def test_admin_delete_field_requires_custom(self, patch_salesforce_admin_client):
        """delete_field should reject non-custom fields."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_delete_field,
        )

        reset_admin_client()

        result = salesforce_admin_delete_field.invoke(
            {"object_name": "Contact", "field_name": "Email"}
        )

        assert "Error" in result
        assert "__c" in result

    def test_admin_list_users_success(self, patch_salesforce_admin_client):
        """list_users should return formatted user info."""
        from sdrbot_cli.services.salesforce.admin_tools import (
            reset_admin_client,
            salesforce_admin_list_users,
        )

        reset_admin_client()

        result = salesforce_admin_list_users.invoke({})

        assert "Test User" in result
        assert "user@example.com" in result
        assert "Sales Rep" in result


class TestSalesforceNotesToolsUnit:
    """Unit tests for Salesforce notes tools (mocked API)."""

    def test_create_note_success(self, patch_salesforce_admin_client):
        """create_note_on_record should create a note."""
        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_create_note_on_record,
        )

        reset_client()

        result = salesforce_create_note_on_record.invoke(
            {
                "parent_id": "001000000000001",
                "title": "Test Note",
                "body": "This is a test note.",
            }
        )

        assert "Successfully created" in result

    def test_list_notes_success(self, patch_salesforce_admin_client):
        """list_notes_on_record should return notes."""
        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_list_notes_on_record,
        )

        reset_client()

        result = salesforce_list_notes_on_record.invoke({"parent_id": "001000000000001"})

        assert "Test Note" in result
        assert "Note body" in result

    def test_list_notes_empty(self, patch_salesforce_admin_client):
        """list_notes_on_record should handle no notes."""
        # Override mock to return empty (clear side_effect to use return_value)
        patch_salesforce_admin_client.query.side_effect = None
        patch_salesforce_admin_client.query.return_value = {"records": []}

        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_list_notes_on_record,
        )

        reset_client()

        result = salesforce_list_notes_on_record.invoke({"parent_id": "001000000000001"})

        assert "No notes found" in result


class TestSalesforceTasksToolsUnit:
    """Unit tests for Salesforce tasks tools (mocked API)."""

    def test_create_task_success(self, patch_salesforce_admin_client):
        """create_task_on_record should create a task."""
        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_create_task_on_record,
        )

        reset_client()

        result = salesforce_create_task_on_record.invoke(
            {
                "record_id": "001000000000001",
                "subject": "Follow up call",
                "description": "Call to discuss proposal",
            }
        )

        assert "Successfully created" in result

    def test_create_task_with_all_params(self, patch_salesforce_admin_client):
        """create_task_on_record should accept all parameters."""
        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_create_task_on_record,
        )

        reset_client()

        result = salesforce_create_task_on_record.invoke(
            {
                "record_id": "001000000000001",
                "subject": "Follow up",
                "description": "Details",
                "due_date": "2024-12-31",
                "status": "In Progress",
                "priority": "High",
            }
        )

        assert "Successfully created" in result

    def test_list_tasks_success(self, patch_salesforce_admin_client):
        """list_tasks_on_record should return tasks."""
        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_list_tasks_on_record,
        )

        reset_client()

        result = salesforce_list_tasks_on_record.invoke({"record_id": "001000000000001"})

        assert "Follow up" in result
        assert "Not Started" in result

    def test_list_tasks_empty(self, patch_salesforce_admin_client):
        """list_tasks_on_record should handle no tasks."""
        # Override mock to return empty (clear side_effect to use return_value)
        patch_salesforce_admin_client.query.side_effect = None
        patch_salesforce_admin_client.query.return_value = {"records": []}

        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_list_tasks_on_record,
        )

        reset_client()

        result = salesforce_list_tasks_on_record.invoke({"record_id": "001000000000001"})

        assert "No tasks found" in result


class TestSalesforceGenericToolsUnit:
    """Unit tests for Salesforce generic tools (mocked API)."""

    def test_search_records_success(self, patch_salesforce_admin_client):
        """search_records should return matching records."""
        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_search_records,
        )

        reset_client()

        result = salesforce_search_records.invoke({"object_type": "Contact", "limit": 10})

        assert "Test Record" in result
        assert "Found" in result

    def test_search_records_with_query(self, patch_salesforce_admin_client):
        """search_records should filter by query."""
        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_search_records,
        )

        reset_client()

        result = salesforce_search_records.invoke(
            {"object_type": "Contact", "query": "Test", "limit": 5}
        )

        assert "Found" in result

    def test_search_records_empty(self, patch_salesforce_admin_client):
        """search_records should handle no results."""
        # Override mock to return empty (clear side_effect to use return_value)
        patch_salesforce_admin_client.query.side_effect = None
        patch_salesforce_admin_client.query.return_value = {"totalSize": 0, "records": []}

        from sdrbot_cli.services.salesforce.tools import (
            reset_client,
            salesforce_search_records,
        )

        reset_client()

        result = salesforce_search_records.invoke({"object_type": "Contact", "limit": 10})

        assert "No Contact records found" in result

    def test_get_record_success(self, patch_salesforce_admin_client):
        """get_record should return a single record."""
        from sdrbot_cli.services.salesforce.tools import reset_client, salesforce_get_record

        reset_client()

        result = salesforce_get_record.invoke(
            {"object_type": "Contact", "record_id": "003000000000001"}
        )

        assert "Test Contact" in result
        assert "test@example.com" in result

    def test_get_record_error(self, patch_salesforce_admin_client):
        """get_record should handle errors."""
        patch_salesforce_admin_client.restful.side_effect = Exception("Not found")

        from sdrbot_cli.services.salesforce.tools import reset_client, salesforce_get_record

        reset_client()

        result = salesforce_get_record.invoke({"object_type": "Contact", "record_id": "invalid"})

        assert "Error" in result


class TestSalesforceAdminToolsLoading:
    """Test that admin tools load correctly."""

    def test_admin_tools_load(self):
        """Admin tools should load."""
        from sdrbot_cli.services.salesforce.admin_tools import get_admin_tools

        tools = get_admin_tools()

        assert len(tools) == 8
        tool_names = [t.name for t in tools]
        # Object management
        assert "salesforce_admin_list_objects" in tool_names
        assert "salesforce_admin_get_object" in tool_names
        # Field management
        assert "salesforce_admin_list_fields" in tool_names
        assert "salesforce_admin_get_field" in tool_names
        assert "salesforce_admin_create_field" in tool_names
        assert "salesforce_admin_update_field" in tool_names
        assert "salesforce_admin_delete_field" in tool_names
        # Users
        assert "salesforce_admin_list_users" in tool_names

    def test_admin_tools_are_base_tool_instances(self):
        """Admin tools should be BaseTool instances."""
        from sdrbot_cli.services.salesforce.admin_tools import get_admin_tools

        tools = get_admin_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_admin_tools_have_descriptions(self):
        """Admin tools should have descriptions."""
        from sdrbot_cli.services.salesforce.admin_tools import get_admin_tools

        tools = get_admin_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"
            assert len(tool.description) > 10, f"{tool.name} description too short"
