"""Invoices — wraps generate_invoices.run_generate_invoices.
Respects Carole OCTOPUS + multi-mois (additional_amounts) + AED + cleanup-replace."""
from __future__ import annotations

import json
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from app.services.config import load_familles_euros, load_secrets
from app.services.paths import PROJECT_ROOT, ensure_scripts_on_path, get_data_dir, get_invoices_dir

ensure_scripts_on_path()


def _load_data() -> dict[str, Any]:
    p = get_data_dir() / "full_output_tb_SIMPLE.json"
    if not p.exists():
        raise RuntimeError("Pas de données extraites — lance d'abord une extraction.")
    return json.loads(p.read_text(encoding="utf-8"))


def _logo_path() -> str | None:
    candidates = [
        PROJECT_ROOT / "assets" / "logo.png",
        PROJECT_ROOT / "logo.png",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


async def run_generate_job(
    *,
    target_folder_path: str | None,
    force_new_folder: bool,
    previous_unpaid_data: dict[str, Any] | None,
    previous_month_label: str | None,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    on_log("📂 Chargement des données + configs…")
    data = _load_data()
    secrets = load_secrets()
    familles_euros = load_familles_euros()
    on_log(f"  ✓ {len(data)} familles · {len(familles_euros)} familles EUR")

    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    from scripts.generate_invoices import run_generate_invoices

    result = await run_in_threadpool(
        run_generate_invoices,
        data,
        secrets,
        familles_euros,
        str(get_data_dir()),
        str(PROJECT_ROOT),
        _logo_path(),
        cb,
        target_folder_path,
        force_new_folder,
        previous_unpaid_data,
        previous_month_label,
    )
    on_progress(1.0)
    if result and not result.get("success", True):
        raise RuntimeError(result.get("error") or "Génération factures échouée")
    on_log("✅ Factures générées")
    return result or {}


def detect_unpaid_n2(year: int, month: int) -> dict[str, Any]:
    from scripts.fetch_unpaid_notion import fetch_unpaid_n2
    return fetch_unpaid_n2(load_secrets(), year, month)
