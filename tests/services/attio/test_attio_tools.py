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

        from sdrbot_cli.services.attio.tools import attio_create_note

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_create_note.invoke({
            "object_slug": "people",
            "record_id": "rec-123",
            "title": "Test Note",
            "body": "Test content"
        })

        assert "Successfully created note" in result
        assert "note-123" in result

        # Verify API was called correctly
        patch_attio_client.request.assert_called_once()
        call_args = patch_attio_client.request.call_args
        assert call_args[0] == ("POST", "/notes")

    def test_create_note_error(self, patch_attio_client):
        """attio_create_note should handle API errors."""
        patch_attio_client.request.side_effect = Exception("API Error: Invalid record")

        from sdrbot_cli.services.attio.tools import attio_create_note

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_create_note.invoke({
            "object_slug": "people",
            "record_id": "invalid-id",
            "title": "Test",
            "body": "Content"
        })

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
                }
            ]
        }

        from sdrbot_cli.services.attio.tools import attio_list_notes

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_list_notes.invoke({
            "object_slug": "people",
            "record_id": "rec-123"
        })

        assert "Notes:" in result
        assert "Meeting Notes" in result
        assert "Follow-up" in result
        assert "2024-01-15" in result

    def test_list_notes_empty(self, patch_attio_client):
        """attio_list_notes should handle no notes."""
        patch_attio_client.request.return_value = {"data": []}

        from sdrbot_cli.services.attio.tools import attio_list_notes

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_list_notes.invoke({
            "object_slug": "companies",
            "record_id": "rec-456"
        })

        assert "No notes found" in result

    def test_list_notes_error(self, patch_attio_client):
        """attio_list_notes should handle API errors."""
        patch_attio_client.request.side_effect = Exception("Connection timeout")

        from sdrbot_cli.services.attio.tools import attio_list_notes

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_list_notes.invoke({
            "object_slug": "people",
            "record_id": "rec-123"
        })

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
                }
            }
        }

        from sdrbot_cli.services.attio.tools import attio_get_record

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_get_record.invoke({
            "object_slug": "people",
            "record_id": "rec-123"
        })

        assert "Record ID: rec-123" in result
        assert "John Doe" in result
        assert "john@example.com" in result
        assert "Acme Inc" in result

    def test_get_record_not_found(self, patch_attio_client):
        """attio_get_record should handle missing record."""
        patch_attio_client.request.return_value = {"data": {}}

        from sdrbot_cli.services.attio.tools import attio_get_record

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_get_record.invoke({
            "object_slug": "people",
            "record_id": "nonexistent-id"
        })

        assert "Record not found" in result

    def test_get_record_error(self, patch_attio_client):
        """attio_get_record should handle API errors."""
        patch_attio_client.request.side_effect = Exception("404 Not Found")

        from sdrbot_cli.services.attio.tools import attio_get_record

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_get_record.invoke({
            "object_slug": "invalid",
            "record_id": "rec-123"
        })

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
                }
            }
        }

        from sdrbot_cli.services.attio.tools import attio_get_record

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        result = attio_get_record.invoke({
            "object_slug": "companies",
            "record_id": "rec-456"
        })

        assert "Acme Corp" in result
        assert "acme.com" in result


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
        from sdrbot_cli.services.attio.tools import attio_list_notes

        import sdrbot_cli.services.attio.tools as tools_module
        tools_module._attio_client = None

        # Use a placeholder record - should return "No notes" or actual notes
        result = attio_list_notes.invoke({
            "object_slug": "people",
            "record_id": "test-record-id",
            "limit": 5
        })

        # Should either return notes or handle gracefully
        assert "notes" in result.lower() or "error" in result.lower()
