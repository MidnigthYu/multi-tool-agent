"""SQLite 会话数据表 CRUD 封装 -- WAL 模式。"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SQLiteClient:
    def __init__(self, db_path: str, busy_timeout_s: int = 5) -> None:
        self._db_path = str(Path(db_path).resolve())
        self._busy_timeout_ms = busy_timeout_s * 1000
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, timeout=self._busy_timeout_ms / 1000)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms};")
        return self._conn

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "session_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "summary TEXT DEFAULT '', metadata TEXT DEFAULT '{}')"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
            "role TEXT NOT NULL, content TEXT NOT NULL, timestamp TEXT NOT NULL, "
            "metadata TEXT DEFAULT '{}', "
            "FOREIGN KEY (session_id) REFERENCES sessions(session_id))"
        )
        self.conn.commit()

    def create_session(self, session_id: str, thread_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, thread_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, thread_id, now, now),
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def save_message(self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, now, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        self.conn.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))
        self.conn.commit()

    def get_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?", (session_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_summary(self, session_id: str, summary: str) -> None:
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            "UPDATE sessions SET summary = ?, updated_at = ? WHERE session_id = ?", (summary, now, session_id)
        )
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


_sqlite_instance: SQLiteClient | None = None


def get_sqlite_client(db_path: str = "data/sessions.db") -> SQLiteClient:
    global _sqlite_instance
    if _sqlite_instance is None:
        _sqlite_instance = SQLiteClient(db_path)
    return _sqlite_instance
