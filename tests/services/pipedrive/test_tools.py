"""Tests for Pipedrive tools."""

import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestPipedriveToolLoading:
    """Test that Pipedrive tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.pipedrive.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 6
        tool_names = [t.name for t in tools]
        assert "pipedrive_search" in tool_names
        assert "pipedrive_add_note" in tool_names
        assert "pipedrive_list_notes" in tool_names
        assert "pipedrive_list_pipelines" in tool_names
        assert "pipedrive_list_users" in tool_names
        assert "pipedrive_get_deal_activities" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.pipedrive.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.pipedrive.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_get_tools_includes_static(self):
        """get_tools should include static tools."""
        from sdrbot_cli.services.pipedrive import get_tools

        tools = get_tools()
        tool_names = [t.name for t in tools]

        # Static tools should always be present
        assert "pipedrive_search" in tool_names
        assert "pipedrive_add_note" in tool_names
        assert "pipedrive_list_notes" in tool_names


class TestPipedriveToolsUnit:
    """Unit tests for Pipedrive tools with mocked API."""

    @pytest.fixture
    def mock_pipedrive_client(self):
        """Create a mock Pipedrive client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def patch_pipedrive_client(self, mock_pipedrive_client):
        """Patch Pipedrive client."""
        import sdrbot_cli.services.pipedrive.tools as tools_module

        original_client = tools_module._pipedrive_client
        tools_module._pipedrive_client = None

        with patch(
            "sdrbot_cli.services.pipedrive.tools.get_pipedrive_client",
            return_value=mock_pipedrive_client,
        ):
            yield mock_pipedrive_client

        tools_module._pipedrive_client = original_client

    def test_search_success(self, patch_pipedrive_client):
        """pipedrive_search should return formatted results."""
        patch_pipedrive_client.get.return_value = {
            "data": {
                "items": [
                    {
                        "item": {
                            "id": 123,
                            "title": "Acme Corp Deal",
                            "type": "deal",
                        }
                    },
                    {
                        "item": {
                            "id": 456,
                            "title": "John Doe",
                            "type": "person",
                        }
                    },
                ]
            }
        }

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_search

        tools_module._pipedrive_client = None

        result = pipedrive_search.invoke({"term": "acme"})

        assert "2 results" in result
        assert "Acme Corp Deal" in result
        assert "John Doe" in result

    def test_search_no_results(self, patch_pipedrive_client):
        """pipedrive_search should handle empty results."""
        patch_pipedrive_client.get.return_value = {"data": {"items": []}}

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_search

        tools_module._pipedrive_client = None

        result = pipedrive_search.invoke({"term": "nonexistent"})

        assert "No results found" in result

    def test_search_error(self, patch_pipedrive_client):
        """pipedrive_search should handle API errors."""
        patch_pipedrive_client.get.side_effect = Exception("API rate limit exceeded")

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_search

        tools_module._pipedrive_client = None

        result = pipedrive_search.invoke({"term": "test"})

        assert "Error" in result
        assert "rate limit" in result

    def test_add_note_success(self, patch_pipedrive_client):
        """pipedrive_add_note should return success message."""
        patch_pipedrive_client.post.return_value = {"data": {"id": 789}}

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_add_note

        tools_module._pipedrive_client = None

        result = pipedrive_add_note.invoke({"content": "Follow-up call scheduled", "deal_id": 123})

        assert "Successfully added note" in result
        assert "789" in result
        assert "Deal 123" in result

    def test_add_note_multiple_targets(self, patch_pipedrive_client):
        """pipedrive_add_note should attach to multiple entities."""
        patch_pipedrive_client.post.return_value = {"data": {"id": 999}}

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_add_note

        tools_module._pipedrive_client = None

        result = pipedrive_add_note.invoke(
            {"content": "Discussion notes", "deal_id": 123, "person_id": 456}
        )

        assert "Successfully added note" in result
        assert "Deal 123" in result
        assert "Person 456" in result

    def test_add_note_no_target(self, patch_pipedrive_client):
        """pipedrive_add_note should require at least one target."""
        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_add_note

        tools_module._pipedrive_client = None

        result = pipedrive_add_note.invoke({"content": "Orphaned note"})

        assert "Error" in result
        assert "at least one" in result

    def test_add_note_error(self, patch_pipedrive_client):
        """pipedrive_add_note should handle API errors."""
        patch_pipedrive_client.post.side_effect = Exception("Invalid deal ID")

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_add_note

        tools_module._pipedrive_client = None

        result = pipedrive_add_note.invoke({"content": "Test", "deal_id": 999999})

        assert "Error" in result
        assert "Invalid deal ID" in result

    def test_list_notes_for_deal(self, patch_pipedrive_client):
        """pipedrive_list_notes should return notes for a deal."""
        patch_pipedrive_client.get.return_value = {
            "data": [
                {
                    "id": 1,
                    "content": "Initial contact made",
                    "add_time": "2024-01-15 10:30:00",
                    "update_time": "2024-01-15 10:30:00",
                },
                {
                    "id": 2,
                    "content": "Proposal sent",
                    "add_time": "2024-01-16 14:00:00",
                    "update_time": "2024-01-16 14:00:00",
                },
            ]
        }

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_notes

        tools_module._pipedrive_client = None

        result = pipedrive_list_notes.invoke({"deal_id": 123})

        assert "2 notes" in result
        assert "Initial contact made" in result
        assert "Proposal sent" in result

    def test_list_notes_empty(self, patch_pipedrive_client):
        """pipedrive_list_notes should handle no notes."""
        patch_pipedrive_client.get.return_value = {"data": []}

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_notes

        tools_module._pipedrive_client = None

        result = pipedrive_list_notes.invoke({"person_id": 456})

        assert "No notes found" in result

    def test_list_notes_error(self, patch_pipedrive_client):
        """pipedrive_list_notes should handle API errors."""
        patch_pipedrive_client.get.side_effect = Exception("Connection timeout")

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_notes

        tools_module._pipedrive_client = None

        result = pipedrive_list_notes.invoke({"deal_id": 123})

        assert "Error" in result
        assert "Connection timeout" in result

    def test_list_pipelines_success(self, patch_pipedrive_client):
        """pipedrive_list_pipelines should return pipelines with stages."""
        patch_pipedrive_client.get.side_effect = [
            # First call: pipelines
            {
                "data": [
                    {
                        "id": 1,
                        "name": "Sales Pipeline",
                        "active": True,
                        "deal_probability": True,
                    },
                    {
                        "id": 2,
                        "name": "Enterprise Pipeline",
                        "active": True,
                        "deal_probability": True,
                    },
                ]
            },
            # Second call: stages for pipeline 1
            {
                "data": [
                    {"id": 1, "name": "Lead In", "order_nr": 1},
                    {"id": 2, "name": "Qualified", "order_nr": 2},
                ]
            },
            # Third call: stages for pipeline 2
            {
                "data": [
                    {"id": 3, "name": "Discovery", "order_nr": 1},
                    {"id": 4, "name": "Proposal", "order_nr": 2},
                ]
            },
        ]

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_pipelines

        tools_module._pipedrive_client = None

        result = pipedrive_list_pipelines.invoke({})

        assert "2 pipelines" in result
        assert "Sales Pipeline" in result
        assert "Enterprise Pipeline" in result
        assert "Lead In" in result
        assert "Qualified" in result

    def test_list_pipelines_empty(self, patch_pipedrive_client):
        """pipedrive_list_pipelines should handle no pipelines."""
        patch_pipedrive_client.get.return_value = {"data": []}

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_pipelines

        tools_module._pipedrive_client = None

        result = pipedrive_list_pipelines.invoke({})

        assert "No pipelines found" in result

    def test_list_pipelines_error(self, patch_pipedrive_client):
        """pipedrive_list_pipelines should handle API errors."""
        patch_pipedrive_client.get.side_effect = Exception("Unauthorized")

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_pipelines

        tools_module._pipedrive_client = None

        result = pipedrive_list_pipelines.invoke({})

        assert "Error" in result
        assert "Unauthorized" in result

    def test_list_users_success(self, patch_pipedrive_client):
        """pipedrive_list_users should return formatted user list."""
        patch_pipedrive_client.get.return_value = {
            "data": [
                {
                    "id": 1,
                    "name": "John Admin",
                    "email": "john@company.com",
                    "active_flag": True,
                    "role_id": 1,
                },
                {
                    "id": 2,
                    "name": "Jane Sales",
                    "email": "jane@company.com",
                    "active_flag": True,
                    "role_id": 2,
                },
            ]
        }

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_users

        tools_module._pipedrive_client = None

        result = pipedrive_list_users.invoke({})

        assert "2 users" in result
        assert "John Admin" in result
        assert "jane@company.com" in result

    def test_list_users_empty(self, patch_pipedrive_client):
        """pipedrive_list_users should handle no users."""
        patch_pipedrive_client.get.return_value = {"data": []}

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_users

        tools_module._pipedrive_client = None

        result = pipedrive_list_users.invoke({})

        assert "No users found" in result

    def test_list_users_error(self, patch_pipedrive_client):
        """pipedrive_list_users should handle API errors."""
        patch_pipedrive_client.get.side_effect = Exception("Forbidden")

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_users

        tools_module._pipedrive_client = None

        result = pipedrive_list_users.invoke({})

        assert "Error" in result
        assert "Forbidden" in result

    def test_get_deal_activities_success(self, patch_pipedrive_client):
        """pipedrive_get_deal_activities should return activities."""
        patch_pipedrive_client.get.return_value = {
            "data": [
                {
                    "id": 1,
                    "type": "call",
                    "subject": "Discovery call",
                    "due_date": "2024-01-20",
                    "due_time": "10:00",
                    "done": False,
                    "marked_as_done_time": None,
                },
                {
                    "id": 2,
                    "type": "meeting",
                    "subject": "Demo presentation",
                    "due_date": "2024-01-25",
                    "due_time": "14:00",
                    "done": True,
                    "marked_as_done_time": "2024-01-25 15:30:00",
                },
            ]
        }

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_get_deal_activities

        tools_module._pipedrive_client = None

        result = pipedrive_get_deal_activities.invoke({"deal_id": 123})

        assert "2 activities" in result
        assert "Discovery call" in result
        assert "Demo presentation" in result
        assert "call" in result
        assert "meeting" in result

    def test_get_deal_activities_empty(self, patch_pipedrive_client):
        """pipedrive_get_deal_activities should handle no activities."""
        patch_pipedrive_client.get.return_value = {"data": []}

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_get_deal_activities

        tools_module._pipedrive_client = None

        result = pipedrive_get_deal_activities.invoke({"deal_id": 456})

        assert "No activities found" in result

    def test_get_deal_activities_error(self, patch_pipedrive_client):
        """pipedrive_get_deal_activities should handle API errors."""
        patch_pipedrive_client.get.side_effect = Exception("Deal not found")

        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_get_deal_activities

        tools_module._pipedrive_client = None

        result = pipedrive_get_deal_activities.invoke({"deal_id": 999999})

        assert "Error" in result
        assert "Deal not found" in result


