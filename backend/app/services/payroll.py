"""Teachers payroll — recap_profs + generate_prof_pdfs."""
from __future__ import annotations

import json
import zipfile
import io
from datetime import date
from typing import Any

from app.services.config import load_familles_euros, load_secrets, load_tarifs_speciaux
from app.services.paths import PROJECT_ROOT, ensure_scripts_on_path, get_data_dir

ensure_scripts_on_path()


def _load_data() -> dict[str, Any]:
    p = get_data_dir() / "full_output_tb_SIMPLE.json"
    if not p.exists():
        raise RuntimeError("Pas de données extraites.")
    return json.loads(p.read_text(encoding="utf-8"))


def _logo_path() -> str | None:
    for c in (PROJECT_ROOT / "assets" / "logo.png", PROJECT_ROOT / "logo.png"):
        if c.exists():
            return str(c)
    return None


def _extraction_end() -> date | None:
    p = get_data_dir() / "last_extract_summary.json"
    if not p.exists():
        return None
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        return date.fromisoformat(s.get("extraction_end") or "")
    except Exception:
        return None


def _zero_hour_notion_profs() -> set[str]:
    """Profs listed with 0h in Notion 'Profs hors TutorBird' — they must be
    excluded from the recap (mirrors page_accueil's _get_zero_hour_notion_profs
    in pages/__init__.py, but works in our non-Streamlit context).
    """
    excluded: set[str] = set()
    try:
        from app.services.notion import fetch_profs_hors_tb
        r = fetch_profs_hors_tb()
        if r.get("success"):
            for e in r.get("entries", []) or []:
                if float(e.get("heures_faites") or 0) <= 0:
                    prof = (e.get("professeur") or "").strip()
                    if prof:
                        excluded.add(prof)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ zero-hour Notion profs lookup: {exc}")
    return excluded


def summary(*, auto_chf_target: float | None = None) -> dict[str, Any]:
    """Compute the prof payroll recap. Excludes profs with 0h in Notion
    (consistency with page_accueil + extract summary)."""
    from scripts.recap_profs import compute_teacher_recap

    data = _load_data()
    secrets = load_secrets()
    fe = load_familles_euros()
    ts = load_tarifs_speciaux()

    excluded = _zero_hour_notion_profs()

    recap = compute_teacher_recap(
        data, secrets, fe, ts,
        extraction_end_date=_extraction_end(),
        excluded_teacher_names=excluded,
    )

    teachers = []
    for name, d in sorted(recap.get("teachers", {}).items()):
        d = d or {}
        teachers.append({
            "name": name,
            "nb_lessons": d.get("nb_lessons", 0),
            "total_hours": round(float(d.get("total_hours", 0) or 0), 2),
            "eur": round(float(d.get("eur", 0) or 0), 2),
            "chf_as_eur": round(float(d.get("chf_as_eur", 0) or 0), 2),
            "total_eur": round(float(d.get("eur", 0) or 0) + float(d.get("chf_as_eur", 0) or 0), 2),
            "details": d.get("details", []),
        })

    return {
        "teachers": teachers,
        "grand_total": float(recap.get("grand_total", 0) or 0),
        "total_lessons": int(recap.get("total_lessons", 0) or 0),
        "fx": recap.get("fx") or {},
    }


def pdf_for_teacher(teacher_name: str, *, mois_label: str | None = None) -> bytes:
    from scripts.generate_prof_pdfs import generate_single_pdf_to_bytes
    return generate_single_pdf_to_bytes(
        teacher_name, _load_data(), mois_label or "Période en cours",
        logo_path=_logo_path(), extraction_end_date=_extraction_end(),
    )


def zip_all_pdfs(*, mois_label: str | None = None) -> bytes:
    from scripts.generate_prof_pdfs import generate_all_pdfs_as_zip
    summary_data = summary()
    teacher_recaps = {t["name"]: {"eur": t["eur"], "chf_as_eur": t["chf_as_eur"],
                                  "nb_lessons": t["nb_lessons"], "total_hours": t["total_hours"],
                                  "details": t["details"]}
                      for t in summary_data["teachers"]}
    return generate_all_pdfs_as_zip(
        teacher_recaps, mois_label or "Période en cours",
        logo_path=_logo_path(), extraction_end_date=_extraction_end(),
    )


def combined_pdf(*, mois_label: str | None = None) -> bytes:
    from scripts.generate_prof_pdfs import generate_all_pdfs_to_bytes
    summary_data = summary()
    teacher_recaps = {t["name"]: {"eur": t["eur"], "chf_as_eur": t["chf_as_eur"],
                                  "nb_lessons": t["nb_lessons"], "total_hours": t["total_hours"],
                                  "details": t["details"]}
                      for t in summary_data["teachers"]}
    return generate_all_pdfs_to_bytes(
        teacher_recaps, mois_label or "Période en cours",
        logo_path=_logo_path(), extraction_end_date=_extraction_end(),
    )
