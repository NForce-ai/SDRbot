"""Tests for non-interactive mode."""

from __future__ import annotations

import subprocess
import sys


class TestCLIFlags:
    """Verify the CLI argument parser accepts the new flags."""

    def test_usage_includes_non_interactive(self) -> None:
        """Parser usage text mentions -n flag."""
        result = subprocess.run(
            [sys.executable, "-m", "sdrbot_cli.main", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # add_help=False means --help is unrecognized, but usage goes to stderr
        combined = result.stdout + result.stderr
        assert "-n" in combined

    def test_parse_non_interactive_flags(self) -> None:
        """Verify parse_args accepts the new flags without crashing."""
        # Monkey-patch sys.argv for testing
        import sys as _sys

        from sdrbot_cli.main import parse_args

        old_argv = _sys.argv
        try:
            _sys.argv = [
                "sdrbot",
                "--non-interactive",
                "-p",
                "Hello world",
                "--output-format",
                "json",
                "--max-turns",
                "10",
            ]
            args = parse_args()
            assert args.non_interactive is True
            assert args.prompt == "Hello world"
            assert args.output_format == "json"
            assert args.max_turns == 10
        finally:
            _sys.argv = old_argv
