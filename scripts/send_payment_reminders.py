"""
🔔 Send Payment Reminders
Envoie des rappels de paiement aux familles n'ayant pas encore payé.
Rapproche Notion avec le dossier de factures courant.
"""

import os
import re
import smtplib
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


MONTHS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
]


def normalize(s):
    """Normalise un nom : minuscules, sans accents, espaces propres."""
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("-", " ")
    s = s.replace("_", " ")
    s = s.replace("&", " ")
    s = re.sub(r"\s+", " ", s)
    if "," in s:
        p = [x.strip() for x in s.split(",", 1)]
        if len(p) == 2:
            s = f"{p[1]} {p[0]}"
    return s.strip()


def _names_match(a, b):
    na = normalize(a)
    nb = normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    wa = set(na.split())
    wb = set(nb.split())
    common = wa & wb
    if len(common) >= max(1, min(2, len(wa), len(wb))):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.82


def _collect_pdfs_recursively(invoice_folder):
    pdf_files = []
    if not invoice_folder or not os.path.exists(invoice_folder):
        return pdf_files
    for root, _, files in os.walk(invoice_folder):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(root, f))
    return pdf_files


def _match_family_invoices(parent_name, pdf_paths):
    target = normalize(parent_name)
    target_words = {w for w in target.split() if len(w) >= 2}
    matched = []
    for path in pdf_paths:
        hay = normalize(os.path.basename(path) + " " + os.path.basename(os.path.dirname(path)))
        hay_words = set(hay.split())
        if target and (target in hay or hay in target):
            matched.append(path)
            continue
        if target_words and len(target_words & hay_words) >= max(1, min(2, len(target_words))):
            matched.append(path)
            continue
        if SequenceMatcher(None, target, hay).ratio() >= 0.72:
            matched.append(path)
    return matched


def _extract_folder_invoice_date(invoice_folder):
    label = os.path.basename(str(invoice_folder or ""))
    m = re.search(r"(\d{2})[-_/](\d{2})[-_/](\d{4})", label)
    if not m:
        return None
    day, month, year = m.groups()
    return f"{year}-{month}-{day}"


def _safe_title(props, name):
    prop = props.get(name, {})
    items = prop.get("title", [])
    if items:
        return items[0].get("plain_text", "").strip()
    return ""


def _safe_rich_text(props, name):
    prop = props.get(name, {})
    items = prop.get("rich_text", [])
    if items:
        return items[0].get("plain_text", "").strip()
    return ""


def _safe_email(props, name):
    prop = props.get(name, {})
    email = prop.get("email")
    if email:
        return str(email).strip()
    return _safe_rich_text(props, name)


def _safe_number(props, *names):
    for name in names:
        prop = props.get(name, {})
        number = prop.get("number")
        if number is not None:
            return float(number)
    return 0.0


def _safe_checkbox(props, *names):
    for name in names:
        prop = props.get(name, {})
        if "checkbox" in prop:
            return bool(prop.get("checkbox", False))
    return False


def _safe_date(props, name):
    prop = props.get(name, {})
    date_prop = prop.get("date")
    if isinstance(date_prop, dict):
        return date_prop.get("start")
    return None


def _find_email_from_family_data(parent_name, family_data):
    if not isinstance(family_data, dict):
        return ""

    target = normalize(parent_name)
    target_words = set(target.split())
    best_email = ""
    best_score = 0.0

    for fam in family_data.values():
        fam_name = fam.get("parent_name") or fam.get("family_name") or ""
        fam_email = fam.get("parent_email") or fam.get("email_client") or ""
        if not fam_name or not fam_email:
            continue
        fam_norm = normalize(fam_name)
        if fam_norm == target:
            return fam_email
        fam_words = set(fam_norm.split())
        overlap = len(target_words & fam_words)
        score = SequenceMatcher(None, target, fam_norm).ratio()
        if overlap >= max(1, min(2, len(target_words), len(fam_words))) and score >= 0.55:
            return fam_email
        if score > best_score:
            best_score = score
            best_email = fam_email

    return best_email if best_score >= 0.86 else ""


def get_default_reminder_template(month_name=None, year=None):
    """Retourne le template d'email de rappel par défaut."""
    if not month_name:
        now = datetime.now()
        month_name = MONTHS_FR[now.month - 1]
        year = now.year

    return {
        "subject": f"Rappel - Facture(s) en attente - Soutien scolaire - {month_name} {year}",
        "body": f"""Bonjour,

J'espère que vous allez bien.

Je me permets de vous relancer concernant la/les facture(s) de soutien scolaire du mois de {month_name} {year} qui reste(nt) en attente de règlement.

Vous trouverez ci-joint la/les facture(s) correspondante(s). Vous pouvez régler directement en cliquant sur le bouton \"Payer en ligne\" dans le PDF.

Merci de procéder au paiement dès que possible.

N'hésitez pas à me contacter si vous avez des questions ou si vous avez déjà effectué le paiement.

Cordialement,
Professor+
"""
    }


