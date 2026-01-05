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

        assert len(tools) == 7
        tool_names = [t.name for t in tools]
        assert "zohocrm_coql_query" in tool_names
        assert "zohocrm_convert_lead" in tool_names
        assert "zohocrm_add_note" in tool_names
        assert "zohocrm_list_notes" in tool_names
        assert "zohocrm_count_records" in tool_names
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


class TestZohoCRMAdminToolLoading:
    """Test that Zoho CRM admin tools load correctly."""

    def test_admin_tools_load(self):
        """Admin tools should load."""
        from sdrbot_cli.services.zohocrm.admin_tools import get_admin_tools

        tools = get_admin_tools()

        assert len(tools) == 11
        tool_names = [t.name for t in tools]
        # Modules
        assert "zohocrm_admin_list_modules" in tool_names
        assert "zohocrm_admin_get_module" in tool_names
        assert "zohocrm_admin_create_module" in tool_names
        assert "zohocrm_admin_update_module" in tool_names
        # Fields
        assert "zohocrm_admin_list_fields" in tool_names
        assert "zohocrm_admin_get_field" in tool_names
        assert "zohocrm_admin_create_field" in tool_names
        assert "zohocrm_admin_update_field" in tool_names
        assert "zohocrm_admin_delete_field" in tool_names
        # Users & Profiles
        assert "zohocrm_admin_list_users" in tool_names
        assert "zohocrm_admin_list_profiles" in tool_names

    def test_admin_tools_are_base_tool_instances(self):
        """All admin tools should be BaseTool instances."""
        from sdrbot_cli.services.zohocrm.admin_tools import get_admin_tools

        tools = get_admin_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_admin_tools_have_descriptions(self):
        """All admin tools should have descriptions."""
        from sdrbot_cli.services.zohocrm.admin_tools import get_admin_tools

        tools = get_admin_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_admin_tools_are_privileged(self):
        """Admin tools should be marked as privileged scope."""
        from sdrbot_cli.services.zohocrm.admin_tools import get_admin_tools
        from sdrbot_cli.tools import SCOPE_PRIVILEGED

        tools = get_admin_tools()

        for tool in tools:
            assert tool.metadata.get("scope") == SCOPE_PRIVILEGED, (
                f"{tool.name} is not marked privileged"
            )

    def test_schema_modifying_tools_are_marked(self):
        """Schema-modifying tools should be marked."""
        from sdrbot_cli.services.zohocrm.admin_tools import get_admin_tools

        tools = get_admin_tools()
        schema_modifying_tools = [
            "zohocrm_admin_create_module",
            "zohocrm_admin_update_module",
            "zohocrm_admin_create_field",
            "zohocrm_admin_update_field",
            "zohocrm_admin_delete_field",
        ]

        for tool in tools:
            if tool.name in schema_modifying_tools:
                assert tool.metadata.get("schema_modifying"), (
                    f"{tool.name} should be marked schema_modifying"
                )
            else:
                assert not tool.metadata.get("schema_modifying"), (
                    f"{tool.name} should not be marked schema_modifying"
                )


