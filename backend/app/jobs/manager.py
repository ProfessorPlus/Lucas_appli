"""SQLite-backed job manager for fire-and-poll long-running tasks."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterator

from app.core.config import settings

JobFunc = Callable[["JobContext"], Awaitable[Any]]


@dataclass
class JobContext:
    job_id: str
    _manager: "JobManager"

    def log(self, message: str) -> None:
        self._manager.append_log(self.job_id, message)

    def progress(self, value: float) -> None:
        self._manager.set_progress(self.job_id, max(0.0, min(1.0, value)))


class JobManager:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.jobs_db_path
        self._lock = threading.Lock()
        self._listeners: dict[str, list[asyncio.Queue[str]]] = {}
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    logs TEXT NOT NULL DEFAULT '[]',
                    result TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def create(self, name: str) -> str:
        job_id = uuid.uuid4().hex[:12]
        now = time.time()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO jobs (id, name, status, created_at, updated_at) VALUES (?, ?, 'pending', ?, ?)",
                (job_id, name, now, now),
            )
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "progress": row["progress"],
            "logs": json.loads(row["logs"] or "[]"),
            "result": json.loads(row["result"]) if row["result"] else None,
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def append_log(self, job_id: str, message: str) -> None:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute("SELECT logs FROM jobs WHERE id = ?", (job_id,)).fetchone()
                if not row:
                    return
                logs = json.loads(row["logs"] or "[]")
                logs.append(message)
                conn.execute(
                    "UPDATE jobs SET logs = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(logs), time.time(), job_id),
                )
        self._notify(job_id, json.dumps({"type": "log", "message": message}))

    def set_progress(self, job_id: str, value: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET progress = ?, updated_at = ? WHERE id = ?",
                (value, time.time(), job_id),
            )
        self._notify(job_id, json.dumps({"type": "progress", "value": value}))

    def _set_status(
        self,
        job_id: str,
        status: str,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, result = ?, error = ?, updated_at = ? WHERE id = ?",
                (
                    status,
                    json.dumps(result) if result is not None else None,
                    error,
                    time.time(),
                    job_id,
                ),
            )
        self._notify(job_id, json.dumps({"type": "status", "status": status}))

    async def run(self, job_id: str, func: JobFunc) -> None:
        ctx = JobContext(job_id=job_id, _manager=self)
        self._set_status(job_id, "running")
        try:
            result = await func(ctx)
            self._set_status(job_id, "done", result=result)
        except Exception as exc:
            self._set_status(job_id, "error", error=str(exc))

    def cleanup_old(self) -> int:
        cutoff = time.time() - settings.jobs_retention_hours * 3600
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE updated_at < ?", (cutoff,))
            return cursor.rowcount

    def subscribe(self, job_id: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._listeners.setdefault(job_id, []).append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[str]) -> None:
        listeners = self._listeners.get(job_id, [])
        if queue in listeners:
            listeners.remove(queue)

    def _notify(self, job_id: str, payload: str) -> None:
        for queue in self._listeners.get(job_id, []):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass


_manager_instance: JobManager | None = None


def get_job_manager() -> JobManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = JobManager()
    return _manager_instance
