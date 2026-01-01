"""Tests for Outlook tools."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestOutlookToolLoading:
    """Test that Outlook tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.outlook.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 13
        tool_names = [t.name for t in tools]
        assert "outlook_search_emails" in tool_names
        assert "outlook_read_email" in tool_names
        assert "outlook_send_email" in tool_names
        assert "outlook_reply_to_email" in tool_names
        assert "outlook_create_draft" in tool_names
        assert "outlook_send_draft" in tool_names
        assert "outlook_schedule_email" in tool_names
        assert "outlook_list_folders" in tool_names
        assert "outlook_list_folder_emails" in tool_names
        assert "outlook_move_email" in tool_names
        assert "outlook_mark_read" in tool_names
        assert "outlook_delete_email" in tool_names
        assert "outlook_get_conversation" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.outlook.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.outlook.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_service_get_tools(self):
        """Service get_tools should return all tools."""
        from sdrbot_cli.services.outlook import get_tools

        tools = get_tools()

        assert len(tools) == 13


class TestOutlookToolsUnit:
    """Unit tests for Outlook tools with mocked API."""

    @pytest.fixture
    def mock_outlook_auth(self):
        """Mock Outlook auth to return headers."""
        with patch("sdrbot_cli.services.outlook.tools.outlook_auth") as mock_auth:
            mock_auth.get_headers.return_value = {"Authorization": "Bearer test-token"}
            yield mock_auth

    @pytest.fixture
    def mock_requests(self):
        """Mock requests library."""
        with patch("sdrbot_cli.services.outlook.tools.requests") as mock_req:
            yield mock_req

    def test_search_emails_success(self, mock_outlook_auth, mock_requests):
        """search_emails should return formatted results."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "value": [
                {
                    "id": "msg1",
                    "subject": "Test Subject",
                    "from": {"emailAddress": {"name": "Sender", "address": "sender@example.com"}},
                    "receivedDateTime": "2024-01-01T12:00:00Z",
                    "bodyPreview": "This is a preview...",
                    "isRead": False,
                    "importance": "normal",
                },
            ]
        }

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_search_emails

        result = outlook_search_emails.invoke({"query": "from:test@example.com", "max_results": 10})

        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["subject"] == "Test Subject"
        assert "sender@example.com" in parsed[0]["from"]

    def test_search_emails_no_results(self, mock_outlook_auth, mock_requests):
        """search_emails should handle empty results."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"value": []}

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_search_emails

        result = outlook_search_emails.invoke({"query": "nonexistent", "max_results": 10})

        assert "No emails found" in result

    def test_search_emails_error(self, mock_outlook_auth, mock_requests):
        """search_emails should handle API errors."""
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_search_emails

        result = outlook_search_emails.invoke({"query": "test", "max_results": 10})

        assert "Error" in result
        assert "401" in result

    def test_read_email_success(self, mock_outlook_auth, mock_requests):
        """read_email should return full email content."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "id": "msg123",
            "conversationId": "conv123",
            "subject": "Test Email",
            "from": {"emailAddress": {"name": "Sender", "address": "sender@example.com"}},
            "toRecipients": [
                {"emailAddress": {"name": "Recipient", "address": "recipient@example.com"}}
            ],
            "ccRecipients": [],
            "receivedDateTime": "2024-01-01T12:00:00Z",
            "isRead": True,
            "importance": "normal",
            "hasAttachments": False,
            "body": {"contentType": "text", "content": "Hello, this is the email body."},
        }

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_read_email

        result = outlook_read_email.invoke({"message_id": "msg123"})

        parsed = json.loads(result)
        assert parsed["id"] == "msg123"
        assert parsed["subject"] == "Test Email"
        assert "sender@example.com" in parsed["from"]
        assert "Hello, this is the email body" in parsed["body"]

    def test_send_email_success(self, mock_outlook_auth, mock_requests):
        """send_email should send and return confirmation."""
        mock_resp = MagicMock()
        mock_resp.ok = True

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_send_email

        result = outlook_send_email.invoke(
            {
                "to": "recipient@example.com",
                "subject": "Test Subject",
                "body": "Test body content",
            }
        )

        assert "sent successfully" in result.lower()

    def test_send_email_with_cc_bcc(self, mock_outlook_auth, mock_requests):
        """send_email should handle CC and BCC."""
        mock_resp = MagicMock()
        mock_resp.ok = True

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_send_email

        result = outlook_send_email.invoke(
            {
                "to": "recipient@example.com",
                "subject": "Test",
                "body": "Test",
                "cc": "cc@example.com",
                "bcc": "bcc@example.com",
            }
        )

        assert "sent successfully" in result.lower()

    def test_send_email_error(self, mock_outlook_auth, mock_requests):
        """send_email should handle errors."""
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_send_email

        result = outlook_send_email.invoke({"to": "invalid", "subject": "Test", "body": "Test"})

        assert "Error" in result

    def test_create_draft_success(self, mock_outlook_auth, mock_requests):
        """create_draft should create and return draft ID."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "draft123"}

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_create_draft

        result = outlook_create_draft.invoke(
            {"to": "recipient@example.com", "subject": "Draft Subject", "body": "Draft body"}
        )

        assert "draft123" in result
        assert "Draft created" in result

    def test_schedule_email_success(self, mock_outlook_auth, mock_requests):
        """schedule_email should create draft with deferred time and move to outbox."""
        # Mock draft creation
        mock_draft_resp = MagicMock()
        mock_draft_resp.ok = True
        mock_draft_resp.json.return_value = {"id": "draft123"}

        # Mock outbox folder lookup
        mock_outbox_resp = MagicMock()
        mock_outbox_resp.ok = True
        mock_outbox_resp.json.return_value = {"id": "outbox-folder-id"}

        # Mock move to outbox
        mock_move_resp = MagicMock()
        mock_move_resp.ok = True

        mock_requests.post.side_effect = [mock_draft_resp, mock_move_resp]
        mock_requests.get.return_value = mock_outbox_resp

        from sdrbot_cli.services.outlook.tools import outlook_schedule_email

        result = outlook_schedule_email.invoke(
            {
                "to": "recipient@example.com",
                "subject": "Scheduled Email",
                "body": "This will be sent later",
                "send_at": "2024-12-25T09:00:00Z",
            }
        )

        assert "scheduled successfully" in result.lower()
        assert "2024-12-25T09:00:00Z" in result

    def test_schedule_email_error_on_draft(self, mock_outlook_auth, mock_requests):
        """schedule_email should handle draft creation error."""
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 400
        mock_resp.text = "Invalid request"

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_schedule_email

        result = outlook_schedule_email.invoke(
            {
                "to": "recipient@example.com",
                "subject": "Test",
                "body": "Test",
                "send_at": "2024-12-25T09:00:00Z",
            }
        )

        assert "Error" in result

    def test_list_folders_success(self, mock_outlook_auth, mock_requests):
        """list_folders should return formatted folders."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "value": [
                {
                    "id": "inbox-id",
                    "displayName": "Inbox",
                    "totalItemCount": 100,
                    "unreadItemCount": 5,
                },
                {
                    "id": "sent-id",
                    "displayName": "Sent Items",
                    "totalItemCount": 50,
                    "unreadItemCount": 0,
                },
            ]
        }

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_list_folders

        result = outlook_list_folders.invoke({})

        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Inbox"
        assert parsed[0]["unreadItems"] == 5

    def test_move_email_success(self, mock_outlook_auth, mock_requests):
        """move_email should move email to folder."""
        # Mock folder lookup
        mock_folder_resp = MagicMock()
        mock_folder_resp.ok = True
        mock_folder_resp.json.return_value = {"id": "archive-folder-id"}

        # Mock move operation
        mock_move_resp = MagicMock()
        mock_move_resp.ok = True

        mock_requests.get.return_value = mock_folder_resp
        mock_requests.post.return_value = mock_move_resp

        from sdrbot_cli.services.outlook.tools import outlook_move_email

        result = outlook_move_email.invoke(
            {"message_id": "msg123", "destination_folder": "Archive"}
        )

        assert "moved" in result.lower()
        assert "Archive" in result

    def test_mark_read_success(self, mock_outlook_auth, mock_requests):
        """mark_read should update email read status."""
        mock_resp = MagicMock()
        mock_resp.ok = True

        mock_requests.patch.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_mark_read

        result = outlook_mark_read.invoke({"message_id": "msg123", "is_read": True})

        assert "marked as read" in result.lower()

    def test_mark_unread_success(self, mock_outlook_auth, mock_requests):
        """mark_read should mark as unread when is_read=False."""
        mock_resp = MagicMock()
        mock_resp.ok = True

        mock_requests.patch.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_mark_read

        result = outlook_mark_read.invoke({"message_id": "msg123", "is_read": False})

        assert "marked as unread" in result.lower()

    def test_delete_email_success(self, mock_outlook_auth, mock_requests):
        """delete_email should delete email."""
        mock_resp = MagicMock()
        mock_resp.ok = True

        mock_requests.delete.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_delete_email

        result = outlook_delete_email.invoke({"message_id": "msg123"})

        assert "msg123" in result
        assert "deleted" in result.lower()

    def test_get_conversation_success(self, mock_outlook_auth, mock_requests):
        """get_conversation should return all messages in thread."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "value": [
                {
                    "id": "msg1",
                    "subject": "Thread Subject",
                    "from": {"emailAddress": {"name": "Sender", "address": "sender@example.com"}},
                    "receivedDateTime": "2024-01-01T12:00:00Z",
                    "bodyPreview": "First message...",
                    "isRead": True,
                },
                {
                    "id": "msg2",
                    "subject": "Re: Thread Subject",
                    "from": {
                        "emailAddress": {"name": "Recipient", "address": "recipient@example.com"}
                    },
                    "receivedDateTime": "2024-01-01T13:00:00Z",
                    "bodyPreview": "Reply message...",
                    "isRead": True,
                },
            ]
        }

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_get_conversation

        result = outlook_get_conversation.invoke({"conversation_id": "conv123"})

        parsed = json.loads(result)
        assert parsed["conversationId"] == "conv123"
        assert len(parsed["messages"]) == 2
        assert parsed["messages"][0]["id"] == "msg1"
        assert parsed["messages"][1]["id"] == "msg2"

    def test_reply_to_email_success(self, mock_outlook_auth, mock_requests):
        """reply_to_email should send reply."""
        mock_resp = MagicMock()
        mock_resp.ok = True

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_reply_to_email

        result = outlook_reply_to_email.invoke(
            {"message_id": "msg123", "body": "This is my reply", "reply_all": False}
        )

        assert "Reply sent" in result

    def test_reply_all_success(self, mock_outlook_auth, mock_requests):
        """reply_to_email should handle reply_all."""
        mock_resp = MagicMock()
        mock_resp.ok = True

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.outlook.tools import outlook_reply_to_email

        result = outlook_reply_to_email.invoke(
            {"message_id": "msg123", "body": "Reply to all", "reply_all": True}
        )

        assert "Reply sent" in result
        assert "reply_all=True" in result


