"""Dashboard data — summary cards, payments per folder, email history, quotes."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import requests

from app.services.paths import ensure_scripts_on_path, get_data_dir
from app.services.yaml_io import read_yaml

ensure_scripts_on_path()


# ── Summary (4 top metrics) ────────────────────────────────────────────

def summary() -> dict[str, Any]:
    """Reads the last extraction summary + config to produce the 4 cards."""
    secrets = read_yaml("secrets.yaml")
    teachers = secrets.get("teachers", {}) or {}

    # Profs count = teachers in secrets + unique Notion profs (not in secrets)
    notion_profs: set[str] = set()
    try:
        from app.services.notion import fetch_profs_hors_tb
        n = fetch_profs_hors_tb()
        if n.get("success"):
            for e in n.get("entries", []):
                p = (e.get("professeur") or "").strip()
                if p:
                    notion_profs.add(p)
    except Exception:
        pass
    teacher_set = {t.lower() for t in teachers.keys()}
    notion_only = {p for p in notion_profs if p.lower() not in teacher_set}
    nb_profs = len(teacher_set) + len(notion_only)

    # Latest extraction summary
    nb_families = 0
    amounts_by_currency: dict[str, float] = {}
    ca_total_eur = 0.0
    profs_total_eur = 0.0
    net_eur = 0.0
    extraction_end: str | None = None

    summary_path = get_data_dir() / "last_extract_summary.json"
    if summary_path.exists():
        s = json.loads(summary_path.read_text(encoding="utf-8"))
        nb_families = int(s.get("families", 0) or 0)
        amounts_by_currency = dict(s.get("amounts_by_currency") or {})
        ca_total_eur = float(s.get("ca_total_eur", 0) or 0)
        profs_total_eur = float(s.get("profs_total_eur", 0) or 0)
        net_eur = float(s.get("net_eur", 0) or 0)
        extraction_end = s.get("extraction_end")

    return {
        "nb_profs": nb_profs,
        "nb_profs_breakdown": {
            "tutorbird_or_secrets": len(teacher_set),
            "notion_only": len(notion_only),
        },
        "nb_families": nb_families,
        "amounts_by_currency": amounts_by_currency,
        "ca_total_eur": round(ca_total_eur, 2),
        "profs_total_eur": round(profs_total_eur, 2),
        "net_eur": round(net_eur, 2),
        "extraction_end": extraction_end,
    }


# ── Invoice folders ────────────────────────────────────────────────────

def list_invoice_folders() -> list[dict[str, Any]]:
    try:
        from scripts.storage_manager import list_invoice_folders as _list
        folders = _list() or []
    except Exception:
        folders = []
    out: list[dict[str, Any]] = []
    for f in folders:
        name = f.get("month") or f.get("name") or ""
        out.append({
            "id": name,  # use the month name as a stable ID
            "month": name,
            "year": f.get("year"),
            "source": f.get("source", "local"),
        })
    return out


# ── Payments per folder ────────────────────────────────────────────────

def _parse_folder_month(folder_name: str) -> str | None:
    """'Octobre 2025 - 28-10' → '2025-10'."""
    MONTHS_FR = {
        "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
    }
    if not folder_name:
        return None
    parts = folder_name.split(" - ")
    first = parts[0].strip()
    tokens = first.split()
    if len(tokens) < 2:
        return None
    month_word = tokens[0].lower()
    try:
        year = int(tokens[-1])
    except ValueError:
        return None
    m = MONTHS_FR.get(month_word)
    if not m:
        return None
    return f"{year:04d}-{m:02d}"


def payments_for_folder(folder: str) -> dict[str, Any]:
    """Reads Notion 'Paiements - Base Centrale' and counts paid vs unpaid
    invoices whose Invoice date is in the same month as the folder.
    """
    target_month = _parse_folder_month(folder)
    secrets = read_yaml("secrets.yaml")
    notion = secrets.get("notion", {}) or {}
    token = notion.get("token")
    db_id = notion.get("paiements_database_id")

    if not token or not db_id or not target_month:
        return {
            "folder": folder,
            "target_month": target_month,
            "total": 0,
            "paid": 0,
            "unpaid": 0,
            "pct": 0,
            "amounts_by_currency_paid": {},
            "amounts_by_currency_due": {},
            "error": "Notion config missing" if not (token and db_id) else "Folder month not parseable",
        }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    rows: list[dict] = []
    cursor: str | None = None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=headers, json=body, timeout=20,
        )
        if r.status_code != 200:
            return {"folder": folder, "error": f"Notion {r.status_code}: {r.text[:200]}"}
        payload = r.json()
        rows.extend(payload.get("results", []))
        if not payload.get("has_more"):
            break
        cursor = payload.get("next_cursor")

    total = paid = unpaid = 0
    amounts_paid: dict[str, float] = {}
    amounts_due: dict[str, float] = {}
    for row in rows:
        p = row.get("properties", {}) or {}
        inv_date = p.get("Invoice date", {}).get("date")
        row_month = inv_date["start"][:7] if inv_date and inv_date.get("start") else None
        if row_month != target_month:
            continue

        is_paid = bool(p.get("Payé ?", {}).get("checkbox", False))
        # Try several common amount/currency field names
        amount = 0.0
        currency = "CHF"
        for amt_key in ("Montant dû Famille", "Montant", "Montant client", "Montant facture"):
            v = p.get(amt_key, {})
            if v.get("number") is not None:
                amount = float(v["number"])
                break
        for cur_key in ("Devise", "Currency"):
            v = p.get(cur_key, {})
            sel = v.get("select") or v.get("status")
            if sel and sel.get("name"):
                currency = sel["name"].upper()
                break

        total += 1
        if is_paid:
            paid += 1
            amounts_paid[currency] = amounts_paid.get(currency, 0.0) + amount
        else:
            unpaid += 1
        amounts_due[currency] = amounts_due.get(currency, 0.0) + amount

    pct = int(round(paid / total * 100)) if total else 0
    return {
        "folder": folder,
        "target_month": target_month,
        "total": total,
        "paid": paid,
        "unpaid": unpaid,
        "pct": pct,
        "amounts_by_currency_paid": {k: round(v, 2) for k, v in amounts_paid.items()},
        "amounts_by_currency_due": {k: round(v, 2) for k, v in amounts_due.items()},
    }


# ── Email history (from Notion metadata DB) ────────────────────────────

def email_history() -> dict[str, Any]:
    secrets = read_yaml("secrets.yaml")
    notion = secrets.get("notion", {}) or {}
    token = notion.get("token")
    md_id = notion.get("metadata_database_id")
    if not token or not md_id:
        return {"invoice_sent_date": None, "reminder_sent_date": None, "reminder_count": 0}

    try:
        r = requests.post(
            f"https://api.notion.com/v1/databases/{md_id}/query",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            },
            json={},
            timeout=10,
        )
        if r.status_code != 200:
            return {"invoice_sent_date": None, "reminder_sent_date": None, "reminder_count": 0,
                    "error": f"Notion {r.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"invoice_sent_date": None, "reminder_sent_date": None, "reminder_count": 0,
                "error": str(exc)}

    invoice_sent: str | None = None
    reminder_sent: str | None = None
    reminder_count = 0
    for row in r.json().get("results", []):
        p = row.get("properties", {}) or {}
        cle = p.get("Clé", {}).get("title", [])
        key = cle[0].get("plain_text", "").strip() if cle else ""
        d = p.get("Invoice date mail", {}).get("date")
        date_str = d["start"][:10] if d and d.get("start") else None
        val = p.get("Valeur", {}).get("number")
        if key == "last_invoice_sent_date" and date_str:
            invoice_sent = date_str
        elif key == "last_reminder_sent_date":
            if date_str:
                reminder_sent = date_str
            if val:
                reminder_count = int(val)

    return {
        "invoice_sent_date": invoice_sent,
        "reminder_sent_date": reminder_sent,
        "reminder_count": reminder_count,
    }


# ── Quotes ──────────────────────────────────────────────────────────────

def random_quotes() -> dict[str, Any]:
    from scripts.quotes_data import get_random_hadith, get_random_life_quote
    hadith = get_random_hadith()
    quote = get_random_life_quote()
    # quote is a tuple (text, author) per quotes_data.py
    if isinstance(quote, tuple):
        quote = {"text": quote[0], "author": quote[1]}
    return {"hadith": hadith, "quote": quote}
