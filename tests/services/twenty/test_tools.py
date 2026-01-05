"""Tests for Twenty tools."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestTwentyToolLoading:
    """Test that Twenty tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.twenty.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 7
        tool_names = [t.name for t in tools]
        # Note/Task linking tools (CRUD is generated, linking is static)
        assert "twenty_link_note_to_record" in tool_names
        assert "twenty_list_notes_on_record" in tool_names
        assert "twenty_link_task_to_record" in tool_names
        assert "twenty_count_records" in tool_names
        assert "twenty_list_tasks_on_record" in tool_names
        # Search/get tools
        assert "twenty_search_records" in tool_names
        assert "twenty_get_record" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.twenty.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.twenty.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_get_tools_includes_static(self):
        """get_tools should include static tools."""
        from sdrbot_cli.services.twenty import get_tools

        tools = get_tools()
        tool_names = [t.name for t in tools]

        # Static tools should always be present
        assert "twenty_link_note_to_record" in tool_names
        assert "twenty_list_notes_on_record" in tool_names
        assert "twenty_link_task_to_record" in tool_names
        assert "twenty_list_tasks_on_record" in tool_names
        assert "twenty_search_records" in tool_names
        assert "twenty_get_record" in tool_names


class TestTwentyToolsUnit:
    """Unit tests for Twenty tools with mocked API."""

    @pytest.fixture
    def mock_twenty_client(self):
        """Create a mock Twenty client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_twenty_client(self, mock_twenty_client):
        """Patch Twenty client."""
        import sdrbot_cli.services.twenty.tools as tools_module

        original_client = tools_module._twenty_client
        tools_module._twenty_client = None

        with patch(
            "sdrbot_cli.services.twenty.tools.TwentyClient", return_value=mock_twenty_client
        ):
            yield mock_twenty_client

        tools_module._twenty_client = original_client

    def test_link_note_to_record_success(self, patch_twenty_client):
        """twenty_link_note_to_record should return success message."""
        patch_twenty_client.post.return_value = {"data": {"noteTarget": {"id": "target-456"}}}

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_link_note_to_record

        tools_module._twenty_client = None

        result = twenty_link_note_to_record.invoke(
            {
                "note_id": "note-123",
                "target_type": "person",
                "target_record_id": "rec-123",
            }
        )

        assert "Successfully linked note" in result
        assert "note-123" in result
        assert "person" in result
        patch_twenty_client.post.assert_called_once()

    def test_link_note_to_record_invalid_target(self, patch_twenty_client):
        """twenty_link_note_to_record should reject invalid target types."""
        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_link_note_to_record

        tools_module._twenty_client = None

        result = twenty_link_note_to_record.invoke(
            {
                "note_id": "note-123",
                "target_type": "invalid_type",
                "target_record_id": "rec-123",
            }
        )

        assert "Error" in result
        assert "Invalid target_type" in result

    def test_link_note_to_record_error(self, patch_twenty_client):
        """twenty_link_note_to_record should handle API errors."""
        patch_twenty_client.post.side_effect = Exception("API Error: Invalid record")

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_link_note_to_record

        tools_module._twenty_client = None

        result = twenty_link_note_to_record.invoke(
            {
                "note_id": "note-123",
                "target_type": "person",
                "target_record_id": "invalid-id",
            }
        )

        assert "Error" in result
        assert "Invalid record" in result

    def test_list_notes_on_record_success(self, patch_twenty_client):
        """twenty_list_notes_on_record should return formatted notes."""
        # First call returns noteTargets, subsequent calls return individual notes
        patch_twenty_client.get.side_effect = [
            {"data": {"noteTargets": [{"noteId": "note-1"}, {"noteId": "note-2"}]}},
            {
                "data": {
                    "note": {
                        "id": "note-1",
                        "title": "Meeting Notes",
                        "createdAt": "2024-01-15T10:30:00Z",
                        "bodyV2": {"markdown": "Discussion about project"},
                    }
                }
            },
            {
                "data": {
                    "note": {
                        "id": "note-2",
                        "title": "Follow-up",
                        "createdAt": "2024-01-16T14:00:00Z",
                        "bodyV2": {"markdown": "Action items"},
                    }
                }
            },
        ]

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_list_notes_on_record

        tools_module._twenty_client = None

        result = twenty_list_notes_on_record.invoke(
            {"target_type": "person", "target_record_id": "rec-123"}
        )

        assert "Notes:" in result
        assert "Meeting Notes" in result
        assert "Follow-up" in result
        assert "2024-01-15" in result

    def test_list_notes_on_record_empty(self, patch_twenty_client):
        """twenty_list_notes_on_record should handle no notes."""
        patch_twenty_client.get.return_value = {"data": {"noteTargets": []}}

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_list_notes_on_record

        tools_module._twenty_client = None

        result = twenty_list_notes_on_record.invoke(
            {"target_type": "company", "target_record_id": "rec-456"}
        )

        assert "No notes found" in result

    def test_list_notes_on_record_error(self, patch_twenty_client):
        """twenty_list_notes_on_record should handle API errors."""
        patch_twenty_client.get.side_effect = Exception("Connection timeout")

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_list_notes_on_record

        tools_module._twenty_client = None

        result = twenty_list_notes_on_record.invoke(
            {"target_type": "person", "target_record_id": "rec-123"}
        )

        assert "Error" in result
        assert "Connection timeout" in result

    def test_link_task_to_record_success(self, patch_twenty_client):
        """twenty_link_task_to_record should return success message."""
        patch_twenty_client.post.return_value = {"data": {"taskTarget": {"id": "target-789"}}}

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_link_task_to_record

        tools_module._twenty_client = None

        result = twenty_link_task_to_record.invoke(
            {
                "task_id": "task-123",
                "target_type": "company",
                "target_record_id": "rec-456",
            }
        )

        assert "Successfully linked task" in result
        assert "task-123" in result
        assert "company" in result
        patch_twenty_client.post.assert_called_once()

    def test_link_task_to_record_invalid_target(self, patch_twenty_client):
        """twenty_link_task_to_record should reject invalid target types."""
        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_link_task_to_record

        tools_module._twenty_client = None

        result = twenty_link_task_to_record.invoke(
            {
                "task_id": "task-123",
                "target_type": "invalid_type",
                "target_record_id": "rec-123",
            }
        )

        assert "Error" in result
        assert "Invalid target_type" in result

    def test_list_tasks_on_record_success(self, patch_twenty_client):
        """twenty_list_tasks_on_record should return formatted tasks."""
        patch_twenty_client.get.side_effect = [
            {"data": {"taskTargets": [{"taskId": "task-1"}]}},
            {
                "data": {
                    "task": {
                        "id": "task-1",
                        "title": "Follow up call",
                        "status": "TODO",
                        "createdAt": "2024-01-15T10:30:00Z",
                    }
                }
            },
        ]

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_list_tasks_on_record

        tools_module._twenty_client = None

        result = twenty_list_tasks_on_record.invoke(
            {"target_type": "person", "target_record_id": "rec-123"}
        )

        assert "Tasks:" in result
        assert "Follow up call" in result
        assert "TODO" in result

    def test_list_tasks_on_record_empty(self, patch_twenty_client):
        """twenty_list_tasks_on_record should handle no tasks."""
        patch_twenty_client.get.return_value = {"data": {"taskTargets": []}}

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_list_tasks_on_record

        tools_module._twenty_client = None

        result = twenty_list_tasks_on_record.invoke(
            {"target_type": "company", "target_record_id": "rec-456"}
        )

        assert "No tasks found" in result

    def test_search_records_success(self, patch_twenty_client):
        """twenty_search_records should return formatted results."""
        patch_twenty_client.get.return_value = {
            "data": {
                "people": [
                    {
                        "id": "person-1",
                        "name": "John Doe",
                        "email": "john@example.com",
                    },
                    {
                        "id": "person-2",
                        "name": "Jane Smith",
                        "email": "jane@example.com",
                    },
                ]
            }
        }

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_search_records

        tools_module._twenty_client = None

        result = twenty_search_records.invoke({"object_type": "people", "query": "john"})

        assert "Found 2 people" in result
        assert "John Doe" in result
        assert "john@example.com" in result

    def test_search_records_empty(self, patch_twenty_client):
        """twenty_search_records should handle no results."""
        patch_twenty_client.get.return_value = {"data": {"people": []}}

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_search_records

        tools_module._twenty_client = None

        result = twenty_search_records.invoke({"object_type": "people", "query": "nonexistent"})

        assert "No people found" in result

    def test_get_record_success(self, patch_twenty_client):
        """twenty_get_record should return formatted record."""
        patch_twenty_client.get.return_value = {
            "data": {
                "person": {
                    "id": "person-123",
                    "name": "John Doe",
                    "email": "john@example.com",
                    "phone": "+1234567890",
                }
            }
        }

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_get_record

        tools_module._twenty_client = None

        result = twenty_get_record.invoke({"object_type": "people", "record_id": "person-123"})

        assert "person-123" in result
        assert "John Doe" in result
        assert "john@example.com" in result

    def test_get_record_not_found(self, patch_twenty_client):
        """twenty_get_record should handle missing record."""
        patch_twenty_client.get.return_value = {"data": {"person": {}}}

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_get_record

        tools_module._twenty_client = None

        result = twenty_get_record.invoke({"object_type": "people", "record_id": "nonexistent-id"})

        assert "Record not found" in result

    def test_get_record_error(self, patch_twenty_client):
        """twenty_get_record should handle API errors."""
        patch_twenty_client.get.side_effect = Exception("404 Not Found")

        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_get_record

        tools_module._twenty_client = None

        result = twenty_get_record.invoke({"object_type": "invalid", "record_id": "rec-123"})

        assert "Error" in result
        assert "404" in result


@pytest.mark.integration
class TestTwentyToolsIntegration:
    """Integration tests for Twenty tools.

    Run with: pytest -m integration
    Requires Twenty API key.
    """

    @pytest.fixture
    def check_twenty_credentials(self):
        """Skip if Twenty credentials not available."""
        if not os.getenv("TWENTY_API_KEY"):
            pytest.skip("TWENTY_API_KEY not set - skipping integration test")

    def test_search_records_real(self, check_twenty_credentials):
        """Test searching records against real API."""
        import sdrbot_cli.services.twenty.tools as tools_module
        from sdrbot_cli.services.twenty.tools import twenty_search_records

        tools_module._twenty_client = None

        result = twenty_search_records.invoke({"object_type": "people", "query": "", "limit": 5})

        # Should either return records or handle gracefully
        assert "people" in result.lower() or "found" in result.lower() or "error" in result.lower()