class TestZohoCRMAdminToolsUnit:
    """Unit tests for Zoho CRM admin tools with mocked API."""

    @pytest.fixture
    def mock_zoho_client(self):
        """Create a mock Zoho CRM client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_admin_client(self, mock_zoho_client):
        """Patch Zoho CRM admin client."""
        import sdrbot_cli.services.zohocrm.admin_tools as admin_module

        original_client = admin_module._admin_client
        admin_module._admin_client = None

        with patch(
            "sdrbot_cli.services.zohocrm.admin_tools.get_zoho_client",
            return_value=mock_zoho_client,
        ):
            yield mock_zoho_client

        admin_module._admin_client = original_client

    def test_list_modules_success(self, patch_admin_client):
        """list_modules should return formatted modules."""
        patch_admin_client.get.return_value = {
            "modules": [
                {
                    "api_name": "Leads",
                    "singular_label": "Lead",
                    "plural_label": "Leads",
                    "module_name": "Leads",
                    "id": "1",
                    "generated_type": "default",
                    "api_supported": True,
                    "creatable": True,
                    "editable": True,
                    "viewable": True,
                    "deletable": True,
                },
                {
                    "api_name": "Custom_Module",
                    "singular_label": "Custom Item",
                    "plural_label": "Custom Items",
                    "module_name": "Custom_Module",
                    "id": "2",
                    "generated_type": "custom",
                    "api_supported": True,
                    "creatable": True,
                    "editable": True,
                    "viewable": True,
                    "deletable": True,
                },
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_modules

        admin_module._admin_client = None

        result = zohocrm_admin_list_modules.invoke({})

        assert "2 API-accessible modules" in result
        assert "Leads" in result
        assert "Custom_Module" in result

    def test_list_modules_empty(self, patch_admin_client):
        """list_modules should handle no modules."""
        patch_admin_client.get.return_value = {"modules": []}

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_modules

        admin_module._admin_client = None

        result = zohocrm_admin_list_modules.invoke({})

        assert "No modules found" in result

    def test_get_module_success(self, patch_admin_client):
        """get_module should return module details."""
        patch_admin_client.get.side_effect = [
            {
                "modules": [
                    {
                        "api_name": "Leads",
                        "singular_label": "Lead",
                        "plural_label": "Leads",
                        "module_name": "Leads",
                        "id": "1",
                        "generated_type": "default",
                        "api_supported": True,
                        "creatable": True,
                        "editable": True,
                        "viewable": True,
                        "deletable": True,
                    }
                ]
            },
            {
                "fields": [
                    {"api_name": "Last_Name", "custom_field": False},
                    {"api_name": "Custom_Field", "custom_field": True},
                ]
            },
        ]

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_get_module

        admin_module._admin_client = None

        result = zohocrm_admin_get_module.invoke({"module_api_name": "Leads"})

        assert "Module 'Leads'" in result
        assert "field_count" in result
        assert "custom_field_count" in result

    def test_get_module_not_found(self, patch_admin_client):
        """get_module should handle module not found."""
        patch_admin_client.get.return_value = {"modules": []}

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_get_module

        admin_module._admin_client = None

        result = zohocrm_admin_get_module.invoke({"module_api_name": "NonExistent"})

        assert "not found" in result

    def test_list_fields_success(self, patch_admin_client):
        """list_fields should return formatted fields."""
        patch_admin_client.get.return_value = {
            "fields": [
                {
                    "api_name": "Last_Name",
                    "field_label": "Last Name",
                    "data_type": "text",
                    "id": "1",
                    "custom_field": False,
                    "system_mandatory": True,
                    "read_only": False,
                    "visible": True,
                    "length": 100,
                },
                {
                    "api_name": "Email",
                    "field_label": "Email",
                    "data_type": "email",
                    "id": "2",
                    "custom_field": False,
                    "system_mandatory": False,
                    "read_only": False,
                    "visible": True,
                    "length": 100,
                },
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_fields

        admin_module._admin_client = None

        result = zohocrm_admin_list_fields.invoke({"module_api_name": "Leads"})

        assert "2 fields" in result
        assert "Last_Name" in result
        assert "Email" in result

    def test_list_fields_with_picklist(self, patch_admin_client):
        """list_fields should include picklist values."""
        patch_admin_client.get.return_value = {
            "fields": [
                {
                    "api_name": "Lead_Status",
                    "field_label": "Lead Status",
                    "data_type": "picklist",
                    "id": "3",
                    "custom_field": False,
                    "system_mandatory": False,
                    "read_only": False,
                    "visible": True,
                    "pick_list_values": [
                        {"display_value": "New"},
                        {"display_value": "Contacted"},
                        {"display_value": "Qualified"},
                    ],
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_fields

        admin_module._admin_client = None

        result = zohocrm_admin_list_fields.invoke({"module_api_name": "Leads"})

        assert "Lead_Status" in result
        assert "New" in result
        assert "Contacted" in result

    def test_get_field_success(self, patch_admin_client):
        """get_field should return field details."""
        patch_admin_client.get.return_value = {
            "fields": [
                {
                    "api_name": "Email",
                    "field_label": "Email",
                    "data_type": "email",
                    "id": "field-123",
                    "custom_field": False,
                    "system_mandatory": False,
                    "read_only": False,
                    "visible": True,
                    "length": 100,
                    "tooltip": "Primary email address",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_get_field

        admin_module._admin_client = None

        result = zohocrm_admin_get_field.invoke(
            {"module_api_name": "Leads", "field_api_name": "Email"}
        )

        assert "Field 'Email'" in result
        assert "field-123" in result

    def test_get_field_not_found(self, patch_admin_client):
        """get_field should handle field not found."""
        patch_admin_client.get.return_value = {"fields": [{"api_name": "Other_Field", "id": "1"}]}

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_get_field

        admin_module._admin_client = None

        result = zohocrm_admin_get_field.invoke(
            {"module_api_name": "Leads", "field_api_name": "NonExistent"}
        )

        assert "not found" in result

    def test_create_field_success(self, patch_admin_client):
        """create_field should return success message."""
        patch_admin_client.post.return_value = {
            "fields": [
                {
                    "code": "SUCCESS",
                    "details": {"id": "field-new-123"},
                    "message": "field created",
                    "status": "success",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_create_field

        admin_module._admin_client = None

        result = zohocrm_admin_create_field.invoke(
            {
                "module_api_name": "Leads",
                "field_label": "Custom Score",
                "data_type": "integer",
                "length": 5,
            }
        )

        assert "Successfully created" in result
        assert "Custom Score" in result
        assert "field-new-123" in result

    def test_create_field_with_picklist(self, patch_admin_client):
        """create_field should handle picklist values."""
        patch_admin_client.post.return_value = {
            "fields": [
                {
                    "code": "SUCCESS",
                    "details": {"id": "field-pick-123"},
                    "message": "field created",
                    "status": "success",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_create_field

        admin_module._admin_client = None

        result = zohocrm_admin_create_field.invoke(
            {
                "module_api_name": "Leads",
                "field_label": "Rating",
                "data_type": "picklist",
                "pick_list_values": '["Hot", "Warm", "Cold"]',
            }
        )

        assert "Successfully created" in result
        assert "Rating" in result

    def test_create_field_invalid_picklist_json(self, patch_admin_client):
        """create_field should handle invalid picklist JSON."""
        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_create_field

        admin_module._admin_client = None

        result = zohocrm_admin_create_field.invoke(
            {
                "module_api_name": "Leads",
                "field_label": "Rating",
                "data_type": "picklist",
                "pick_list_values": "not valid json",
            }
        )

        assert "Error" in result
        assert "JSON array" in result

    def test_create_field_error(self, patch_admin_client):
        """create_field should handle API errors."""
        patch_admin_client.post.return_value = {
            "fields": [
                {
                    "code": "DUPLICATE_DATA",
                    "message": "A field with this label already exists",
                    "status": "error",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_create_field

        admin_module._admin_client = None

        result = zohocrm_admin_create_field.invoke(
            {
                "module_api_name": "Leads",
                "field_label": "Existing Field",
                "data_type": "text",
            }
        )

        assert "Failed" in result
        assert "DUPLICATE_DATA" in result

    def test_update_field_success(self, patch_admin_client):
        """update_field should return success message."""
        patch_admin_client.request.return_value = {
            "fields": [
                {
                    "code": "SUCCESS",
                    "message": "field updated",
                    "status": "success",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_update_field

        admin_module._admin_client = None

        result = zohocrm_admin_update_field.invoke(
            {
                "module_api_name": "Leads",
                "field_id": "field-123",
                "field_label": "Updated Label",
            }
        )

        assert "Successfully updated" in result
        assert "field-123" in result

    def test_update_field_no_changes(self, patch_admin_client):
        """update_field should require at least one change."""
        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_update_field

        admin_module._admin_client = None

        result = zohocrm_admin_update_field.invoke(
            {"module_api_name": "Leads", "field_id": "field-123"}
        )

        assert "Error" in result
        assert "At least one" in result

    def test_delete_field_success(self, patch_admin_client):
        """delete_field should return success message."""
        patch_admin_client.delete.return_value = {
            "fields": [
                {
                    "code": "SUCCESS",
                    "message": "field deleted",
                    "status": "success",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_delete_field

        admin_module._admin_client = None

        result = zohocrm_admin_delete_field.invoke(
            {"module_api_name": "Leads", "field_id": "field-custom-123"}
        )

        assert "Successfully deleted" in result
        assert "field-custom-123" in result

    def test_delete_field_dependency_error(self, patch_admin_client):
        """delete_field should handle dependency errors."""
        patch_admin_client.delete.return_value = {
            "fields": [
                {
                    "code": "DEPENDENCY_ERROR",
                    "message": "Field cannot be deleted due to workflow dependency",
                    "status": "error",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_delete_field

        admin_module._admin_client = None

        result = zohocrm_admin_delete_field.invoke(
            {"module_api_name": "Leads", "field_id": "field-123"}
        )

        assert "Error" in result
        assert "Cannot delete" in result or "dependency" in result.lower()

    def test_list_users_admin_success(self, patch_admin_client):
        """admin list_users should return detailed user info."""
        patch_admin_client.get.return_value = {
            "users": [
                {
                    "id": "user-1",
                    "full_name": "John Admin",
                    "email": "john@company.com",
                    "role": {"name": "Administrator"},
                    "profile": {"name": "Admin"},
                    "status": "active",
                    "confirm": True,
                    "created_time": "2024-01-01T00:00:00Z",
                    "time_zone": "America/New_York",
                },
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_users

        admin_module._admin_client = None

        result = zohocrm_admin_list_users.invoke({})

        assert "1 users" in result
        assert "John Admin" in result
        assert "Administrator" in result

    def test_create_module_success(self, patch_admin_client):
        """create_module should return success message."""
        patch_admin_client.post.return_value = {
            "modules": [
                {
                    "code": "SUCCESS",
                    "details": {"id": "module-new-123"},
                    "message": "module created successfully",
                    "status": "success",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_create_module

        admin_module._admin_client = None

        result = zohocrm_admin_create_module.invoke(
            {
                "singular_label": "Project",
                "plural_label": "Projects",
                "profile_ids": '["123456789"]',
            }
        )

        assert "Successfully created" in result
        assert "Project" in result
        assert "module-new-123" in result

    def test_create_module_invalid_profile_json(self, patch_admin_client):
        """create_module should handle invalid profile JSON."""
        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_create_module

        admin_module._admin_client = None

        result = zohocrm_admin_create_module.invoke(
            {
                "singular_label": "Project",
                "plural_label": "Projects",
                "profile_ids": "not valid json",
            }
        )

        assert "Error" in result
        assert "JSON array" in result

    def test_create_module_error(self, patch_admin_client):
        """create_module should handle API errors."""
        patch_admin_client.post.return_value = {
            "modules": [
                {
                    "code": "DUPLICATE_DATA",
                    "message": "A module with this name already exists",
                    "status": "error",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_create_module

        admin_module._admin_client = None

        result = zohocrm_admin_create_module.invoke(
            {
                "singular_label": "Lead",
                "plural_label": "Leads",
                "profile_ids": '["123456789"]',
            }
        )

        assert "Failed" in result
        assert "DUPLICATE_DATA" in result

    def test_update_module_success(self, patch_admin_client):
        """update_module should return success message."""
        patch_admin_client.put.return_value = {
            "modules": [
                {
                    "code": "SUCCESS",
                    "message": "module updated successfully",
                    "status": "success",
                }
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_update_module

        admin_module._admin_client = None

        result = zohocrm_admin_update_module.invoke(
            {
                "module_id_or_api_name": "Custom_Module",
                "singular_label": "Updated Name",
            }
        )

        assert "Successfully updated" in result
        assert "Custom_Module" in result

    def test_update_module_no_changes(self, patch_admin_client):
        """update_module should require at least one change."""
        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_update_module

        admin_module._admin_client = None

        result = zohocrm_admin_update_module.invoke({"module_id_or_api_name": "Custom_Module"})

        assert "Error" in result
        assert "At least one" in result

    def test_list_profiles_success(self, patch_admin_client):
        """list_profiles should return formatted profiles."""
        patch_admin_client.get.return_value = {
            "profiles": [
                {
                    "id": "profile-1",
                    "name": "Administrator",
                    "description": "Admin profile",
                    "default": True,
                    "created_time": "2024-01-01T00:00:00Z",
                },
                {
                    "id": "profile-2",
                    "name": "Standard",
                    "description": "Standard user profile",
                    "default": False,
                    "created_time": "2024-01-01T00:00:00Z",
                },
            ]
        }

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_profiles

        admin_module._admin_client = None

        result = zohocrm_admin_list_profiles.invoke({})

        assert "2 profiles" in result
        assert "Administrator" in result
        assert "Standard" in result
        assert "profile-1" in result

    def test_list_profiles_empty(self, patch_admin_client):
        """list_profiles should handle no profiles."""
        patch_admin_client.get.return_value = {"profiles": []}

        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_profiles

        admin_module._admin_client = None

        result = zohocrm_admin_list_profiles.invoke({})

        assert "No profiles found" in result


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


@pytest.mark.integration
class TestZohoCRMAdminToolsIntegration:
    """Integration tests for Zoho CRM admin tools.

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

    def test_list_modules_real(self, check_zoho_credentials):
        """Test listing modules against real API."""
        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_modules

        admin_module._admin_client = None

        result = zohocrm_admin_list_modules.invoke({})

        # Should return modules or handle gracefully
        assert "modules" in result.lower() or "error" in result.lower()

    def test_list_fields_real(self, check_zoho_credentials):
        """Test listing fields against real API."""
        import sdrbot_cli.services.zohocrm.admin_tools as admin_module
        from sdrbot_cli.services.zohocrm.admin_tools import zohocrm_admin_list_fields

        admin_module._admin_client = None

        result = zohocrm_admin_list_fields.invoke({"module_api_name": "Leads"})

        # Should return fields or handle gracefully
        assert "fields" in result.lower() or "error" in result.lower()
