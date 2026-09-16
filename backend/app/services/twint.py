"""Twint — statut et activation de la capability `twint_payments` sur Connect."""
from __future__ import annotations

from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from app.services.config import load_secrets
from app.services.paths import ensure_scripts_on_path

ensure_scripts_on_path()


async def status() -> dict[str, Any]:
    from scripts.activate_twint import get_twint_status
    return await run_in_threadpool(get_twint_status, load_secrets(), None)


def connect_accounts() -> list[dict[str, str]]:
    """Profs ayant un compte Connect — seuls candidats à l'activation Twint."""
    teachers = (load_secrets() or {}).get("teachers", {}) or {}
    return [
        {"name": name, "connect_account_id": (info or {}).get("connect_account_id", "")}
        for name, info in teachers.items()
        if (info or {}).get("connect_account_id")
    ]


async def run_activate_job(
    *,
    account_ids: list[str],
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    if not account_ids:
        on_progress(1.0)
        return {"success": True, "activated": 0, "errors": [], "skipped": "aucun compte sélectionné"}

    from scripts.activate_twint import activate_twint_for_accounts
    result = await run_in_threadpool(activate_twint_for_accounts, load_secrets(), account_ids, cb)
    on_progress(1.0)
    return result or {}
