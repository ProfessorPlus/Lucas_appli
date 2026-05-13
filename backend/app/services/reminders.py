"""Payment reminders — wraps run_send_reminders."""
from __future__ import annotations

import json
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from app.services.config import load_secrets
from app.services.paths import ensure_scripts_on_path, get_data_dir

ensure_scripts_on_path()


def _load_data() -> dict[str, Any]:
    p = get_data_dir() / "full_output_tb_SIMPLE.json"
    if not p.exists():
        raise RuntimeError("Pas de données extraites.")
    return json.loads(p.read_text(encoding="utf-8"))


def _invoice_folder(folder_name: str) -> dict[str, Any]:
    from scripts.storage_manager import list_invoice_folders
    folders = list_invoice_folders() or []
    for f in folders:
        if (f.get("month") or f.get("name")) == folder_name:
            return f
    raise RuntimeError(f"Dossier '{folder_name}' introuvable")


def unpaid_families(folder_name: str) -> dict[str, Any]:
    from scripts.send_payment_reminders import get_unpaid_families_from_notion
    return get_unpaid_families_from_notion(
        load_secrets(), callback=None, data=_load_data(), invoice_folder=_invoice_folder(folder_name),
    )


def default_template() -> dict[str, str]:
    from scripts.send_payment_reminders import get_default_reminder_template
    return get_default_reminder_template()


def should_send_auto() -> dict[str, Any]:
    """Auto-detect candidates rule (used by Streamlit's banner on accueil)."""
    try:
        from scripts.send_payment_reminders import should_send_automatic_reminder
        return {"should_send": bool(should_send_automatic_reminder())}
    except Exception as exc:  # noqa: BLE001
        return {"should_send": False, "error": str(exc)}


async def run_send_reminders_job(
    *,
    folder_name: str,
    templates: dict[str, dict[str, str]],
    selected_families: list[str] | None,
    send_to_test: bool,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    secrets = load_secrets()
    data = _load_data()
    folder = _invoice_folder(folder_name)

    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    fr = templates.get("fr") or {}
    en = templates.get("en") or {}
    car = templates.get("carole") or {}

    from scripts.send_payment_reminders import run_send_reminders
    result = await run_in_threadpool(
        run_send_reminders,
        secrets,
        data,
        folder,
        str(get_data_dir()),
        fr.get("subject"),
        fr.get("body"),
        selected_families,
        send_to_test,
        cb,
        en.get("subject"),
        en.get("body"),
        car.get("subject"),
        car.get("body"),
    )
    on_progress(1.0)
    if result and not result.get("success", True):
        raise RuntimeError(result.get("error") or "Envoi rappels échoué")
    on_log("✅ Rappels envoyés")
    return result or {}
