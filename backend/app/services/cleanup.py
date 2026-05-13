"""Notion cleanup — scan dates / delete old rows / clean duplicates."""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from app.services.config import load_secrets
from app.services.paths import ensure_scripts_on_path

ensure_scripts_on_path()


async def scan_dates() -> dict[str, Any]:
    from scripts.cleanup_notion import run_scan_notion_dates
    return await run_in_threadpool(run_scan_notion_dates, load_secrets(), None)


async def run_delete_old_job(
    *,
    keep_from_date: date,
    dry_run: bool,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)
    from scripts.cleanup_notion import run_delete_old_rows
    result = await run_in_threadpool(run_delete_old_rows, load_secrets(), keep_from_date, dry_run, cb)
    on_progress(1.0)
    return result or {}


async def run_cleanup_duplicates_job(
    *,
    dry_run: bool,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)
    from scripts.cleanup_notion import run_cleanup_duplicates
    result = await run_in_threadpool(run_cleanup_duplicates, load_secrets(), dry_run, cb)
    on_progress(1.0)
    return result or {}
