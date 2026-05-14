"""Invoice editor — load an existing PDF, edit fields, re-render PDF, then
download / send by email / re-upload to Drive. Mirrors page_edit_invoice in
the Streamlit app.
"""
from __future__ import annotations

import base64
import io
import json
import os
import smtplib
import tempfile
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from app.services.config import load_secrets
from app.services.paths import PROJECT_ROOT, ensure_scripts_on_path, get_data_dir

ensure_scripts_on_path()


# ── Helpers ────────────────────────────────────────────────────────────


def _find_fam_id_for_folder(data: dict[str, Any], folder_name: str) -> str | None:
    norm = (folder_name or "").lower().replace("_", " ").strip()
    for fid, fam in data.items():
        pn = (fam.get("parent_name") or "").lower().strip()
        if pn and (pn == norm or pn in norm or norm in pn):
            return fid
    return None


def _logo_path() -> str | None:
    for c in (PROJECT_ROOT / "assets" / "logo.png", PROJECT_ROOT / "logo.png"):
        if c.exists():
            return str(c)
    return None


def _load_extracted_data() -> dict[str, Any]:
    p = get_data_dir() / "full_output_tb_SIMPLE.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _find_folder(folder_name: str) -> dict[str, Any] | None:
    """Find a folder dict (local + Drive) by month name."""
    from app.services.dashboard import list_invoice_folders
    for f in list_invoice_folders():
        if f.get("month") == folder_name:
            return f
    return None


def _ensure_folder_local(folder_name: str) -> Path | None:
    """Make sure the folder is downloaded locally. Returns its local path."""
    f = _find_folder(folder_name)
    if not f:
        return None

    # Try to find an existing local path via the legacy function
    try:
        from scripts.storage_manager import list_invoice_folders as _list_legacy
        for ff in _list_legacy() or []:
            if (ff.get("month") == folder_name) and ff.get("path") and Path(ff["path"]).exists():
                return Path(ff["path"])
    except Exception:
        pass

    # Download from Drive
    try:
        from scripts.storage_manager import load_invoice_folder
        year = f.get("year") or ""
        res = load_invoice_folder(year, folder_name)
        if res.get("success") and res.get("local_path"):
            return Path(res["local_path"])
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ Drive download for {folder_name}: {exc}")
    return None


# ── Public API ─────────────────────────────────────────────────────────


def list_families(folder_name: str) -> dict[str, Any]:
    folder_path = _ensure_folder_local(folder_name)
    if not folder_path or not folder_path.exists():
        return {"folder": folder_name, "downloaded": False, "families": []}
    fams = sorted([d.name for d in folder_path.iterdir() if d.is_dir()])
    return {"folder": folder_name, "downloaded": True, "local_path": str(folder_path), "families": fams}


def list_pdfs(folder_name: str, family: str) -> list[str]:
    folder_path = _ensure_folder_local(folder_name)
    if not folder_path:
        return []
    fam_path = folder_path / family
    if not fam_path.exists():
        return []
    return sorted([p.name for p in fam_path.iterdir() if p.suffix.lower() == ".pdf"])


def load_invoice(folder_name: str, family: str, pdf_filename: str) -> dict[str, Any]:
    """Return raw PDF (base64) + prefilled editor fields."""
    folder_path = _ensure_folder_local(folder_name)
    if not folder_path:
        raise FileNotFoundError(f"Folder {folder_name!r} not available")

    pdf_path = folder_path / family / pdf_filename
    if not pdf_path.exists():
        raise FileNotFoundError(f"{pdf_filename} not in {family}")
    raw_bytes = pdf_path.read_bytes()

    data = _load_extracted_data()
    fam_id = _find_fam_id_for_folder(data, family)
    fam = data.get(fam_id, {}) if fam_id else {}

    items = []
    for L in fam.get("lessons", []):
        if L.get("attendance_status") == "AbsentNotice":
            continue
        items.append({
            "date": L.get("date", ""),
            "description": f"Cours avec {L.get('teacher', '?')} pour {L.get('student', '?')} ({L.get('duration_min', '?')} min)",
            "amount": float(L.get("amount", 0) or 0),
        })

    pay_link = ""
    try:
        pl = get_data_dir() / "payment_links_output.json"
        if pl.exists():
            for p in json.loads(pl.read_text(encoding="utf-8")):
                if p.get("family_id") == fam_id:
                    pay_link = p.get("payment_link") or ""
                    break
    except Exception:
        pass

    parent_name = fam.get("parent_name") or family.replace("_", " ")
    is_carole = "carole" in parent_name.lower() and "tessier" in parent_name.lower()

    folder = _find_folder(folder_name)
    return {
        "raw_pdf_base64": base64.b64encode(raw_bytes).decode(),
        "fields": {
            "parent_name": parent_name,
            "billing_address": (
                "OCTOPUS SARL\nC/o CATS BUSINESS CENTER\n28 bd Princesse Charlotte\n98 000 MONACO"
                if is_carole else ""
            ),
            "parent_email": fam.get("parent_email") or fam.get("email_client") or "",
            "invoice_date": datetime.today().date().isoformat(),
            "invoice_number": "",
            "currency": (fam.get("currency") or "EUR").upper(),
            "items": items or [{"date": "", "description": "", "amount": 0.0}],
            "package_mode": is_carole,
            "package_label": "1 Package FORMATION Anglais",
            "total_due": sum(i["amount"] for i in items),
            "pay_link_url": pay_link,
            "_origin_drive_folder_id": folder.get("drive_id") if folder else None,
            "_origin_family_subfolder": family,
            "_origin_pdf_filename": pdf_filename,
        },
    }


