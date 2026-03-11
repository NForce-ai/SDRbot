"""SQLite-backed session persistence for conversation threads.

Provides an ``AsyncSqliteSaver`` checkpointer so conversations survive
restarts, plus lightweight CRUD helpers for listing / resuming / deleting
threads.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from sdrbot_cli.config import get_config_dir


def _sessions_db_path() -> Path:
    """Return the path to the sessions database file."""
    return get_config_dir() / "sessions.db"


async def get_checkpointer():
    """Create an ``AsyncSqliteSaver`` pointed at ``.sdrbot/sessions.db``.

    Opens the underlying ``aiosqlite`` connection and creates tables.
    The returned saver must be closed with ``await saver.conn.close()``
    when the application exits.

    Returns:
        An ``AsyncSqliteSaver`` instance ready for use.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db_path = str(_sessions_db_path())
    # Ensure parent directory exists
    _sessions_db_path().parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver


def _extract_first_human_message(checkpoint_blob: bytes) -> str:
    """Extract the first human message from a msgpack checkpoint blob.

    Parses the raw bytes to find the first HumanMessage content string
    without requiring the msgpack library.
    """
    try:
        text = checkpoint_blob.decode("utf-8", errors="replace")
        idx = text.find("HumanMessage")
        if idx < 0:
            return ""
        content_idx = text.find("content", idx)
        if content_idx < 0:
            return ""
        # Content value starts after the msgpack string-length byte(s)
        # following the "content" key.  Grab a window and strip non-printable chars.
        raw = text[content_idx + 7 : content_idx + 200]
        cleaned = re.sub(r"[^\x20-\x7e]", "", raw).strip()
        # Stop at known msgpack key boundaries
        for boundary in ("additional_kwargs", "response_metadata", "type"):
            bi = cleaned.find(boundary)
            if bi > 0:
                cleaned = cleaned[:bi].strip()
                break
        # Strip leading non-alpha chars (msgpack length-prefix residue)
        cleaned = re.sub(r"^[^a-zA-Z0-9]+", "", cleaned)
        return cleaned
    except Exception:
        return ""


def _extract_timestamp(checkpoint_blob: bytes) -> str:
    """Extract the ISO-8601 timestamp from a msgpack checkpoint blob."""
    try:
        text = checkpoint_blob.decode("utf-8", errors="replace")
        match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", text)
        if match:
            return match.group(0).replace("T", " ")
        return ""
    except Exception:
        return ""


def list_threads(*, limit: int = 50) -> list[dict[str, Any]]:
    """Return recent conversation threads from the sessions database.

    Each dict contains:
    - ``thread_id`` (str)
    - ``preview`` (str) — first human message, truncated
    - ``timestamp`` (str) — approximate creation time
    - ``steps`` (int) — number of agent steps

    Sorted most-recent first.
    """
    db_path = _sessions_db_path()
    if not db_path.exists():
        return []

    results: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(str(db_path))
        # Get the earliest checkpoint per thread (for first message preview)
        # and the latest checkpoint_id (for ordering by recency).
        rows = conn.execute(
            """
            SELECT thread_id,
                   MIN(checkpoint_id) AS first_ckpt_id,
                   MAX(checkpoint_id) AS last_ckpt_id
            FROM checkpoints
            WHERE checkpoint_ns = ''
            GROUP BY thread_id
            ORDER BY MAX(checkpoint_id) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        for thread_id, first_ckpt_id, _last_ckpt_id in rows:
            # Fetch the earliest checkpoint blob for preview + timestamp
            row = conn.execute(
                """
                SELECT checkpoint, metadata FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = '' AND checkpoint_id = ?
                """,
                (thread_id, first_ckpt_id),
            ).fetchone()

            preview = ""
            timestamp = ""
            steps = 0
            if row:
                preview = _extract_first_human_message(row[0])
                timestamp = _extract_timestamp(row[0])

            # Get step count from the latest checkpoint metadata
            latest = conn.execute(
                """
                SELECT metadata FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ''
                ORDER BY checkpoint_id DESC LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
            if latest and latest[0]:
                import json

                try:
                    meta = json.loads(latest[0])
                    steps = meta.get("step", 0)
                except (json.JSONDecodeError, TypeError):
                    pass

            results.append(
                {
                    "thread_id": thread_id,
                    "preview": preview[:80] if preview else "(empty)",
                    "timestamp": timestamp,
                    "steps": steps,
                }
            )
        conn.close()
    except (sqlite3.Error, OSError):
        pass

    return results


def get_most_recent() -> str | None:
    """Return the ``thread_id`` of the most recently updated thread, or ``None``."""
    threads = list_threads(limit=1)
    if threads:
        return threads[0]["thread_id"]
    return None


def delete_thread(thread_id: str) -> bool:
    """Remove all checkpoints for *thread_id*.

    Returns ``True`` if any rows were deleted.
    """
    db_path = _sessions_db_path()
    if not db_path.exists():
        return False

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?",
            (thread_id,),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted
    except (sqlite3.Error, OSError):
        return False