@pytest.mark.integration
class TestPipedriveToolsIntegration:
    """Integration tests for Pipedrive tools.

    Run with: pytest -m integration
    Requires Pipedrive API credentials.
    """

    @pytest.fixture
    def check_pipedrive_credentials(self):
        """Skip if Pipedrive credentials not available."""
        if not (
            os.getenv("PIPEDRIVE_API_TOKEN")
            or (os.getenv("PIPEDRIVE_CLIENT_ID") and os.getenv("PIPEDRIVE_CLIENT_SECRET"))
        ):
            pytest.skip("Pipedrive credentials not set - skipping integration test")

    def test_search_real(self, check_pipedrive_credentials):
        """Test search against real API."""
        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_search

        tools_module._pipedrive_client = None

        result = pipedrive_search.invoke({"term": "test", "limit": 5})

        # Should either return results or handle gracefully
        assert "results" in result.lower() or "no results" in result.lower()

    def test_list_users_real(self, check_pipedrive_credentials):
        """Test listing users against real API."""
        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_users

        tools_module._pipedrive_client = None

        result = pipedrive_list_users.invoke({"limit": 5})

        # Should either return users or handle gracefully
        assert "users" in result.lower() or "error" in result.lower()

    def test_list_pipelines_real(self, check_pipedrive_credentials):
        """Test listing pipelines against real API."""
        import sdrbot_cli.services.pipedrive.tools as tools_module
        from sdrbot_cli.services.pipedrive.tools import pipedrive_list_pipelines

        tools_module._pipedrive_client = None

        result = pipedrive_list_pipelines.invoke({})

        # Should either return pipelines or handle gracefully
        assert "pipelines" in result.lower() or "error" in result.lower()