def get_unpaid_families_from_notion(secrets, callback=None, invoice_folder=None, family_data=None):
    """
    Récupère les familles non payées depuis Notion et, si demandé,
    les rapproche avec le dossier de factures courant.
    """

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        NOTION_TOKEN = secrets["notion"]["token"]
        DB_PAIEMENTS = secrets["notion"]["paiements_database_id"]

        HEADERS = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

        def notion_request(method, endpoint, json_data=None):
            time.sleep(0.25)
            url = f"https://api.notion.com/v1/{endpoint}"
            if method == "POST":
                r = requests.post(url, headers=HEADERS, json=json_data, timeout=30)
            elif method == "GET":
                r = requests.get(url, headers=HEADERS, timeout=30)
            else:
                return None

            if r.status_code == 429:
                retry = int(r.headers.get("Retry-After", 2))
                time.sleep(retry)
                return notion_request(method, endpoint, json_data)

            if r.status_code in (200, 201):
                return r.json() if r.text else {"ok": True}
            return None

        update(5, "📥 Chargement des lignes Notion...")

        all_rows = []
        cursor = None
        while True:
            payload = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor
            data = notion_request("POST", f"databases/{DB_PAIEMENTS}/query", payload)
            if not data:
                break
            all_rows.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        update(35, f"📊 {len(all_rows)} ligne(s) Notion chargée(s)")

        pdf_paths = _collect_pdfs_recursively(invoice_folder) if invoice_folder else []
        folder_invoice_date = _extract_folder_invoice_date(invoice_folder) if invoice_folder else None

        unpaid_by_family = {}
        for row in all_rows:
            props = row.get("properties", {})
            if _safe_checkbox(props, "Payé ?", "Payé"):
                continue

            famille = _safe_title(props, "Famille") or _safe_rich_text(props, "Famille")
            if not famille:
                continue

            date_cours = _safe_date(props, "Date cours factures")
            invoice_matches = _match_family_invoices(famille, pdf_paths) if pdf_paths else []
            if invoice_folder and not invoice_matches:
                continue

            email = _safe_email(props, "Email parent")
            if not email:
                email = _find_email_from_family_data(famille, family_data or {})

            amount = _safe_number(props, "Montant total dû", "Montant dû Famille/Prof")
            currency = _safe_rich_text(props, "Devise") or "CHF"
            key = normalize(famille)

            entry = unpaid_by_family.setdefault(key, {
                "parent_name": famille,
                "parent_email": email,
                "amount": 0.0,
                "date": date_cours,
                "currency": currency,
                "page_ids": [],
                "invoice_paths": [],
            })
            entry["amount"] += amount
            if email and not entry.get("parent_email"):
                entry["parent_email"] = email
            if date_cours and not entry.get("date"):
                entry["date"] = date_cours
            if currency and not entry.get("currency"):
                entry["currency"] = currency
            entry["page_ids"].append(row.get("id"))
            for path in invoice_matches:
                if path not in entry["invoice_paths"]:
                    entry["invoice_paths"].append(path)

        unpaid = sorted(unpaid_by_family.values(), key=lambda x: normalize(x["parent_name"]))

        update(100, f"✅ {len(unpaid)} famille(s) impayée(s) rapprochée(s)")
        return {"success": True, "unpaid": unpaid}

    except Exception as e:
        return {"success": False, "error": str(e)}


def run_send_reminders(secrets, data, invoice_folder, data_dir,
                       custom_subject=None, custom_body=None,
                       selected_families=None, send_to_test=False,
                       callback=None):
    """Envoie des rappels de paiement aux familles n'ayant pas payé."""

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        gmail_config = secrets.get("gmail", {})
        sender_email = gmail_config.get("email")
        app_password = gmail_config.get("app_password")

        if not sender_email or not app_password:
            return {"success": False, "error": "Configuration email manquante dans secrets.yaml"}

        update(5, "📥 Récupération des impayés depuis Notion...")
        result = get_unpaid_families_from_notion(
            secrets,
            callback=callback,
            invoice_folder=invoice_folder or None,
            family_data=data or {},
        )
        if not result["success"]:
            return result

        unpaid_families = result["unpaid"]
        if not unpaid_families:
            return {"success": True, "sent": 0, "total": 0, "errors": [], "message": "Aucune famille avec paiement en attente"}

        if selected_families:
            unpaid_families = [f for f in unpaid_families if f["parent_name"] in selected_families]

        update(20, f"📊 {len(unpaid_families)} famille(s) à relancer")

        template = get_default_reminder_template()
        subject = custom_subject or template["subject"]
        body = custom_body or template["body"]

        update(30, "🔌 Connexion au serveur email...")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)

        sent = 0
        errors = []
        total = len(unpaid_families)

        for i, family in enumerate(unpaid_families):
            progress = int(30 + (i / max(total, 1) * 65))
            recipient = sender_email if send_to_test else family.get("parent_email")
            if not recipient:
                errors.append(f"{family['parent_name']}: email manquant")
                continue

            update(progress, f"📧 Rappel à {family['parent_name']}...")

            try:
                msg = MIMEMultipart()
                msg["From"] = sender_email
                msg["To"] = recipient
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))

                attached_count = 0
                invoice_paths = family.get("invoice_paths") or []

                if not invoice_paths and os.path.exists(invoice_folder):
                    invoice_paths = _match_family_invoices(family["parent_name"], _collect_pdfs_recursively(invoice_folder))

                for invoice_path in invoice_paths:
                    if not os.path.exists(invoice_path):
                        continue
                    filename = os.path.basename(invoice_path)
                    with open(invoice_path, "rb") as f:
                        part = MIMEBase("application", "pdf")
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", f"attachment; filename={filename}")
                        msg.attach(part)
                        attached_count += 1

                server.sendmail(sender_email, recipient, msg.as_string())
                sent += 1

            except Exception as e:
                errors.append(f"{family['parent_name']}: {str(e)}")

        server.quit()
        update(100, "✅ Terminé !")

        return {
            "success": True,
            "sent": sent,
            "total": total,
            "errors": errors,
            "test_mode": send_to_test,
        }

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "Erreur d'authentification Gmail"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def should_send_automatic_reminder():
    """Vérifie si on est le 11 du mois (pour rappel automatique)."""
    return datetime.now().day == 11


def get_reminder_settings_path(config_dir):
    """Retourne le chemin du fichier de paramètres des rappels."""
    return os.path.join(config_dir, "reminder_settings.yaml")
