"""Tests for file_ops.py — encoding, offset bounds, and exception narrowing."""

from __future__ import annotations

from pathlib import Path

from sdrbot_cli.file_ops import (
    FileOpTracker,
    _safe_read,
    compute_unified_diff,
)

# ---------------------------------------------------------------------------
# _safe_read
# ---------------------------------------------------------------------------


def test_safe_read_uses_utf8(tmp_path: Path) -> None:
    """_safe_read should pass encoding='utf-8' so non-ASCII content works."""
    content = "café résumé naïve"
    p = tmp_path / "utf8.txt"
    p.write_text(content, encoding="utf-8")
    assert _safe_read(p) == content


def test_safe_read_returns_none_on_missing_file(tmp_path: Path) -> None:
    p = tmp_path / "no_such_file.txt"
    assert _safe_read(p) is None


def test_safe_read_returns_none_on_decode_error(tmp_path: Path) -> None:
    p = tmp_path / "binary.bin"
    p.write_bytes(b"\x80\x81\x82")
    assert _safe_read(p) is None


# ---------------------------------------------------------------------------
# Offset bounds check in complete_with_message
# ---------------------------------------------------------------------------


class _FakeToolMessage:
    """Minimal stand-in for a LangChain ToolMessage."""

    def __init__(self, tool_call_id: str, content: str, status: str = "success"):
        self.tool_call_id = tool_call_id
        self.content = content
        self.status = status


def test_offset_bounds_clamped(tmp_path: Path) -> None:
    """When offset > actual lines, it should be reset to 0."""
    tracker = FileOpTracker(assistant_id=None)

    # Start a read_file operation with an offset larger than content
    tracker.start_operation(
        "read_file",
        {"file_path": str(tmp_path / "f.txt"), "offset": 9999},
        "call-1",
    )

    msg = _FakeToolMessage("call-1", "line1\nline2\nline3")
    record = tracker.complete_with_message(msg)
    assert record is not None
    # offset was 9999 but content has 3 lines → offset clamped to 0
    assert record.metrics.start_line == 1


def test_offset_within_bounds(tmp_path: Path) -> None:
    """When offset is within bounds, start_line = offset + 1."""
    tracker = FileOpTracker(assistant_id=None)
    tracker.start_operation(
        "read_file",
        {"file_path": str(tmp_path / "f.txt"), "offset": 2},
        "call-2",
    )
    msg = _FakeToolMessage("call-2", "line1\nline2\nline3")
    record = tracker.complete_with_message(msg)
    assert record is not None
    assert record.metrics.start_line == 3  # offset 2 + 1


# ---------------------------------------------------------------------------
# compute_unified_diff
# ---------------------------------------------------------------------------


def test_compute_unified_diff_no_change() -> None:
    assert compute_unified_diff("a\nb\n", "a\nb\n", "test.txt") is None


def test_compute_unified_diff_with_change() -> None:
    diff = compute_unified_diff("a\nb\n", "a\nc\n", "test.txt")
    assert diff is not None
    assert "-b" in diff
    assert "+c" in diff


def test_compute_unified_diff_max_lines() -> None:
    before = "\n".join(str(i) for i in range(100))
    after = "\n".join(str(i + 1000) for i in range(100))
    diff = compute_unified_diff(before, after, "test.txt", max_lines=10)
    assert diff is not None
    assert diff.endswith("...")
