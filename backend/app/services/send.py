"""Send invoices — wraps run_send_invoices with 4 templates (FR, EN, Carole, Multi)."""
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
    """Build the invoice_folder dict the legacy script expects."""
    from scripts.storage_manager import list_invoice_folders
    folders = list_invoice_folders() or []
    for f in folders:
        if (f.get("month") or f.get("name")) == folder_name:
            return f
    raise RuntimeError(f"Dossier '{folder_name}' introuvable")


def preview_per_template(folder_name: str) -> dict[str, list[str]]:
    """Return {fr: [...], en: [...], carole: [...], multi: [...]} — family names
    that would receive each template, based on language + Carole detection +
    multimonth ids from payment_links_output.json."""
    data = _load_data()

    # Multimonth ids
    multimonth_ids: set[str] = set()
    pl_path = get_data_dir() / "payment_links_output.json"
    if pl_path.exists():
        try:
            for it in json.loads(pl_path.read_text(encoding="utf-8")):
                if str(it.get("includes_previous_months", "")).lower() == "true":
                    fid = it.get("family_id")
                    if fid:
                        multimonth_ids.add(fid)
        except Exception:
            pass

    fr, en, carole, multi = [], [], [], []
    for fam_id, fam in data.items():
        name = fam.get("parent_name") or fam_id
        ln = (fam.get("language") or "fr").lower()
        is_carole = ("carole" in name.lower()) and ("tessier" in name.lower())
        is_multi = fam_id in multimonth_ids
        # Priority: multi > carole > en > fr
        if is_multi:
            multi.append(name)
        elif is_carole:
            carole.append(name)
        elif ln in {"en", "anglais", "english"}:
            en.append(name)
        else:
            fr.append(name)
    return {"fr": sorted(fr), "en": sorted(en), "carole": sorted(carole), "multi": sorted(multi)}


def diagnostic(folder_name: str) -> dict[str, Any]:
    """Sanity check before sending: PDFs available, emails set, missing pieces."""
    from scripts.send_invoices_email import get_families_from_folder
    data = _load_data()
    folder = _invoice_folder(folder_name)
    fams = get_families_from_folder(folder, data)
    with_email = [f for f in fams if f.get("email")]
    without_email = [f for f in fams if not f.get("email")]
    return {
        "folder": folder_name,
        "total": len(fams),
        "with_email": len(with_email),
        "without_email": [f.get("parent_name") for f in without_email],
    }


async def run_send_job(
    *,
    folder_name: str,
    templates: dict[str, dict[str, str]],
    selected_families: list[str] | None,
    send_to_test: bool,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    """templates: {fr: {subject, body}, en: {...}, carole: {...}, multi: {...}}"""
    secrets = load_secrets()
    data = _load_data()
    folder = _invoice_folder(folder_name)

    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    # Multimonth ids again (for the script param)
    multimonth_ids: list[str] = []
    pl_path = get_data_dir() / "payment_links_output.json"
    if pl_path.exists():
        try:
            for it in json.loads(pl_path.read_text(encoding="utf-8")):
                if str(it.get("includes_previous_months", "")).lower() == "true":
                    fid = it.get("family_id")
                    if fid:
                        multimonth_ids.append(fid)
        except Exception:
            pass

    fr = templates.get("fr") or {}
    en = templates.get("en") or {}
    car = templates.get("carole") or {}
    mul = templates.get("multi") or {}

    from scripts.send_invoices_email import run_send_invoices
    result = await run_in_threadpool(
        run_send_invoices,
        secrets,
        data,
        folder,
        fr.get("subject"),
        fr.get("body"),
        selected_families,
        send_to_test,
        cb,
        en.get("subject"),
        en.get("body"),
        car.get("subject"),
        car.get("body"),
        mul.get("subject"),
        mul.get("body"),
        multimonth_ids or None,
    )
    on_progress(1.0)
    if result and not result.get("success", True):
        raise RuntimeError(result.get("error") or "Envoi factures échoué")
    on_log("✅ Envoi terminé")
    return result or {}


def default_templates(month_name: str | None = None, year: int | None = None) -> dict[str, dict[str, str]]:
    from scripts.send_invoices_email import get_default_email_template, get_default_multimonth_template
    fr = get_default_email_template(month_name, year, "fr")
    en = get_default_email_template(month_name, year, "en")
    mul = get_default_multimonth_template(month_name, year, None)
    # Carole template: hardcoded simple OCTOPUS subject
    car = {
        "subject": f"Invoice {month_name or ''} {year or ''} - OCTOPUS SARL".strip(),
        "body": fr.get("body", ""),
    }
    return {"fr": fr, "en": en, "carole": car, "multi": mul}
