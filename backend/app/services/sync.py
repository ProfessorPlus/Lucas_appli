"""Stripe → Notion sync (both split and no-split modes)."""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from app.services.config import load_secrets, load_secrets_no_prof
from app.services.paths import ensure_scripts_on_path

ensure_scripts_on_path()


async def run_sync_job(
    *,
    mode: str,
    since_date: date | None,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    if mode == "no-split":
        on_log("💸 Sync NO-SPLIT — Stripe → Notion (compte unique)")
        secrets_np = load_secrets_no_prof()
        secrets_notion = load_secrets()
        from scripts.no_prof_sync_stripe_notion import run_sync_stripe_notion_no_split
        result = await run_in_threadpool(
            run_sync_stripe_notion_no_split,
            secrets_np,
            secrets_notion,
            since_date,
            cb,
        )
    else:
        on_log("🔄 Sync NORMAL — Stripe Connect → Notion")
        secrets = load_secrets()
        from scripts.sync_stripe_notion import run_sync_stripe_notion
        result = await run_in_threadpool(run_sync_stripe_notion, secrets, since_date, cb)

    on_progress(1.0)
    if result and not result.get("success", True):
        raise RuntimeError(result.get("error") or "Sync échouée")
    on_log("✅ Sync terminée")
    return result or {}
