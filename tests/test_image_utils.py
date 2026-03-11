"""Tests for image_utils.py — _get_executable and exception narrowing."""

from __future__ import annotations

from unittest.mock import patch

from sdrbot_cli.image_utils import _get_executable, _get_linux_clipboard_image


class TestGetExecutable:
    def test_returns_path_when_found(self) -> None:
        with patch("sdrbot_cli.image_utils.shutil.which", return_value="/usr/bin/xclip"):
            assert _get_executable("xclip") == "/usr/bin/xclip"

    def test_returns_none_when_missing(self) -> None:
        with patch("sdrbot_cli.image_utils.shutil.which", return_value=None):
            assert _get_executable("nonexistent") is None


class TestLinuxClipboardValidation:
    """Verify _get_linux_clipboard_image bails out when xclip is not on PATH."""

    def test_returns_none_when_xclip_missing(self) -> None:
        with patch("sdrbot_cli.image_utils._get_executable", return_value=None):
            assert _get_linux_clipboard_image() is None