def empty_fields() -> dict[str, Any]:
    return {
        "parent_name": "",
        "billing_address": "",
        "parent_email": "",
        "invoice_date": datetime.today().date().isoformat(),
        "invoice_number": "",
        "currency": "EUR",
        "items": [{"date": "", "description": "", "amount": 0.0}],
        "package_mode": False,
        "package_label": "1 Package FORMATION Anglais",
        "total_due": 0.0,
        "pay_link_url": "",
    }


def render_pdf(fields: dict[str, Any]) -> bytes:
    """Build a PDF from the edited fields using the legacy _build_invoice_pdf."""
    from scripts.generate_invoices import _build_invoice_pdf

    items_for_pdf = []
    for r in fields.get("items") or []:
        d = datetime.min
        if r.get("date"):
            try:
                d = datetime.strptime(r["date"], "%d.%m.%Y")
            except Exception:
                pass
        items_for_pdf.append({
            "date": d,
            "description": r.get("description", ""),
            "amount": float(r.get("amount", 0) or 0),
        })

    currency = (fields.get("currency") or "EUR").upper()
    total_due = float(fields.get("total_due", 0) or 0)
    invoice_date_str = fields.get("invoice_date") or datetime.today().date().isoformat()
    invoice_date = datetime.fromisoformat(invoice_date_str)

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "edited.pdf")
        counter_root = os.path.join(tmp, "ctr")
        _build_invoice_pdf(
            output_path=out,
            items=items_for_pdf,
            total_due_display=f"{total_due:.2f} {currency}",
            pay_link_url=(fields.get("pay_link_url") or "https://example.com"),
            parent_name=(fields.get("parent_name") or "Parent"),
            logo_path=_logo_path(),
            counter_root=counter_root,
            today=invoice_date,
            is_notion_custom=bool(fields.get("package_mode", False)),
            custom_billing_address=(fields.get("billing_address") or None),
            invoice_number_override=(fields.get("invoice_number") or None),
            custom_package_label=(fields.get("package_label") if fields.get("package_mode") else None),
        )
        return Path(out).read_bytes()


def send_pdf_email(*, fields: dict[str, Any], pdf_bytes: bytes) -> dict[str, Any]:
    secrets = load_secrets()
    gmail = secrets.get("gmail", {}) or {}
    sender = gmail.get("email")
    pwd = gmail.get("app_password")
    if not sender or not pwd:
        raise RuntimeError("Gmail config manquante (email/app_password).")
    recipient = (fields.get("parent_email") or "").strip()
    if not recipient:
        raise RuntimeError("Email du destinataire vide.")

    safe = (fields.get("parent_name") or "facture").replace(" ", "_")
    date_str = (fields.get("invoice_date") or datetime.today().date().isoformat())[:10]
    filename = f"Facture_{date_str}_{safe}.pdf"

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"Facture - {fields.get('parent_name', '')}".strip(" -")
    msg.attach(MIMEText(
        "Bonjour,\n\nVeuillez trouver ci-joint la facture éditée.\n\nCordialement.",
        "plain", "utf-8",
    ))
    part = MIMEBase("application", "pdf")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={filename}")
    msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls()
        s.login(sender, pwd)
        s.sendmail(sender, recipient, msg.as_string())
    return {"sent_to": recipient, "filename": filename}


def save_to_drive(*, pdf_bytes: bytes, origin_drive_folder_id: str, family_subfolder: str,
                  pdf_filename: str) -> dict[str, Any]:
    """Upload the edited PDF back to Drive, overwriting if a file with the
    same name exists in the family subfolder (we never *create* in user Drive
    if a service account is in use — limitation noted in MIGRATION_SPEC §5)."""
    from scripts.google_drive import get_drive_service, find_or_create_folder, upload_file
    service = get_drive_service()
    if not service:
        raise RuntimeError("Drive non configuré")

    fam_folder_id = find_or_create_folder(service, family_subfolder, origin_drive_folder_id)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        res = upload_file(service, tmp_path, pdf_filename, fam_folder_id)
        return {"ok": True, "drive_file_id": res.get("id"), "name": res.get("name")}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
