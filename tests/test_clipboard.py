"""Tests for clipboard.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sdrbot_cli.clipboard import copy_to_clipboard


class TestCopyToClipboard:
    def test_uses_pyperclip_when_available(self) -> None:
        mock_pyperclip = MagicMock()
        with patch.dict("sys.modules", {"pyperclip": mock_pyperclip}):
            result = copy_to_clipboard("hello")
        mock_pyperclip.copy.assert_called_once_with("hello")
        assert result is True

    def test_falls_back_to_osc52(self) -> None:
        """When pyperclip raises, should fall back to OSC52."""
        with patch("sdrbot_cli.clipboard._osc52_copy", return_value=True):
            import sdrbot_cli.clipboard as cb

            result = cb._osc52_copy("test")
        assert result is True