class TestOutlookAuth:
    """Test Outlook authentication module."""

    def test_is_configured_false_without_credentials(self):
        """is_configured should return False without credentials."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib

            import sdrbot_cli.auth.outlook as outlook_module

            importlib.reload(outlook_module)

            assert outlook_module.is_configured() is False

    def test_is_configured_true_with_credentials(self):
        """is_configured should return True with credentials."""
        with patch.dict(
            os.environ,
            {"OUTLOOK_CLIENT_ID": "test-id", "OUTLOOK_CLIENT_SECRET": "test-secret"},
        ):
            import importlib

            import sdrbot_cli.auth.outlook as outlook_module

            importlib.reload(outlook_module)

            assert outlook_module.is_configured() is True


@pytest.mark.integration
class TestOutlookToolsIntegration:
    """Integration tests for Outlook tools.

    Run with: pytest -m integration
    Requires OUTLOOK_CLIENT_ID and OUTLOOK_CLIENT_SECRET in environment,
    plus completed OAuth flow (stored token in keyring).
    """

    @pytest.fixture
    def check_outlook_auth(self):
        """Skip if Outlook not configured."""
        if not os.getenv("OUTLOOK_CLIENT_ID") or not os.getenv("OUTLOOK_CLIENT_SECRET"):
            pytest.skip("OUTLOOK_CLIENT_ID/SECRET not set - skipping integration test")

    def test_list_folders_real(self, check_outlook_auth):
        """Test listing folders against real API."""
        from sdrbot_cli.services.outlook.tools import outlook_list_folders

        result = outlook_list_folders.invoke({})

        # Should return valid JSON with folders or error
        parsed = json.loads(result)
        assert isinstance(parsed, list) or "Error" in result

    def test_search_emails_real(self, check_outlook_auth):
        """Test searching emails against real API."""
        from sdrbot_cli.services.outlook.tools import outlook_search_emails

        result = outlook_search_emails.invoke({"query": "isRead:true", "max_results": 3})

        # Should return valid JSON or no results message
        assert "Error" not in result or "No emails found" in result
