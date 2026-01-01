"""Tests for Gmail tools."""

import base64
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestGmailToolLoading:
    """Test that Gmail tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.gmail.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 9
        tool_names = [t.name for t in tools]
        assert "gmail_search_emails" in tool_names
        assert "gmail_read_email" in tool_names
        assert "gmail_send_email" in tool_names
        assert "gmail_reply_to_email" in tool_names
        assert "gmail_create_draft" in tool_names
        assert "gmail_list_labels" in tool_names
        assert "gmail_modify_labels" in tool_names
        assert "gmail_trash_email" in tool_names
        assert "gmail_get_thread" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.gmail.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.gmail.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_service_get_tools(self):
        """Service get_tools should return all tools."""
        from sdrbot_cli.services.gmail import get_tools

        tools = get_tools()

        assert len(tools) == 9


class TestGmailToolsUnit:
    """Unit tests for Gmail tools with mocked API."""

    @pytest.fixture
    def mock_gmail_auth(self):
        """Mock Gmail auth to return headers."""
        with patch("sdrbot_cli.services.gmail.tools.gmail_auth") as mock_auth:
            mock_auth.get_headers.return_value = {"Authorization": "Bearer test-token"}
            yield mock_auth

    @pytest.fixture
    def mock_requests(self):
        """Mock requests library."""
        with patch("sdrbot_cli.services.gmail.tools.requests") as mock_req:
            yield mock_req

    def test_search_emails_success(self, mock_gmail_auth, mock_requests):
        """search_emails should return formatted results."""
        # Mock list messages response
        mock_list_resp = MagicMock()
        mock_list_resp.ok = True
        mock_list_resp.json.return_value = {
            "messages": [
                {"id": "msg1", "threadId": "thread1"},
                {"id": "msg2", "threadId": "thread2"},
            ]
        }

        # Mock get message details responses
        mock_detail_resp = MagicMock()
        mock_detail_resp.ok = True
        mock_detail_resp.json.return_value = {
            "id": "msg1",
            "threadId": "thread1",
            "snippet": "This is a test email...",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
                ]
            },
        }

        mock_requests.get.side_effect = [mock_list_resp, mock_detail_resp, mock_detail_resp]

        from sdrbot_cli.services.gmail.tools import gmail_search_emails

        result = gmail_search_emails.invoke({"query": "from:test@example.com", "max_results": 10})

        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["subject"] == "Test Subject"
        assert parsed[0]["from"] == "sender@example.com"

    def test_search_emails_no_results(self, mock_gmail_auth, mock_requests):
        """search_emails should handle empty results."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"messages": []}

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_search_emails

        result = gmail_search_emails.invoke({"query": "nonexistent", "max_results": 10})

        assert "No emails found" in result

    def test_search_emails_error(self, mock_gmail_auth, mock_requests):
        """search_emails should handle API errors."""
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_search_emails

        result = gmail_search_emails.invoke({"query": "test", "max_results": 10})

        assert "Error" in result
        assert "401" in result

    def test_read_email_success(self, mock_gmail_auth, mock_requests):
        """read_email should return full email content."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        # Encode a simple body
        body_text = "Hello, this is the email body."
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        mock_resp.json.return_value = {
            "id": "msg123",
            "threadId": "thread123",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Email"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
                ],
                "body": {"data": encoded_body},
            },
        }

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_read_email

        result = gmail_read_email.invoke({"message_id": "msg123"})

        parsed = json.loads(result)
        assert parsed["id"] == "msg123"
        assert parsed["subject"] == "Test Email"
        assert parsed["from"] == "sender@example.com"
        assert "Hello, this is the email body" in parsed["body"]

    def test_send_email_success(self, mock_gmail_auth, mock_requests):
        """send_email should send and return message ID."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "sent123"}

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_send_email

        result = gmail_send_email.invoke(
            {
                "to": "recipient@example.com",
                "subject": "Test Subject",
                "body": "Test body content",
            }
        )

        assert "sent123" in result
        assert "successfully" in result.lower()

    def test_send_email_with_cc_bcc(self, mock_gmail_auth, mock_requests):
        """send_email should handle CC and BCC."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "sent124"}

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_send_email

        result = gmail_send_email.invoke(
            {
                "to": "recipient@example.com",
                "subject": "Test",
                "body": "Test",
                "cc": "cc@example.com",
                "bcc": "bcc@example.com",
            }
        )

        assert "sent124" in result

    def test_send_email_error(self, mock_gmail_auth, mock_requests):
        """send_email should handle errors."""
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_send_email

        result = gmail_send_email.invoke({"to": "invalid", "subject": "Test", "body": "Test"})

        assert "Error" in result

    def test_create_draft_success(self, mock_gmail_auth, mock_requests):
        """create_draft should create and return draft ID."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "draft123"}

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_create_draft

        result = gmail_create_draft.invoke(
            {"to": "recipient@example.com", "subject": "Draft Subject", "body": "Draft body"}
        )

        assert "draft123" in result
        assert "Draft created" in result

    def test_list_labels_success(self, mock_gmail_auth, mock_requests):
        """list_labels should return formatted labels."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "STARRED", "name": "STARRED", "type": "system"},
                {"id": "Label_1", "name": "Work", "type": "user"},
            ]
        }

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_list_labels

        result = gmail_list_labels.invoke({})

        parsed = json.loads(result)
        assert "system_labels" in parsed
        assert "user_labels" in parsed
        assert len(parsed["system_labels"]) == 2
        assert len(parsed["user_labels"]) == 1

    def test_modify_labels_success(self, mock_gmail_auth, mock_requests):
        """modify_labels should update labels."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "msg123", "labelIds": ["INBOX", "STARRED"]}

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_modify_labels

        result = gmail_modify_labels.invoke(
            {"message_id": "msg123", "add_labels": "STARRED", "remove_labels": "UNREAD"}
        )

        assert "modified successfully" in result.lower()

    def test_modify_labels_no_changes(self, mock_gmail_auth, mock_requests):
        """modify_labels should error if no labels specified."""
        from sdrbot_cli.services.gmail.tools import gmail_modify_labels

        result = gmail_modify_labels.invoke(
            {"message_id": "msg123", "add_labels": "", "remove_labels": ""}
        )

        assert "Error" in result
        assert "at least one label" in result.lower()

    def test_trash_email_success(self, mock_gmail_auth, mock_requests):
        """trash_email should move email to trash."""
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": "msg123"}

        mock_requests.post.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_trash_email

        result = gmail_trash_email.invoke({"message_id": "msg123"})

        assert "msg123" in result
        assert "trash" in result.lower()

    def test_get_thread_success(self, mock_gmail_auth, mock_requests):
        """get_thread should return all messages in thread."""
        body_text = "Message content"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "id": "thread123",
            "messages": [
                {
                    "id": "msg1",
                    "snippet": "First message...",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "sender@example.com"},
                            {"name": "To", "value": "recipient@example.com"},
                            {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
                            {"name": "Subject", "value": "Thread Subject"},
                        ],
                        "body": {"data": encoded_body},
                    },
                },
                {
                    "id": "msg2",
                    "snippet": "Reply message...",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "recipient@example.com"},
                            {"name": "To", "value": "sender@example.com"},
                            {"name": "Date", "value": "Mon, 1 Jan 2024 13:00:00 +0000"},
                            {"name": "Subject", "value": "Re: Thread Subject"},
                        ],
                        "body": {"data": encoded_body},
                    },
                },
            ],
        }

        mock_requests.get.return_value = mock_resp

        from sdrbot_cli.services.gmail.tools import gmail_get_thread

        result = gmail_get_thread.invoke({"thread_id": "thread123"})

        parsed = json.loads(result)
        assert parsed["threadId"] == "thread123"
        assert len(parsed["messages"]) == 2
        assert parsed["messages"][0]["id"] == "msg1"
        assert parsed["messages"][1]["id"] == "msg2"

    def test_reply_to_email_success(self, mock_gmail_auth, mock_requests):
        """reply_to_email should send reply in thread."""
        body_text = "Original message content"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

        # Mock get original message
        mock_get_resp = MagicMock()
        mock_get_resp.ok = True
        mock_get_resp.json.return_value = {
            "id": "msg123",
            "threadId": "thread123",
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Subject", "value": "Original Subject"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
                    {"name": "Message-ID", "value": "<original@example.com>"},
                ],
                "body": {"data": encoded_body},
            },
        }

        # Mock send reply
        mock_send_resp = MagicMock()
        mock_send_resp.ok = True
        mock_send_resp.json.return_value = {"id": "reply123"}

        mock_requests.get.return_value = mock_get_resp
        mock_requests.post.return_value = mock_send_resp

        from sdrbot_cli.services.gmail.tools import gmail_reply_to_email

        result = gmail_reply_to_email.invoke(
            {"message_id": "msg123", "body": "This is my reply", "reply_all": False}
        )

        assert "reply123" in result
        assert "Reply sent" in result


