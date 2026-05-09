"""Notion service — wraps `scripts/fetch_notion_profs`."""
from __future__ import annotations

from typing import Any

from app.services.config import load_secrets
from app.services.paths import ensure_scripts_on_path

ensure_scripts_on_path()


def fetch_profs_hors_tb() -> dict[str, Any]:
    """List all 'Profs hors TutorBird' entries from Notion.

    Returns the same shape as the script: {success, entries[], error}.
    Each entry has: famille, professeur, eleve, devise_client,
    taux_horaire_client, taux_horaire_prof, devise_prof, heures_faites,
    email_client, email_prof, language, page_id, ...
    """
    from scripts.fetch_notion_profs import fetch_notion_profs

    secrets = load_secrets()
    if not secrets:
        return {"success": False, "entries": [], "error": "secrets.yaml introuvable"}
    return fetch_notion_profs(secrets)


def convert_profs_to_families(
    entries: list[dict[str, Any]],
    selected_page_ids: list[str] | None = None,
) -> dict[str, Any]:
    from scripts.fetch_notion_profs import convert_notion_profs_to_families

    selected = entries
    if selected_page_ids is not None:
        selected = [e for e in entries if e.get("page_id") in selected_page_ids]
    return convert_notion_profs_to_families(selected)
