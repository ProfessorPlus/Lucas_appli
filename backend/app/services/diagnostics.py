"""Settings page diagnostics — the alerts I promised to add after the
Imane Berrai / Calabresi incidents (see MEMORY).

- config_sync: compares each YAML in Drive vs local
- phantom_teachers: teachers with TutorBird lessons but 0h in Notion override
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.paths import PROJECT_ROOT, get_data_dir
from app.services.yaml_io import diff_yaml_against_drive, get_drive_diagnostics

CONFIG_FILES = ("secrets.yaml", "familles_euros.yaml", "tarifs_speciaux.yaml")


def config_sync_report() -> dict[str, Any]:
    """Return per-file desync status + a summary boolean."""
    results = {}
    any_diverged = False
    for f in CONFIG_FILES:
        meta = get_drive_diagnostics(f)
        try:
            diff = diff_yaml_against_drive(f)
        except Exception as exc:  # noqa: BLE001
            diff = {"status": "error", "error": str(exc)}
        if diff.get("status") not in {"in_sync", "missing_both"}:
            any_diverged = True
        results[f] = {**meta, "diff": diff}
    return {"all_in_sync": not any_diverged, "files": results}


def phantom_teachers_report() -> dict[str, Any]:
    """A 'phantom teacher' is one who appears as the `teacher` of TutorBird
    lessons in the latest extracted data but is NOT listed in Notion
    'Profs hors TutorBird'. This is the exact pattern that caused 78h of
    fake Imane lessons in May 2026.

    Reads the last extraction (data/full_output_tb_SIMPLE.json) and the
    Notion entries to compare.
    """
    data_path = get_data_dir() / "full_output_tb_SIMPLE.json"
    if not data_path.exists():
        return {"alerts": [], "note": "no extraction yet — phantom check skipped"}

    data = json.loads(data_path.read_text(encoding="utf-8"))

    # Collect teacher → (lesson count, hours) from TB lessons
    tb_teachers: dict[str, dict[str, Any]] = {}
    for fam_id, fam in data.items():
        for L in fam.get("lessons", []):
            if L.get("source") == "notion_hors_tb":
                continue  # only TB-native lessons
            if L.get("attendance_status") == "AbsentNotice":
                continue
            t = (L.get("teacher") or "").strip()
            if not t:
                continue
            entry = tb_teachers.setdefault(t, {"families": set(), "lessons": 0, "hours": 0.0, "unrecorded": 0})
            entry["families"].add(fam.get("parent_name") or fam_id)
            entry["lessons"] += 1
            entry["hours"] += (L.get("duration_min") or 0) / 60.0
            if L.get("attendance_status") == "Unrecorded":
                entry["unrecorded"] += 1

    # Pull Notion entries to know who's "registered" with hours.
    try:
        from app.services.notion import fetch_profs_hors_tb
        notion_res = fetch_profs_hors_tb()
        notion_entries = notion_res.get("entries", []) if notion_res.get("success") else []
    except Exception:
        notion_entries = []
    notion_profs_with_hours = {
        (e.get("professeur") or "").strip()
        for e in notion_entries
        if (e.get("heures_faites") or 0) > 0
    }
    notion_profs_zero = {
        (e.get("professeur") or "").strip()
        for e in notion_entries
        if (e.get("heures_faites") or 0) == 0
    }

    alerts: list[dict[str, Any]] = []
    for t, info in tb_teachers.items():
        if info["unrecorded"] >= 5 and t in notion_profs_zero:
            alerts.append(
                {
                    "severity": "high",
                    "teacher": t,
                    "tb_lessons": info["lessons"],
                    "tb_hours": round(info["hours"], 1),
                    "tb_unrecorded": info["unrecorded"],
                    "families": sorted(info["families"]),
                    "note": (
                        f"{t} a 0h dans Notion mais {info['unrecorded']} leçons "
                        f"TB 'Unrecorded' (= {round(info['hours'], 1)} h). "
                        f"Vérifier que ce prof est bien désactivé côté TutorBird."
                    ),
                }
            )
    return {"alerts": alerts, "tb_teacher_count": len(tb_teachers)}
