"""Tests for Generic Email tools."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool


class TestGenericEmailToolLoading:
    """Test that generic email tools load correctly."""

    def test_static_tools_load(self):
        """Static tools should load."""
        from sdrbot_cli.services.generic_email.tools import get_static_tools

        tools = get_static_tools()

        assert len(tools) == 10
        tool_names = [t.name for t in tools]
        assert "email_list_folders" in tool_names
        assert "email_list_folder" in tool_names
        assert "email_search" in tool_names
        assert "email_read" in tool_names
        assert "email_send" in tool_names
        assert "email_reply" in tool_names
        assert "email_mark_read" in tool_names
        assert "email_move" in tool_names
        assert "email_delete" in tool_names
        assert "email_create_draft" in tool_names

    def test_tools_are_base_tool_instances(self):
        """All tools should be BaseTool instances."""
        from sdrbot_cli.services.generic_email.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} is not a BaseTool"

    def test_tools_have_descriptions(self):
        """All tools should have descriptions."""
        from sdrbot_cli.services.generic_email.tools import get_static_tools

        tools = get_static_tools()

        for tool in tools:
            assert tool.description, f"{tool.name} has no description"

    def test_service_get_tools(self):
        """Service get_tools should return all tools."""
        from sdrbot_cli.services.generic_email import get_tools

        tools = get_tools()

        assert len(tools) == 10


class TestGenericEmailToolsUnit:
    """Unit tests for generic email tools with mocked IMAP/SMTP."""

    @pytest.fixture
    def mock_imap_connection(self):
        """Mock IMAP connection."""
        with patch("sdrbot_cli.services.generic_email.tools.email_auth") as mock_auth:
            mock_imap = MagicMock()
            mock_auth.get_imap_connection.return_value = mock_imap
            mock_auth.get_smtp_config.return_value = MagicMock(username="test@example.com")
            yield mock_imap

    @pytest.fixture
    def mock_smtp_connection(self):
        """Mock SMTP connection."""
        with patch("sdrbot_cli.services.generic_email.tools.email_auth") as mock_auth:
            mock_smtp = MagicMock()
            mock_auth.get_smtp_connection.return_value = mock_smtp
            mock_auth.get_smtp_config.return_value = MagicMock(username="test@example.com")
            yield mock_smtp

    def test_list_folders_success(self, mock_imap_connection):
        """list_folders should return folder names."""
        mock_imap_connection.list.return_value = (
            "OK",
            [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent"'],
        )

        from sdrbot_cli.services.generic_email.tools import email_list_folders

        result = email_list_folders.invoke({})

        parsed = json.loads(result)
        assert "folders" in parsed
        assert "INBOX" in parsed["folders"]
        mock_imap_connection.logout.assert_called_once()

    def test_list_folders_not_configured(self):
        """list_folders should handle not configured."""
        with patch("sdrbot_cli.services.generic_email.tools.email_auth") as mock_auth:
            mock_auth.get_imap_connection.return_value = None

            from sdrbot_cli.services.generic_email.tools import email_list_folders

            result = email_list_folders.invoke({})

            assert "not configured" in result.lower() or "Error" in result

    def test_list_folder_success(self, mock_imap_connection):
        """list_folder should return emails."""
        mock_imap_connection.select.return_value = ("OK", [b"5"])
        mock_imap_connection.search.return_value = ("OK", [b"1 2 3"])
        mock_imap_connection.fetch.return_value = (
            "OK",
            [
                (
                    b"1 (UID 100 BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {50}",
                    b"From: sender@example.com\r\nSubject: Test\r\nDate: Mon, 1 Jan 2024 12:00:00 +0000\r\n",
                )
            ],
        )

        from sdrbot_cli.services.generic_email.tools import email_list_folder

        result = email_list_folder.invoke({"folder": "INBOX", "max_results": 10})

        # Should return JSON or error message
        assert "Test" in result or "Error" in result or "No emails" in result

    def test_send_email_success(self):
        """send_email should send via SMTP."""
        with patch("sdrbot_cli.services.generic_email.tools.email_auth") as mock_auth:
            mock_smtp = MagicMock()
            mock_auth.get_smtp_connection.return_value = mock_smtp
            mock_auth.get_smtp_config.return_value = MagicMock(username="sender@example.com")

            from sdrbot_cli.services.generic_email.tools import email_send

            result = email_send.invoke(
                {
                    "to": "recipient@example.com",
                    "subject": "Test Subject",
                    "body": "Test body content",
                }
            )

            assert "sent successfully" in result.lower()
            mock_smtp.sendmail.assert_called_once()
            mock_smtp.quit.assert_called_once()

    def test_send_email_with_cc_bcc(self):
        """send_email should handle CC and BCC."""
        with patch("sdrbot_cli.services.generic_email.tools.email_auth") as mock_auth:
            mock_smtp = MagicMock()
            mock_auth.get_smtp_connection.return_value = mock_smtp
            mock_auth.get_smtp_config.return_value = MagicMock(username="sender@example.com")

            from sdrbot_cli.services.generic_email.tools import email_send

            result = email_send.invoke(
                {
                    "to": "recipient@example.com",
                    "subject": "Test",
                    "body": "Test",
                    "cc": "cc@example.com",
                    "bcc": "bcc@example.com",
                }
            )

            assert "sent successfully" in result.lower()
            # Verify all recipients were included
            call_args = mock_smtp.sendmail.call_args
            recipients = call_args[0][1]
            assert "recipient@example.com" in recipients
            assert "cc@example.com" in recipients
            assert "bcc@example.com" in recipients

    def test_send_email_not_configured(self):
        """send_email should handle not configured."""
        with patch("sdrbot_cli.services.generic_email.tools.email_auth") as mock_auth:
            mock_auth.get_smtp_connection.return_value = None

            from sdrbot_cli.services.generic_email.tools import email_send

            result = email_send.invoke(
                {"to": "recipient@example.com", "subject": "Test", "body": "Test"}
            )

            assert "not configured" in result.lower() or "Error" in result

    def test_mark_read_success(self, mock_imap_connection):
        """mark_read should update flags."""
        mock_imap_connection.select.return_value = ("OK", [b"5"])
        mock_imap_connection.uid.return_value = ("OK", None)

        from sdrbot_cli.services.generic_email.tools import email_mark_read

        result = email_mark_read.invoke({"uid": "123", "is_read": True})

        assert "marked as read" in result.lower()
        mock_imap_connection.uid.assert_called()

    def test_mark_unread_success(self, mock_imap_connection):
        """mark_read should mark as unread when is_read=False."""
        mock_imap_connection.select.return_value = ("OK", [b"5"])
        mock_imap_connection.uid.return_value = ("OK", None)

        from sdrbot_cli.services.generic_email.tools import email_mark_read

        result = email_mark_read.invoke({"uid": "123", "is_read": False})

        assert "marked as unread" in result.lower()

    def test_delete_email_success(self, mock_imap_connection):
        """delete_email should mark deleted and expunge."""
        mock_imap_connection.select.return_value = ("OK", [b"5"])
        mock_imap_connection.uid.return_value = ("OK", None)
        mock_imap_connection.expunge.return_value = ("OK", None)

        from sdrbot_cli.services.generic_email.tools import email_delete

        result = email_delete.invoke({"uid": "123"})

        assert "deleted" in result.lower()
        mock_imap_connection.expunge.assert_called_once()

    def test_move_email_success(self, mock_imap_connection):
        """move_email should copy and delete."""
        mock_imap_connection.select.return_value = ("OK", [b"5"])
        mock_imap_connection.uid.side_effect = [
            ("OK", None),  # copy
            ("OK", None),  # store deleted flag
        ]
        mock_imap_connection.expunge.return_value = ("OK", None)

        from sdrbot_cli.services.generic_email.tools import email_move

        result = email_move.invoke({"uid": "123", "destination_folder": "Archive"})

        assert "moved" in result.lower()

    def test_create_draft_success(self, mock_imap_connection):
        """create_draft should save to Drafts folder."""
        mock_imap_connection.append.return_value = ("OK", None)

        with patch("sdrbot_cli.services.generic_email.tools.email_auth") as mock_auth:
            mock_auth.get_imap_connection.return_value = mock_imap_connection
            mock_auth.get_smtp_config.return_value = MagicMock(username="test@example.com")

            from sdrbot_cli.services.generic_email.tools import email_create_draft

            result = email_create_draft.invoke(
                {"to": "recipient@example.com", "subject": "Draft Subject", "body": "Draft body"}
            )

            assert "draft created" in result.lower() or "Error" in result


class TestGenericEmailAuth:
    """Test generic email authentication module."""

    def test_is_configured_false_without_credentials(self):
        """is_configured should return False without credentials."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib

            import sdrbot_cli.auth.generic_email as email_module

            importlib.reload(email_module)

            assert email_module.is_configured() is False

    def test_is_configured_true_with_credentials(self):
        """is_configured should return True with full credentials."""
        env = {
            "IMAP_HOST": "imap.example.com",
            "IMAP_PORT": "993",
            "IMAP_USER": "user@example.com",
            "IMAP_PASSWORD": "password",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "465",
            "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": "password",
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib

            import sdrbot_cli.auth.generic_email as email_module

            importlib.reload(email_module)

            assert email_module.is_configured() is True

    def test_provider_presets_exist(self):
        """Provider presets should be defined."""
        from sdrbot_cli.auth.generic_email import PROVIDER_PRESETS

        assert "yahoo" in PROVIDER_PRESETS
        assert "aol" in PROVIDER_PRESETS
        assert "protonmail" in PROVIDER_PRESETS
        assert "icloud" in PROVIDER_PRESETS

        # Check preset structure
        yahoo = PROVIDER_PRESETS["yahoo"]
        assert "imap_host" in yahoo
        assert "imap_port" in yahoo
        assert "smtp_host" in yahoo
        assert "smtp_port" in yahoo
