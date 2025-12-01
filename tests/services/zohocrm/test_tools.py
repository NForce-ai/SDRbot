"""Tests for Zoho CRM tools."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestZohoCRMToolLoading:
    """Test that Zoho CRM tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.zohocrm.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 6
        tool_names = [t.name for t in tools]
        assert "zohocrm_coql_query" in tool_names
        assert "zohocrm_convert_lead" in tool_names
        assert "zohocrm_add_note" in tool_names
        assert "zohocrm_list_notes" in tool_names
        assert "zohocrm_get_related_records" in tool_names
        assert "zohocrm_list_users" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.zohocrm.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.zohocrm.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_get_tools_includes_static(self):
        """get_tools should include static tools."""
        from sdrbot_cli.services.zohocrm import get_tools

        tools = get_tools()
        tool_names = [t.name for t in tools]

        # Static tools should always be present
        assert "zohocrm_coql_query" in tool_names
        assert "zohocrm_convert_lead" in tool_names
        assert "zohocrm_add_note" in tool_names


class TestZohoCRMToolsUnit:
    """Unit tests for Zoho CRM tools with mocked API."""

    @pytest.fixture
    def mock_zoho_client(self):
        """Create a mock Zoho CRM client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_zoho_client(self, mock_zoho_client):
        """Patch Zoho CRM client."""
        import sdrbot_cli.services.zohocrm.tools as tools_module

        original_client = tools_module._zoho_client
        tools_module._zoho_client = None

        with patch(
            "sdrbot_cli.services.zohocrm.tools.get_zoho_client", return_value=mock_zoho_client
        ):
            yield mock_zoho_client

        tools_module._zoho_client = original_client

    def test_coql_query_success(self, patch_zoho_client):
        """coql_query should return formatted results."""
        patch_zoho_client.post.return_value = {
            "data": [
                {
                    "id": "123",
                    "Last_Name": "Doe",
                    "First_Name": "John",
                    "Email": "john@example.com",
                },
                {
                    "id": "456",
                    "Last_Name": "Smith",
                    "First_Name": "Jane",
                    "Email": "jane@example.com",
                },
            ]
        }

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_coql_query

        tools_module._zoho_client = None

        result = zohocrm_coql_query.invoke(
            {"query": "SELECT Last_Name, First_Name, Email FROM Contacts LIMIT 2"}
        )

        assert "2 records" in result
        assert "John" in result
        assert "jane@example.com" in result

    def test_coql_query_no_results(self, patch_zoho_client):
        """coql_query should handle empty results."""
        patch_zoho_client.post.return_value = {"data": []}

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_coql_query

        tools_module._zoho_client = None

        result = zohocrm_coql_query.invoke(
            {"query": "SELECT Last_Name FROM Contacts WHERE Email = 'nonexistent@test.com'"}
        )

        assert "No records found" in result

    def test_coql_query_error(self, patch_zoho_client):
        """coql_query should handle API errors."""
        patch_zoho_client.post.side_effect = Exception("INVALID_QUERY: Syntax error")

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_coql_query

        tools_module._zoho_client = None

        result = zohocrm_coql_query.invoke({"query": "SELECT InvalidField FROM Contacts"})

        assert "Error" in result
        assert "INVALID_QUERY" in result

    def test_convert_lead_success(self, patch_zoho_client):
        """convert_lead should return success with record IDs."""
        patch_zoho_client.post.return_value = {
            "data": [
                {
                    "Contacts": "contact-123",
                    "Accounts": "account-456",
                    "Deals": None,
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_convert_lead

        tools_module._zoho_client = None

        result = zohocrm_convert_lead.invoke(
            {"lead_id": "lead-789", "create_account": True, "create_contact": True}
        )

        assert "Successfully converted" in result
        assert "contact-123" in result
        assert "account-456" in result

    def test_convert_lead_error(self, patch_zoho_client):
        """convert_lead should handle API errors."""
        patch_zoho_client.post.side_effect = Exception("Lead not found")

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_convert_lead

        tools_module._zoho_client = None

        result = zohocrm_convert_lead.invoke({"lead_id": "invalid-lead"})

        assert "Error" in result
        assert "Lead not found" in result

    def test_add_note_success(self, patch_zoho_client):
        """add_note should return success message."""
        patch_zoho_client.post.return_value = {
            "data": [{"details": {"id": "note-123"}, "status": "success"}]
        }

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_add_note

        tools_module._zoho_client = None

        result = zohocrm_add_note.invoke(
            {
                "module": "Leads",
                "record_id": "lead-456",
                "note_title": "Follow-up",
                "note_content": "Call back next week",
            }
        )

        assert "Successfully added note" in result
        assert "note-123" in result

    def test_add_note_error(self, patch_zoho_client):
        """add_note should handle API errors."""
        patch_zoho_client.post.side_effect = Exception("Invalid record ID")

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_add_note

        tools_module._zoho_client = None

        result = zohocrm_add_note.invoke(
            {
                "module": "Leads",
                "record_id": "invalid",
                "note_title": "Test",
                "note_content": "Test content",
            }
        )

        assert "Error" in result
        assert "Invalid record ID" in result

    def test_list_notes_success(self, patch_zoho_client):
        """list_notes should return formatted notes."""
        patch_zoho_client.get.return_value = {
            "data": [
                {
                    "id": "note-1",
                    "Note_Title": "Meeting Notes",
                    "Note_Content": "Discussed project timeline",
                    "Created_Time": "2024-01-15T10:30:00Z",
                },
                {
                    "id": "note-2",
                    "Note_Title": "Follow-up",
                    "Note_Content": "Send proposal",
                    "Created_Time": "2024-01-16T14:00:00Z",
                },
            ]
        }

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_list_notes

        tools_module._zoho_client = None

        result = zohocrm_list_notes.invoke({"module": "Leads", "record_id": "lead-123"})

        assert "2 notes" in result
        assert "Meeting Notes" in result
        assert "Follow-up" in result

    def test_list_notes_empty(self, patch_zoho_client):
        """list_notes should handle no notes."""
        patch_zoho_client.get.return_value = {"data": []}

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_list_notes

        tools_module._zoho_client = None

        result = zohocrm_list_notes.invoke({"module": "Contacts", "record_id": "contact-456"})

        assert "No notes found" in result

    def test_list_notes_error(self, patch_zoho_client):
        """list_notes should handle API errors."""
        patch_zoho_client.get.side_effect = Exception("Connection timeout")

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_list_notes

        tools_module._zoho_client = None

        result = zohocrm_list_notes.invoke({"module": "Leads", "record_id": "lead-123"})

        assert "Error" in result
        assert "Connection timeout" in result

    def test_get_related_records_success(self, patch_zoho_client):
        """get_related_records should return formatted records."""
        patch_zoho_client.get.return_value = {
            "data": [
                {"id": "contact-1", "Last_Name": "Doe", "Email": "john@example.com"},
                {"id": "contact-2", "Last_Name": "Smith", "Email": "jane@example.com"},
            ]
        }

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_get_related_records

        tools_module._zoho_client = None

        result = zohocrm_get_related_records.invoke(
            {"module": "Accounts", "record_id": "account-123", "related_module": "Contacts"}
        )

        assert "2 related Contacts" in result
        assert "Doe" in result
        assert "jane@example.com" in result

    def test_get_related_records_empty(self, patch_zoho_client):
        """get_related_records should handle no related records."""
        patch_zoho_client.get.return_value = {"data": []}

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_get_related_records

        tools_module._zoho_client = None

        result = zohocrm_get_related_records.invoke(
            {"module": "Accounts", "record_id": "account-456", "related_module": "Deals"}
        )

        assert "No Deals found" in result

    def test_get_related_records_error(self, patch_zoho_client):
        """get_related_records should handle API errors."""
        patch_zoho_client.get.side_effect = Exception("Invalid module")

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_get_related_records

        tools_module._zoho_client = None

        result = zohocrm_get_related_records.invoke(
            {"module": "InvalidModule", "record_id": "rec-123", "related_module": "Contacts"}
        )

        assert "Error" in result
        assert "Invalid module" in result

    def test_list_users_success(self, patch_zoho_client):
        """list_users should return formatted user list."""
        patch_zoho_client.get.return_value = {
            "users": [
                {
                    "id": "user-1",
                    "full_name": "John Admin",
                    "email": "john@company.com",
                    "role": {"name": "Administrator"},
                    "profile": {"name": "Admin"},
                    "status": "active",
                },
                {
                    "id": "user-2",
                    "full_name": "Jane Sales",
                    "email": "jane@company.com",
                    "role": {"name": "Sales Rep"},
                    "profile": {"name": "Standard"},
                    "status": "active",
                },
            ]
        }

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_list_users

        tools_module._zoho_client = None

        result = zohocrm_list_users.invoke({})

        assert "2 users" in result
        assert "John Admin" in result
        assert "jane@company.com" in result
        assert "Administrator" in result

    def test_list_users_empty(self, patch_zoho_client):
        """list_users should handle no users."""
        patch_zoho_client.get.return_value = {"users": []}

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_list_users

        tools_module._zoho_client = None

        result = zohocrm_list_users.invoke({})

        assert "No users found" in result

    def test_list_users_error(self, patch_zoho_client):
        """list_users should handle API errors."""
        patch_zoho_client.get.side_effect = Exception("Unauthorized")

        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_list_users

        tools_module._zoho_client = None

        result = zohocrm_list_users.invoke({})

        assert "Error" in result
        assert "Unauthorized" in result


@pytest.mark.integration
class TestZohoCRMToolsIntegration:
    """Integration tests for Zoho CRM tools.

    Run with: pytest -m integration
    Requires Zoho CRM OAuth credentials.
    """

    @pytest.fixture
    def check_zoho_credentials(self):
        """Skip if Zoho CRM credentials not available."""
        if not (
            os.getenv("ZOHO_CLIENT_ID")
            and os.getenv("ZOHO_CLIENT_SECRET")
            and os.getenv("ZOHO_REGION")
        ):
            pytest.skip("Zoho CRM credentials not set - skipping integration test")

    def test_coql_query_real(self, check_zoho_credentials):
        """Test COQL query against real API."""
        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_coql_query

        tools_module._zoho_client = None

        result = zohocrm_coql_query.invoke(
            {"query": "SELECT Last_Name, Email FROM Contacts LIMIT 1"}
        )

        # Should either return results or handle gracefully
        assert "records" in result.lower() or "error" in result.lower()

    def test_list_users_real(self, check_zoho_credentials):
        """Test listing users against real API."""
        import sdrbot_cli.services.zohocrm.tools as tools_module
        from sdrbot_cli.services.zohocrm.tools import zohocrm_list_users

        tools_module._zoho_client = None

        result = zohocrm_list_users.invoke({"limit": 5})

        # Should either return users or handle gracefully
        assert "users" in result.lower() or "error" in result.lower()
