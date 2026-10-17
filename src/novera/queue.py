"""Persistent download queue (SQLite, same DB as history) with pause/resume/cancel."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .downloads import DownloadManager
from .downloads.manager import DownloadCancelled
from .history import HistoryStore

STATES = ("pending", "running", "paused", "done", "failed", "cancelled")


class QueueStore:
    def __init__(self, history: HistoryStore | None = None):
        self.h = history or HistoryStore()
        with self.h._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, status TEXT NOT NULL,
                error TEXT, sha256 TEXT, created_at TEXT NOT NULL)""")
            # A crash leaves 'running' rows; they resume as pending (partials resume safely).
            db.execute("UPDATE queue SET status='pending' WHERE status='running'")

    def add(self, url: str, sha256: str | None = None) -> int:
        from .security import validate_url
        url = validate_url(url)
        with self.h._connect() as db:
            return int(db.execute("INSERT INTO queue(url,status,sha256,created_at) VALUES(?,?,?,?)",
                                  (url, "pending", sha256, datetime.now(timezone.utc).isoformat(timespec="seconds"))).lastrowid)

    def list(self, status: str | None = None) -> list[dict]:
        with self.h._connect() as db:
            q = "SELECT * FROM queue" + (" WHERE status=?" if status else "") + " ORDER BY id"
            return [dict(r) for r in db.execute(q, (status,) if status else ())]

    def set(self, job_id: int, status: str, error: str | None = None) -> None:
        assert status in STATES
        with self.h._connect() as db:
            db.execute("UPDATE queue SET status=?, error=? WHERE id=?", (status, error, job_id))

    def mark(self, job_id: int, frm: tuple[str, ...], to: str) -> bool:
        with self.h._connect() as db:
            c = db.execute(f"UPDATE queue SET status=? WHERE id=? AND status IN ({','.join('?' * len(frm))})", (to, job_id, *frm))
            return c.rowcount > 0


class QueueRunner:
    """Runs pending jobs with bounded concurrency. Pause keeps .part files for safe resume."""

    def __init__(self, config, store: QueueStore | None = None, reporter_factory=None):
        self.config, self.store = config, store or QueueStore()
        self.reporter_factory = reporter_factory
        self._mgrs: dict[int, DownloadManager] = {}
        self._intent: dict[int, str] = {}
        self._lock = threading.Lock()

    def _signal(self, job_id: int, intent: str) -> None:
        with self._lock:
            self._intent[job_id] = intent
            mgr = self._mgrs.get(job_id)
        if mgr:
            mgr.cancel()

    def pause(self, job_id: int) -> None:
        if not self.store.mark(job_id, ("pending",), "paused"):
            self._signal(job_id, "paused")

    def cancel(self, job_id: int) -> None:
        if not self.store.mark(job_id, ("pending", "paused"), "cancelled"):
            self._signal(job_id, "cancelled")

    def resume(self, job_id: int) -> None:
        self.store.mark(job_id, ("paused", "failed", "cancelled"), "pending")

    def _run_job(self, job: dict) -> None:
        jid = job["id"]
        cb = self.reporter_factory(job) if self.reporter_factory else None
        mgr = DownloadManager(self.config, history=self.store.h, progress_callback=cb)
        with self._lock:
            self._mgrs[jid] = mgr
            if self._intent.get(jid):
                mgr.cancel()
        try:
            r = mgr.download(job["url"], expected_sha256=job.get("sha256"))
            self.store.set(jid, "done", None if r.status != "skipped" else "dilewati (file sudah ada)")
        except DownloadCancelled:
            self.store.set(jid, self._intent.get(jid, "cancelled"))
        except Exception as exc:  # noqa: BLE001 - reported per job
            self.store.set(jid, "failed", str(exc)[:300])
        finally:
            with self._lock:
                self._mgrs.pop(jid, None)
                self._intent.pop(jid, None)

    def run(self) -> dict[str, int]:
        jobs = self.store.list("pending")
        for j in jobs:
            self.store.set(j["id"], "running")
        with ThreadPoolExecutor(max_workers=self.config.downloads.concurrency, thread_name_prefix="novera-q") as pool:
            list(pool.map(self._run_job, jobs))
        counts: dict[str, int] = {}
        ids = {j["id"] for j in jobs}
        for j in self.store.list():
            if j["id"] in ids:
                counts[j["status"]] = counts.get(j["status"], 0) + 1
        return counts
