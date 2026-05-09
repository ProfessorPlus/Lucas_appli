"""Extract orchestrator — runs the legacy `run_extraction` in a threadpool
and computes the post-extraction summary (multi-currency + net EUR).

Aligned with MIGRATION_SPEC critical behaviors:
- A. Multi-currency calculated lesson-by-lesson (loop on amounts_by_currency).
- B. Notion 'profs hors TB' merged with TutorBird families.
- H. AbsentNotice lessons excluded by `run_extraction` itself.
"""
from __future__ import annotations

import json
from datetime import date, time
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from app.services.config import load_secrets, load_familles_euros, load_tarifs_speciaux
from app.services.notion import fetch_profs_hors_tb, convert_profs_to_families
from app.services.paths import ensure_scripts_on_path, get_data_dir

ensure_scripts_on_path()


async def run_extract_job(
    *,
    start_date: date,
    end_date: date,
    start_time: time,
    end_time: time,
    notion_prof_page_ids: list[str] | None,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    """Run extraction + post-process. Designed to be called inside a JobContext."""
    from scripts.extract_tutorbird import run_extraction

    secrets = load_secrets()
    if not secrets:
        raise RuntimeError("secrets.yaml introuvable — configure d'abord les Paramètres.")

    on_log("🔧 Chargement des configs (secrets, familles_euros, tarifs)...")
    familles_euros = load_familles_euros()
    tarifs_speciaux = load_tarifs_speciaux()
    on_log(f"  ✓ {len(familles_euros)} familles EUR · {len(tarifs_speciaux)} tarifs spéciaux")

    notion_families: dict[str, Any] | None = None
    if notion_prof_page_ids is not None:
        on_log("📥 Récupération des Profs hors TutorBird (Notion)...")
        result = await run_in_threadpool(fetch_profs_hors_tb)
        if not result.get("success"):
            on_log(f"  ⚠️ Notion : {result.get('error', 'erreur inconnue')}")
        else:
            entries = result.get("entries", [])
            on_log(f"  ✓ {len(entries)} entrées Notion lues")
            if notion_prof_page_ids:
                notion_families = convert_profs_to_families(entries, notion_prof_page_ids)
                on_log(f"  ✓ {len(notion_families)} familles Notion sélectionnées et converties")
            else:
                notion_families = {}

    data_dir = str(get_data_dir())

    def progress_cb(progress: int, message: str) -> None:
        # The legacy script uses 0-100 ints; our JobContext uses 0-1 floats.
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    on_log("🚀 Lancement de l'extraction TutorBird...")
    result = await run_in_threadpool(
        run_extraction,
        secrets,
        start_date,
        end_date,
        start_time,
        end_time,
        data_dir,
        progress_cb,
        notion_families,
    )

    if not result.get("success"):
        raise RuntimeError(result.get("error") or "Extraction TutorBird échouée")

    on_progress(1.0)
    on_log("✅ Extraction terminée")

    # ── Post-process : compute summary aligned with the dashboard fix ──
    summary = _compute_summary(secrets, familles_euros, tarifs_speciaux, end_date, on_log)
    summary.update(
        {
            "families": result.get("families", 0),
            "lessons": result.get("lessons", 0),
            "notion_added": len(notion_families) if notion_families else 0,
        }
    )
    return summary


def _compute_summary(
    secrets: dict[str, Any],
    familles_euros: list[str],
    tarifs_speciaux: list[dict[str, Any]],
    extraction_end: date,
    on_log: Callable[[str], None],
) -> dict[str, Any]:
    """Read the freshly-saved data and compute multi-currency + net EUR.

    Mirrors the corrected page_accueil logic: ca_total_eur = EUR + CHF*rate + AED*rate
    (AED was missing before).
    """
    data_dir = get_data_dir()
    data_path = data_dir / "full_output_tb_SIMPLE.json"
    if not data_path.exists():
        on_log("⚠️ Pas de données extraites trouvées (full_output_tb_SIMPLE.json absent)")
        return {
            "amounts_by_currency": {},
            "ca_total_eur": 0.0,
            "profs_total_eur": 0.0,
            "net_eur": 0.0,
            "details_by_family": [],
        }

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from scripts.update_notion import normalize_name

    euro_parents = {normalize_name(n) for n in familles_euros}

    amounts_by_currency: dict[str, float] = {}
    details_by_family: list[dict[str, Any]] = []

    for fam_id, fam in data.items():
        parent = fam.get("parent_name") or fam.get("family_name") or ""
        is_euro = normalize_name(parent) in euro_parents
        per_family: dict[str, float] = {"EUR": 0.0, "CHF": 0.0, "AED": 0.0}

        for lesson in fam.get("lessons", []):
            if lesson.get("attendance_status") == "AbsentNotice":
                continue
            amount = float(lesson.get("amount") or 0)
            # Lesson currency — Notion lessons carry their own currency, TB lessons inherit family default
            if lesson.get("source") == "notion_hors_tb":
                cur = (lesson.get("notion_devise_client") or "EUR").upper()
            else:
                cur = (fam.get("currency") or "").upper()
                if not cur:
                    cur = "EUR" if is_euro else "CHF"
            if cur not in {"EUR", "CHF", "AED"}:
                cur = "EUR"
            per_family[cur] = per_family.get(cur, 0.0) + amount
            amounts_by_currency[cur] = amounts_by_currency.get(cur, 0.0) + amount

        details_by_family.append(
            {
                "family_id": fam_id,
                "parent_name": parent,
                "is_euro": is_euro,
                "EUR": round(per_family["EUR"], 2),
                "CHF": round(per_family["CHF"], 2),
                "AED": round(per_family["AED"], 2),
            }
        )

    # ── EUR equivalents: SAME calc as page_accueil after the bug fix ──
    ca_total_eur = float(amounts_by_currency.get("EUR", 0))
    chf_eur = aed_eur = None
    try:
        from scripts.recap_profs import fetch_chf_eur_rate, fetch_fx_rate

        if amounts_by_currency.get("CHF"):
            chf_eur, _ = fetch_chf_eur_rate()
            ca_total_eur += amounts_by_currency["CHF"] * chf_eur
        if amounts_by_currency.get("AED"):
            aed_eur, _ = fetch_fx_rate("AED", "EUR")
            ca_total_eur += amounts_by_currency["AED"] * aed_eur
    except Exception as exc:
        on_log(f"⚠️ Erreur conversion FX : {exc}")

    # ── Profs total EUR (réutilise compute_teacher_recap) ──
    profs_total_eur = 0.0
    try:
        from scripts.recap_profs import compute_teacher_recap

        recap = compute_teacher_recap(
            data,
            secrets,
            familles_euros,
            tarifs_speciaux,
            extraction_end_date=extraction_end,
        )
        profs_total_eur = float(recap.get("grand_total", 0))
    except Exception as exc:
        on_log(f"⚠️ Erreur calcul recap profs : {exc}")

    net_eur = ca_total_eur - profs_total_eur
    on_log(
        f"💰 Total : "
        f"{amounts_by_currency.get('EUR', 0):,.0f} € + "
        f"{amounts_by_currency.get('CHF', 0):,.0f} CHF + "
        f"{amounts_by_currency.get('AED', 0):,.0f} AED"
    )
    on_log(f"💶 Net EUR : {net_eur:,.0f} € (CA {ca_total_eur:,.0f} € − Profs {profs_total_eur:,.0f} €)")

    return {
        "amounts_by_currency": {k: round(v, 2) for k, v in amounts_by_currency.items() if v > 0.001},
        "ca_total_eur": round(ca_total_eur, 2),
        "profs_total_eur": round(profs_total_eur, 2),
        "net_eur": round(net_eur, 2),
        "fx": {
            "chf_eur": chf_eur,
            "aed_eur": aed_eur,
        },
        "details_by_family": sorted(details_by_family, key=lambda x: x["parent_name"]),
        "extraction_end": extraction_end.isoformat(),
    }


def get_last_summary() -> dict[str, Any] | None:
    """Return the cached summary file if present, else None."""
    summary_path = get_data_dir() / "last_extract_summary.json"
    if not summary_path.exists():
        return None
    with open(summary_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_summary(summary: dict[str, Any]) -> None:
    summary_path = get_data_dir() / "last_extract_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
