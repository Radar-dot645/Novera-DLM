"""SQLite-backed download history."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_db_path() -> Path:
    return Path.home() / ".local" / "share" / "novera" / "history.sqlite3"


class HistoryStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                destination TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                sha256 TEXT,
                status TEXT NOT NULL,
                backend TEXT NOT NULL DEFAULT 'python-http',
                created_at TEXT NOT NULL
            )""")

    def add(self, *, url: str, destination: str, size_bytes: int = 0,
            sha256: str | None = None, status: str = "completed",
            backend: str = "python-http") -> int:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO downloads(url,destination,size_bytes,sha256,status,backend,created_at) VALUES(?,?,?,?,?,?,?)",
                (url, destination, int(size_bytes), sha256, status, backend, timestamp),
            )
            return int(cursor.lastrowid)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        with self._connect() as db:
            rows = db.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def clear(self) -> int:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM downloads")
            return int(cursor.rowcount)