class TestGmailAuth:
    """Test Gmail authentication module."""

    def test_is_configured_false_without_credentials(self):
        """is_configured should return False without credentials."""
        with patch.dict(os.environ, {}, clear=True):
            # Force reimport to pick up env changes
            import importlib

            import sdrbot_cli.auth.gmail as gmail_module

            # Reload to get fresh env vars
            importlib.reload(gmail_module)

            # With no env vars, should not be configured
            assert gmail_module.is_configured() is False

    def test_is_configured_true_with_credentials(self):
        """is_configured should return True with credentials."""
        with patch.dict(
            os.environ,
            {"GMAIL_CLIENT_ID": "test-id", "GMAIL_CLIENT_SECRET": "test-secret"},
        ):
            import importlib

            import sdrbot_cli.auth.gmail as gmail_module

            importlib.reload(gmail_module)

            assert gmail_module.is_configured() is True


@pytest.mark.integration
class TestGmailToolsIntegration:
    """Integration tests for Gmail tools.

    Run with: pytest -m integration
    Requires GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in environment,
    plus completed OAuth flow (stored token in keyring).
    """

    @pytest.fixture
    def check_gmail_auth(self):
        """Skip if Gmail not configured."""
        if not os.getenv("GMAIL_CLIENT_ID") or not os.getenv("GMAIL_CLIENT_SECRET"):
            pytest.skip("GMAIL_CLIENT_ID/SECRET not set - skipping integration test")

    def test_list_labels_real(self, check_gmail_auth):
        """Test listing labels against real API."""
        from sdrbot_cli.services.gmail.tools import gmail_list_labels

        result = gmail_list_labels.invoke({})

        # Should return valid JSON with labels
        parsed = json.loads(result)
        assert "system_labels" in parsed or "Error" in result

    def test_search_emails_real(self, check_gmail_auth):
        """Test searching emails against real API."""
        from sdrbot_cli.services.gmail.tools import gmail_search_emails

        result = gmail_search_emails.invoke({"query": "is:inbox", "max_results": 3})

        # Should return valid JSON or no results message
        assert "Error" not in result or "No emails found" in result
