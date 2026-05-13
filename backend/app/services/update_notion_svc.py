"""Update Notion — add lessons + scan-compare + add-missing."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from app.services.config import load_familles_euros, load_secrets
from app.services.paths import PROJECT_ROOT, ensure_scripts_on_path, get_data_dir

ensure_scripts_on_path()


def _load_data() -> dict[str, Any]:
    p = get_data_dir() / "full_output_tb_SIMPLE.json"
    if not p.exists():
        raise RuntimeError("Pas de données extraites.")
    return json.loads(p.read_text(encoding="utf-8"))


async def run_update_all_job(
    *,
    no_split: bool,
    invoice_date_override: str | None,
    additional_amounts: dict[str, Any] | None,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    secrets = load_secrets()
    data = _load_data()
    familles_euros = load_familles_euros()

    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    from scripts.update_notion import run_update_notion
    result = await run_in_threadpool(
        run_update_notion,
        secrets,
        data,
        str(PROJECT_ROOT),
        cb,
        no_split,
        familles_euros,
        invoice_date_override,
        additional_amounts,
    )
    on_progress(1.0)
    if result and not result.get("success", True):
        raise RuntimeError(result.get("error") or "Update Notion échoué")
    on_log("✅ Notion mis à jour")
    return result or {}


async def run_update_selective_job(
    *,
    invoice_folder_path: str,
    selected_family_ids: list[str] | None,
    selected_teachers: list[str] | None,
    no_split: bool,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    secrets = load_secrets()
    data = _load_data()

    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    from scripts.update_notion import run_update_notion_selective
    result = await run_in_threadpool(
        run_update_notion_selective,
        secrets, data, invoice_folder_path,
        selected_family_ids, selected_teachers,
        cb, no_split,
    )
    on_progress(1.0)
    if result and not result.get("success", True):
        raise RuntimeError(result.get("error") or "Update Notion (sélection) échoué")
    return result or {}


def scan_and_compare(invoice_folder_path: str) -> dict[str, Any]:
    """Synchronous — compares Drive PDFs to existing Notion rows."""
    from scripts.update_notion import run_scan_and_compare
    secrets = load_secrets()
    data = _load_data()
    return run_scan_and_compare(secrets, data, invoice_folder_path, callback=None)


async def run_add_missing_job(
    *,
    missing_rows: list[dict[str, Any]],
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    secrets = load_secrets()
    data = _load_data()

    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    from scripts.update_notion import run_add_missing_rows
    result = await run_in_threadpool(run_add_missing_rows, secrets, data, missing_rows, cb)
    on_progress(1.0)
    if result and not result.get("success", True):
        raise RuntimeError(result.get("error") or "Ajout des manquantes échoué")
    return result or {}
