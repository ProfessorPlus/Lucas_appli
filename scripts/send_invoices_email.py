"""
📧 Send Invoices Email
Envoie les factures par email aux familles
"""

import os
import re
import smtplib
import unicodedata
from difflib import SequenceMatcher
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime


MONTHS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def _normalize_text(s):
    if not isinstance(s, str):
        return ""
    s = s.strip().lower().replace("_", " ")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    if "," in s:
        p = [x.strip() for x in s.split(",", 1)]
        if len(p) == 2:
            s = f"{p[1]} {p[0]}".strip()
    return s.strip()


def _clean_folder_name(s):
    if not isinstance(s, str):
        return ""
    return re.sub(r"[^a-zA-Z0-9_\- ]", "", s).strip().replace(" ", "_")


def _collect_pdf_paths(invoice_folder):
    pdf_paths = []
    if not invoice_folder or not os.path.exists(invoice_folder):
        return pdf_paths
    for root, _, files in os.walk(invoice_folder):
        for filename in files:
            if filename.lower().endswith(".pdf"):
                pdf_paths.append(os.path.join(root, filename))
    pdf_paths.sort()
    return pdf_paths


def get_default_email_template(month_name=None, year=None):
    """Retourne le template d'email par défaut."""

    if not month_name:
        now = datetime.now()
        month_name = MONTHS_FR[now.month - 1]
        year = now.year

    return {
        "subject": f"Facture(s) - Soutien scolaire - {month_name} {year}",
        "body": f"""Bonjour,

J'espère que vous allez bien.

Veuillez trouver ci-joint votre/vos facture(s) pour les cours de soutien scolaire du mois de {month_name} {year}.

Vous pouvez régler directement en cliquant sur le bouton "Payer en ligne" dans la facture PDF.

Merci de procéder au paiement dans les plus brefs délais, avant le 10 {month_name} {year}.

Cordialement,
Professor+
"""
    }


def get_families_from_folder(invoice_folder, data):
    """
    Récupère la liste des familles avec leurs factures.

    Returns:
        list: [{"family_id": str, "parent_name": str, "parent_email": str, "invoices": [paths], ...}]
    """
    families = []
    pdf_paths = _collect_pdf_paths(invoice_folder)
    if not pdf_paths:
        return families

    # Groupe les PDF par sous-dossier famille
    pdfs_by_folder = {}
    for path in pdf_paths:
        rel_parent = os.path.relpath(os.path.dirname(path), invoice_folder)
        folder_key = rel_parent if rel_parent != "." else ""
        pdfs_by_folder.setdefault(folder_key, []).append(path)

    for fam_id, fam in data.items():
        parent_name = fam.get("parent_name") or fam.get("family_name") or ""
        parent_email = fam.get("parent_email") or ""
        if not parent_email:
            continue

        expected_folder = _clean_folder_name(parent_name)
        norm_parent = _normalize_text(parent_name)
        invoices = []

        # 1) Match exact sur le dossier attendu
        if expected_folder in pdfs_by_folder:
            invoices.extend(pdfs_by_folder[expected_folder])

        # 2) Match souple sur les dossiers (accents/espaces/ordre)
        if not invoices:
            for folder_name, files in pdfs_by_folder.items():
                folder_norm = _normalize_text(folder_name)
                if not folder_norm:
                    continue
                if folder_norm == norm_parent:
                    invoices.extend(files)
                    continue
                ratio = SequenceMatcher(None, folder_norm, norm_parent).ratio()
                if ratio >= 0.82:
                    invoices.extend(files)

        # 3) Fallback sur le nom des PDF
        if not invoices:
            name_parts = [p for p in _normalize_text(parent_name).split() if len(p) > 2]
            for pdf_path in pdf_paths:
                filename_norm = _normalize_text(os.path.basename(pdf_path))
                if name_parts and any(part in filename_norm for part in name_parts):
                    invoices.append(pdf_path)

        # Nettoyage / déduplication
        invoices = sorted(dict.fromkeys(invoices))
        if invoices:
            total_amount = sum(float(L.get("amount") or 0) for L in fam.get("lessons", [])) if isinstance(fam.get("lessons"), list) else fam.get("total_courses", 0)
            families.append({
                "family_id": fam_id,
                "parent_name": parent_name,
                "parent_email": parent_email,
                "invoices": invoices,
                "total": total_amount,
                "invoice_count": len(invoices),
            })

    return families


