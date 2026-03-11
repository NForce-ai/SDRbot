"""Integration tests for session persistence (sessions.py)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from sdrbot_cli.sessions import (
    delete_thread,
    get_checkpointer,
    get_most_recent,
    list_threads,
)


@pytest.fixture()
def tmp_sessions_db(tmp_path):
    """Redirect sessions database to a temporary directory."""
    db_path = tmp_path / "sessions.db"
    with patch("sdrbot_cli.sessions._sessions_db_path", return_value=db_path):
        yield db_path


class TestListThreadsEmpty:
    def test_returns_empty_when_no_db(self, tmp_sessions_db) -> None:
        assert list_threads() == []

    def test_get_most_recent_none(self, tmp_sessions_db) -> None:
        assert get_most_recent() is None


class TestDeleteThread:
    def test_delete_nonexistent_db(self, tmp_sessions_db) -> None:
        assert delete_thread("does-not-exist") is False


class TestCheckpointerCreation:
    def test_get_checkpointer_returns_saver(self, tmp_sessions_db) -> None:
        async def _run():
            saver = await get_checkpointer()
            assert saver is not None
            assert hasattr(saver, "conn")
            await saver.conn.close()

        asyncio.run(_run())
