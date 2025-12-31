"""Tests for Attio tools."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestAttioToolLoading:
    """Test that Attio tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.attio.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "attio_create_note" in tool_names
        assert "attio_list_notes" in tool_names
        assert "attio_get_record" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.attio.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.attio.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_get_tools_includes_static(self):
        """get_tools should include static tools."""
        from sdrbot_cli.services.attio import get_tools

        tools = get_tools()
        tool_names = [t.name for t in tools]

        # Static tools should always be present
        assert "attio_create_note" in tool_names
        assert "attio_list_notes" in tool_names
        assert "attio_get_record" in tool_names


class TestAttioToolsUnit:
    """Unit tests for Attio tools with mocked API."""

    @pytest.fixture
    def mock_attio_client(self):
        """Create a mock Attio client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_attio_client(self, mock_attio_client):
        """Patch Attio client."""
        import sdrbot_cli.services.attio.tools as tools_module

        original_client = tools_module._attio_client
        tools_module._attio_client = None

        with patch("sdrbot_cli.services.attio.tools.AttioClient", return_value=mock_attio_client):
            yield mock_attio_client

        tools_module._attio_client = original_client

    def test_create_note_success(self, patch_attio_client):
        """attio_create_note should return success message."""
        patch_attio_client.request.return_value = {
            "data": {
                "id": {"note_id": "note-123"},
                "title": "Test Note",
                "content": "Test content",
            }
        }

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_create_note

        tools_module._attio_client = None

        result = attio_create_note.invoke(
            {
                "object_slug": "people",
                "record_id": "rec-123",
                "title": "Test Note",
                "body": "Test content",
            }
        )

        assert "Successfully created note" in result
        assert "note-123" in result

        # Verify API was called correctly
        patch_attio_client.request.assert_called_once()
        call_args = patch_attio_client.request.call_args
        assert call_args[0] == ("POST", "/notes")

    def test_create_note_error(self, patch_attio_client):
        """attio_create_note should handle API errors."""
        patch_attio_client.request.side_effect = Exception("API Error: Invalid record")

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_create_note

        tools_module._attio_client = None

        result = attio_create_note.invoke(
            {"object_slug": "people", "record_id": "invalid-id", "title": "Test", "body": "Content"}
        )

        assert "Error" in result
        assert "Invalid record" in result

    def test_list_notes_success(self, patch_attio_client):
        """attio_list_notes should return formatted notes."""
        patch_attio_client.request.return_value = {
            "data": [
                {
                    "id": {"note_id": "note-1"},
                    "title": "Meeting Notes",
                    "created_at": "2024-01-15T10:30:00Z",
                },
                {
                    "id": {"note_id": "note-2"},
                    "title": "Follow-up",
                    "created_at": "2024-01-16T14:00:00Z",
                },
            ]
        }

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_list_notes

        tools_module._attio_client = None

        result = attio_list_notes.invoke({"object_slug": "people", "record_id": "rec-123"})

        assert "Notes:" in result
        assert "Meeting Notes" in result
        assert "Follow-up" in result
        assert "2024-01-15" in result

    def test_list_notes_empty(self, patch_attio_client):
        """attio_list_notes should handle no notes."""
        patch_attio_client.request.return_value = {"data": []}

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_list_notes

        tools_module._attio_client = None

        result = attio_list_notes.invoke({"object_slug": "companies", "record_id": "rec-456"})

        assert "No notes found" in result

    def test_list_notes_error(self, patch_attio_client):
        """attio_list_notes should handle API errors."""
        patch_attio_client.request.side_effect = Exception("Connection timeout")

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_list_notes

        tools_module._attio_client = None

        result = attio_list_notes.invoke({"object_slug": "people", "record_id": "rec-123"})

        assert "Error" in result
        assert "Connection timeout" in result

    def test_get_record_success(self, patch_attio_client):
        """attio_get_record should return formatted record."""
        patch_attio_client.request.return_value = {
            "data": {
                "id": {"record_id": "rec-123"},
                "values": {
                    "name": [{"full_name": "John Doe"}],
                    "email_addresses": [{"email_address": "john@example.com"}],
                    "company": [{"text": "Acme Inc"}],
                },
            }
        }

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_get_record

        tools_module._attio_client = None

        result = attio_get_record.invoke({"object_slug": "people", "record_id": "rec-123"})

        assert "Record ID: rec-123" in result
        assert "John Doe" in result
        assert "john@example.com" in result
        assert "Acme Inc" in result

    def test_get_record_not_found(self, patch_attio_client):
        """attio_get_record should handle missing record."""
        patch_attio_client.request.return_value = {"data": {}}

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_get_record

        tools_module._attio_client = None

        result = attio_get_record.invoke({"object_slug": "people", "record_id": "nonexistent-id"})

        assert "Record not found" in result

    def test_get_record_error(self, patch_attio_client):
        """attio_get_record should handle API errors."""
        patch_attio_client.request.side_effect = Exception("404 Not Found")

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_get_record

        tools_module._attio_client = None

        result = attio_get_record.invoke({"object_slug": "invalid", "record_id": "rec-123"})

        assert "Error" in result
        assert "404" in result

    def test_get_record_with_domain_value(self, patch_attio_client):
        """attio_get_record should extract domain values."""
        patch_attio_client.request.return_value = {
            "data": {
                "id": {"record_id": "rec-456"},
                "values": {
                    "name": [{"value": "Acme Corp"}],
                    "domains": [{"domain": "acme.com"}],
                },
            }
        }

        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_get_record

        tools_module._attio_client = None

        result = attio_get_record.invoke({"object_slug": "companies", "record_id": "rec-456"})

        assert "Acme Corp" in result
        assert "acme.com" in result


class TestAttioAdminToolLoading:
    """Test that Attio admin tools load correctly."""

    def test_admin_tools_load(self):
        """Admin tools should load."""
        from sdrbot_cli.services.attio.admin_tools import get_admin_tools

        tools = get_admin_tools()

        assert len(tools) == 9
        tool_names = [t.name for t in tools]
        # Objects
        assert "attio_admin_list_objects" in tool_names
        assert "attio_admin_get_object" in tool_names
        assert "attio_admin_create_object" in tool_names
        assert "attio_admin_update_object" in tool_names
        # Attributes
        assert "attio_admin_list_attributes" in tool_names
        assert "attio_admin_get_attribute" in tool_names
        assert "attio_admin_create_attribute" in tool_names
        assert "attio_admin_update_attribute" in tool_names
        # Members
        assert "attio_admin_list_members" in tool_names

    def test_admin_tools_are_base_tool_instances(self):
        """All admin tools should be BaseTool instances."""
        from sdrbot_cli.services.attio.admin_tools import get_admin_tools

        tools = get_admin_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_admin_tools_have_descriptions(self):
        """All admin tools should have descriptions."""
        from sdrbot_cli.services.attio.admin_tools import get_admin_tools

        tools = get_admin_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_get_tools_includes_admin(self):
        """get_tools should include admin tools."""
        from sdrbot_cli.services.attio import get_tools

        tools = get_tools()
        tool_names = [t.name for t in tools]

        # Admin tools should be present
        assert "attio_admin_list_objects" in tool_names
        assert "attio_admin_list_attributes" in tool_names
        assert "attio_admin_list_members" in tool_names

    def test_total_tools_count(self):
        """get_tools should return correct total count (static + admin)."""
        from sdrbot_cli.services.attio import get_tools

        tools = get_tools()

        # 3 static + 9 admin = 12 (without generated tools)
        assert len(tools) >= 12


class TestAttioAdminToolsUnit:
    """Unit tests for Attio admin tools with mocked API."""

    @pytest.fixture
    def mock_attio_client(self):
        """Create a mock Attio client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_admin_client(self, mock_attio_client):
        """Patch Attio admin client."""
        import sdrbot_cli.services.attio.admin_tools as admin_module

        original_client = admin_module._admin_client
        admin_module._admin_client = None

        with patch(
            "sdrbot_cli.services.attio.admin_tools.AttioClient", return_value=mock_attio_client
        ):
            yield mock_attio_client

        admin_module._admin_client = original_client

    # =============================================================================
    # OBJECTS
    # =============================================================================

    def test_list_objects_success(self, patch_admin_client):
        """attio_admin_list_objects should return formatted objects."""
        patch_admin_client.request.return_value = {
            "data": [
                {
                    "id": {"object_id": "obj-123"},
                    "api_slug": "people",
                    "singular_noun": "Person",
                    "plural_noun": "People",
                    "created_at": "2024-01-01T00:00:00Z",
                },
                {
                    "id": {"object_id": "obj-456"},
                    "api_slug": "companies",
                    "singular_noun": "Company",
                    "plural_noun": "Companies",
                    "created_at": "2024-01-01T00:00:00Z",
                },
            ]
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_objects

        admin_module._admin_client = None

        result = attio_admin_list_objects.invoke({})

        assert "Found 2 objects" in result
        assert "people" in result
        assert "companies" in result
        assert "Person" in result
        assert "Company" in result

    def test_list_objects_empty(self, patch_admin_client):
        """attio_admin_list_objects should handle no objects."""
        patch_admin_client.request.return_value = {"data": []}

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_objects

        admin_module._admin_client = None

        result = attio_admin_list_objects.invoke({})

        assert "No objects found" in result

    def test_get_object_success(self, patch_admin_client):
        """attio_admin_get_object should return object with attributes."""
        patch_admin_client.request.side_effect = [
            {
                "data": {
                    "id": {"object_id": "obj-123"},
                    "api_slug": "people",
                    "singular_noun": "Person",
                    "plural_noun": "People",
                    "created_at": "2024-01-01T00:00:00Z",
                }
            },
            {
                "data": [
                    {
                        "api_slug": "name",
                        "title": "Name",
                        "type": "text",
                        "is_required": False,
                        "is_writable": True,
                    },
                    {
                        "api_slug": "email_addresses",
                        "title": "Email",
                        "type": "email",
                        "is_required": False,
                        "is_writable": True,
                    },
                ]
            },
        ]

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_get_object

        admin_module._admin_client = None

        result = attio_admin_get_object.invoke({"object_slug": "people"})

        assert "people" in result
        assert "Person" in result
        assert "name" in result
        assert "email_addresses" in result

    def test_create_object_success(self, patch_admin_client):
        """attio_admin_create_object should return success message."""
        patch_admin_client.request.return_value = {
            "data": {
                "id": {"object_id": "obj-789"},
                "api_slug": "projects",
                "singular_noun": "Project",
                "plural_noun": "Projects",
            }
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_create_object

        admin_module._admin_client = None

        result = attio_admin_create_object.invoke(
            {
                "api_slug": "projects",
                "singular_noun": "Project",
                "plural_noun": "Projects",
            }
        )

        assert "Successfully created object" in result
        assert "Project" in result
        assert "obj-789" in result

        patch_admin_client.request.assert_called_once()
        call_args = patch_admin_client.request.call_args
        assert call_args[0] == ("POST", "/objects")

    def test_create_object_error(self, patch_admin_client):
        """attio_admin_create_object should handle errors."""
        patch_admin_client.request.side_effect = Exception("Conflict: slug already exists")

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_create_object

        admin_module._admin_client = None

        result = attio_admin_create_object.invoke(
            {
                "api_slug": "projects",
                "singular_noun": "Project",
                "plural_noun": "Projects",
            }
        )

        assert "Error creating object" in result
        assert "Conflict" in result

    def test_update_object_success(self, patch_admin_client):
        """attio_admin_update_object should return success message."""
        patch_admin_client.request.return_value = {
            "data": {
                "id": {"object_id": "obj-123"},
                "api_slug": "people",
                "singular_noun": "Contact",
                "plural_noun": "Contacts",
            }
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_update_object

        admin_module._admin_client = None

        result = attio_admin_update_object.invoke(
            {
                "object_slug": "people",
                "singular_noun": "Contact",
                "plural_noun": "Contacts",
            }
        )

        assert "Successfully updated object" in result
        assert "people" in result

    def test_update_object_no_fields(self, patch_admin_client):
        """attio_admin_update_object should require at least one field."""
        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_update_object

        admin_module._admin_client = None

        result = attio_admin_update_object.invoke({"object_slug": "people"})

        assert "Error" in result
        assert "At least one field" in result

    # =============================================================================
    # ATTRIBUTES
    # =============================================================================

    def test_list_attributes_success(self, patch_admin_client):
        """attio_admin_list_attributes should return formatted attributes."""
        patch_admin_client.request.return_value = {
            "data": [
                {
                    "id": {"attribute_id": "attr-1"},
                    "api_slug": "name",
                    "title": "Name",
                    "type": "text",
                    "is_required": True,
                    "is_writable": True,
                    "is_archived": False,
                },
                {
                    "id": {"attribute_id": "attr-2"},
                    "api_slug": "email_addresses",
                    "title": "Email",
                    "type": "email",
                    "is_required": False,
                    "is_writable": True,
                    "is_archived": False,
                },
            ]
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_attributes

        admin_module._admin_client = None

        result = attio_admin_list_attributes.invoke({"object_slug": "people"})

        assert "Found 2 attributes" in result
        assert "name" in result
        assert "email_addresses" in result
        assert "text" in result
        assert "email" in result

    def test_list_attributes_excludes_archived(self, patch_admin_client):
        """attio_admin_list_attributes should exclude archived by default."""
        patch_admin_client.request.return_value = {
            "data": [
                {
                    "id": {"attribute_id": "attr-1"},
                    "api_slug": "name",
                    "title": "Name",
                    "type": "text",
                    "is_archived": False,
                },
                {
                    "id": {"attribute_id": "attr-2"},
                    "api_slug": "old_field",
                    "title": "Old Field",
                    "type": "text",
                    "is_archived": True,
                },
            ]
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_attributes

        admin_module._admin_client = None

        result = attio_admin_list_attributes.invoke({"object_slug": "people"})

        assert "name" in result
        assert "old_field" not in result

    def test_list_attributes_with_select_options(self, patch_admin_client):
        """attio_admin_list_attributes should include select options."""
        patch_admin_client.request.return_value = {
            "data": [
                {
                    "id": {"attribute_id": "attr-1"},
                    "api_slug": "status",
                    "title": "Status",
                    "type": "select",
                    "is_archived": False,
                    "config": {
                        "select": {
                            "options": [
                                {"value": "active", "title": "Active"},
                                {"value": "inactive", "title": "Inactive"},
                            ]
                        }
                    },
                },
            ]
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_attributes

        admin_module._admin_client = None

        result = attio_admin_list_attributes.invoke({"object_slug": "people"})

        assert "status" in result
        assert "select" in result
        assert "Active" in result

    def test_get_attribute_success(self, patch_admin_client):
        """attio_admin_get_attribute should return attribute details."""
        patch_admin_client.request.return_value = {
            "data": {
                "id": {"attribute_id": "attr-123"},
                "api_slug": "job_title",
                "title": "Job Title",
                "description": "Person's role",
                "type": "text",
                "is_required": False,
                "is_unique": False,
                "is_writable": True,
                "created_at": "2024-01-01T00:00:00Z",
            }
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_get_attribute

        admin_module._admin_client = None

        result = attio_admin_get_attribute.invoke(
            {
                "object_slug": "people",
                "attribute_slug": "job_title",
            }
        )

        assert "job_title" in result
        assert "Job Title" in result
        assert "Person's role" in result
        assert "text" in result

    def test_create_attribute_success(self, patch_admin_client):
        """attio_admin_create_attribute should return success message."""
        patch_admin_client.request.return_value = {
            "data": {
                "id": {"attribute_id": "attr-new"},
                "api_slug": "lead_score",
                "title": "Lead Score",
                "type": "number",
            }
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_create_attribute

        admin_module._admin_client = None

        result = attio_admin_create_attribute.invoke(
            {
                "object_slug": "people",
                "api_slug": "lead_score",
                "title": "Lead Score",
                "attribute_type": "number",
            }
        )

        assert "Successfully created attribute" in result
        assert "Lead Score" in result
        assert "attr-new" in result

        patch_admin_client.request.assert_called_once()
        call_args = patch_admin_client.request.call_args
        assert call_args[0] == ("POST", "/objects/people/attributes")

    def test_create_attribute_with_type_config(self, patch_admin_client):
        """attio_admin_create_attribute should handle type_config parameter."""
        # Track what payload was sent
        captured_payload = {}

        def capture_request(method, endpoint, json=None):
            captured_payload.update(json or {})
            return {
                "data": {
                    "id": {"attribute_id": "attr-select"},
                    "api_slug": "priority",
                    "title": "Priority",
                    "type": "select",
                }
            }

        patch_admin_client.request.side_effect = capture_request

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_create_attribute

        admin_module._admin_client = None

        type_config = '{"select": {"options": [{"value": "high", "title": "High"}]}}'
        result = attio_admin_create_attribute.invoke(
            {
                "object_slug": "people",
                "api_slug": "priority",
                "title": "Priority",
                "attribute_type": "select",
                "type_config": type_config,
            }
        )

        assert "Successfully created attribute" in result
        # Verify config was included in payload
        assert "data" in captured_payload
        assert "config" in captured_payload["data"]
        assert captured_payload["data"]["config"]["select"]["options"][0]["value"] == "high"

    def test_create_attribute_with_relationship(self, patch_admin_client):
        """attio_admin_create_attribute should handle record-reference type."""
        patch_admin_client.request.return_value = {
            "data": {
                "id": {"attribute_id": "attr-ref"},
                "api_slug": "company",
                "title": "Company",
                "type": "record-reference",
            }
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_create_attribute

        admin_module._admin_client = None

        result = attio_admin_create_attribute.invoke(
            {
                "object_slug": "people",
                "api_slug": "company",
                "title": "Company",
                "attribute_type": "record-reference",
                "relationship_object": "companies",
            }
        )

        assert "Successfully created attribute" in result
        call_args = patch_admin_client.request.call_args
        payload = call_args[1]["json"]["data"]
        assert payload["config"]["record_reference"]["allowed_objects"] == ["companies"]

    def test_create_attribute_invalid_type_config(self, patch_admin_client):
        """attio_admin_create_attribute should reject invalid type_config JSON."""
        # Track if request was called (should NOT be called for invalid JSON)
        request_called = []

        def capture_request(method, endpoint, json=None):
            request_called.append(True)
            return {"data": {"id": {"attribute_id": "attr-x"}}}

        patch_admin_client.request.side_effect = capture_request

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_create_attribute

        admin_module._admin_client = None

        result = attio_admin_create_attribute.invoke(
            {
                "object_slug": "people",
                "api_slug": "test",
                "title": "Test",
                "attribute_type": "select",
                "type_config": "invalid json",
            }
        )

        assert "Error" in result
        assert "valid JSON" in result
        # Request should NOT be called when JSON parsing fails
        assert len(request_called) == 0, "Request should not be called for invalid JSON type_config"

    def test_update_attribute_success(self, patch_admin_client):
        """attio_admin_update_attribute should return success message."""
        patch_admin_client.request.return_value = {
            "data": {
                "id": {"attribute_id": "attr-123"},
                "api_slug": "job_title",
                "title": "Role",
            }
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_update_attribute

        admin_module._admin_client = None

        result = attio_admin_update_attribute.invoke(
            {
                "object_slug": "people",
                "attribute_slug": "job_title",
                "title": "Role",
                "description": "Updated description",
            }
        )

        assert "Successfully updated attribute" in result
        assert "job_title" in result

    def test_update_attribute_no_fields(self, patch_admin_client):
        """attio_admin_update_attribute should require at least one field."""
        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_update_attribute

        admin_module._admin_client = None

        result = attio_admin_update_attribute.invoke(
            {
                "object_slug": "people",
                "attribute_slug": "name",
            }
        )

        assert "Error" in result
        assert "At least one field" in result

    def test_update_attribute_archive(self, patch_admin_client):
        """attio_admin_update_attribute should support archiving."""
        patch_admin_client.request.return_value = {"data": {}}

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_update_attribute

        admin_module._admin_client = None

        result = attio_admin_update_attribute.invoke(
            {
                "object_slug": "people",
                "attribute_slug": "old_field",
                "is_archived": True,
            }
        )

        assert "Successfully updated" in result
        call_args = patch_admin_client.request.call_args
        payload = call_args[1]["json"]["data"]
        assert payload["is_archived"] is True

    # =============================================================================
    # WORKSPACE MEMBERS
    # =============================================================================

    def test_list_members_success(self, patch_admin_client):
        """attio_admin_list_members should return formatted members."""
        patch_admin_client.request.return_value = {
            "data": [
                {
                    "id": {"workspace_member_id": "mem-1"},
                    "email_address": "alice@example.com",
                    "first_name": "Alice",
                    "last_name": "Smith",
                    "access_level": "admin",
                    "avatar_url": "https://example.com/alice.jpg",
                    "created_at": "2024-01-01T00:00:00Z",
                },
                {
                    "id": {"workspace_member_id": "mem-2"},
                    "email_address": "bob@example.com",
                    "first_name": "Bob",
                    "last_name": "Jones",
                    "access_level": "member",
                    "avatar_url": None,
                    "created_at": "2024-01-02T00:00:00Z",
                },
            ]
        }

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_members

        admin_module._admin_client = None

        result = attio_admin_list_members.invoke({})

        assert "Found 2 workspace members" in result
        assert "alice@example.com" in result
        assert "bob@example.com" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "admin" in result
        assert "member" in result

    def test_list_members_empty(self, patch_admin_client):
        """attio_admin_list_members should handle no members."""
        patch_admin_client.request.return_value = {"data": []}

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_members

        admin_module._admin_client = None

        result = attio_admin_list_members.invoke({})

        assert "No workspace members found" in result

    def test_list_members_error(self, patch_admin_client):
        """attio_admin_list_members should handle API errors."""
        patch_admin_client.request.side_effect = Exception("Unauthorized: invalid token")

        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_members

        admin_module._admin_client = None

        result = attio_admin_list_members.invoke({})

        assert "Error" in result
        assert "Unauthorized" in result


@pytest.mark.integration
class TestAttioToolsIntegration:
    """Integration tests for Attio tools.

    Run with: pytest -m integration
    Requires Attio API key.
    """

    @pytest.fixture
    def check_attio_credentials(self):
        """Skip if Attio credentials not available."""
        if not os.getenv("ATTIO_API_KEY"):
            pytest.skip("ATTIO_API_KEY not set - skipping integration test")

    def test_list_notes_real(self, check_attio_credentials):
        """Test listing notes against real API."""
        import sdrbot_cli.services.attio.tools as tools_module
        from sdrbot_cli.services.attio.tools import attio_list_notes

        tools_module._attio_client = None

        # Use a placeholder record - should return "No notes" or actual notes
        result = attio_list_notes.invoke(
            {"object_slug": "people", "record_id": "test-record-id", "limit": 5}
        )

        # Should either return notes or handle gracefully
        assert "notes" in result.lower() or "error" in result.lower()


@pytest.mark.integration
class TestAttioAdminToolsIntegration:
    """Integration tests for Attio admin tools.

    Run with: pytest -m integration
    Requires Attio API key with object_configuration:read scope.
    """

    @pytest.fixture
    def check_attio_credentials(self):
        """Skip if Attio credentials not available."""
        if not os.getenv("ATTIO_API_KEY"):
            pytest.skip("ATTIO_API_KEY not set - skipping integration test")

    def test_list_objects_real(self, check_attio_credentials):
        """Test listing objects against real API."""
        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_objects

        admin_module._admin_client = None

        result = attio_admin_list_objects.invoke({})

        # Should return objects (people, companies are standard)
        assert "Found" in result or "objects" in result.lower()
        # Standard objects should exist
        assert (
            "people" in result.lower() or "companies" in result.lower() or "error" in result.lower()
        )

    def test_list_members_real(self, check_attio_credentials):
        """Test listing workspace members against real API."""
        import sdrbot_cli.services.attio.admin_tools as admin_module
        from sdrbot_cli.services.attio.admin_tools import attio_admin_list_members

        admin_module._admin_client = None

        result = attio_admin_list_members.invoke({})

        # Should return members or an error
        assert "members" in result.lower() or "error" in result.lower()