def run_send_invoices(secrets, data, invoice_folder,
                      custom_subject=None, custom_body=None,
                      selected_families=None, send_to_test=False,
                      callback=None):
    """
    Envoie les factures par email.

    Returns:
        dict: {"success": bool, "sent": int, "total": int, "errors": list}
    """

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        gmail_config = secrets.get("gmail", {})
        sender_email = gmail_config.get("email")
        app_password = gmail_config.get("app_password")

        if not sender_email or not app_password:
            return {"success": False, "error": "Configuration email manquante dans secrets.yaml (gmail.email et gmail.app_password)"}

        if not invoice_folder or not os.path.exists(invoice_folder):
            return {"success": False, "error": f"Dossier de factures introuvable : {invoice_folder}"}

        template = get_default_email_template()
        subject = custom_subject or template["subject"]
        body = custom_body or template["body"]

        update(10, "📧 Préparation des emails...")

        pdf_paths = _collect_pdf_paths(invoice_folder)
        if not pdf_paths:
            return {"success": False, "error": f"Aucun PDF trouvé dans {invoice_folder}"}

        families = get_families_from_folder(invoice_folder, data)
        if not families:
            return {"success": False, "error": "Aucune facture trouvée ou aucune famille avec email"}

        if selected_families:
            selected_set = {str(fid) for fid in selected_families}
            families = [f for f in families if str(f["family_id"]) in selected_set]
            if not families:
                return {"success": False, "error": "Aucune facture trouvée pour les familles sélectionnées"}

        update(20, f"📊 {len(families)} famille(s) à contacter")
        update(30, "🔌 Connexion au serveur email...")

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)

        sent = 0
        errors = []
        total = len(families)

        for i, family in enumerate(families):
            progress = int(30 + (i / max(total, 1) * 65))
            recipient = sender_email if send_to_test else family["parent_email"]
            update(progress, f"📧 Envoi à {family['parent_name']}...")

            try:
                msg = MIMEMultipart()
                msg["From"] = sender_email
                msg["To"] = recipient

                final_subject = subject
                if family["invoice_count"] > 1:
                    final_subject = final_subject.replace("Facture -", "Factures -")
                else:
                    final_subject = final_subject.replace("Facture(s)", "Facture")
                msg["Subject"] = final_subject

                final_body = body
                if family["invoice_count"] > 1:
                    final_body = final_body.replace("votre/vos facture(s)", "vos factures")
                    final_body = final_body.replace("ci-joint votre facture", "ci-joint vos factures")
                else:
                    final_body = final_body.replace("votre/vos facture(s)", "votre facture")
                msg.attach(MIMEText(final_body, "plain"))

                attached = 0
                for invoice_path in family["invoices"]:
                    if os.path.exists(invoice_path):
                        with open(invoice_path, "rb") as f:
                            part = MIMEBase("application", "pdf")
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            filename = os.path.basename(invoice_path)
                            part.add_header("Content-Disposition", f"attachment; filename={filename}")
                            msg.attach(part)
                            attached += 1

                if attached == 0:
                    errors.append(f"{family['parent_name']}: aucun PDF attaché")
                    continue

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
            "found_pdfs": len(pdf_paths),
            "matched_families": len(families),
        }

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "Erreur d'authentification Gmail. Vérifiez l'email et le mot de passe d'application."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_send_test_email(secrets, invoice_folder, data, family_ids=None, callback=None):
    """Envoie les factures sélectionnées à l'email de test uniquement."""
    return run_send_invoices(
        secrets, data, invoice_folder,
        selected_families=family_ids,
        send_to_test=True,
        callback=callback
    )
