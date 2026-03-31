"""
📧 Send Invoices Email
Envoie les factures par email aux familles
"""

import os
import smtplib
import re
import unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime


MONTHS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]
MONTH_MAP_FR_EN = dict(zip(MONTHS_FR, MONTHS_EN))


def normalize_ascii(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def is_english(value):
    return str(value or "").strip().lower() in {"anglais", "english", "en"}


def english_month(month_name, year):
    if month_name in MONTH_MAP_FR_EN:
        return MONTH_MAP_FR_EN[month_name], year
    return month_name, year


def get_default_email_template(month_name=None, year=None, language="fr"):
    """Retourne le template d'email par défaut."""
    if not month_name:
        now = datetime.now()
        idx = now.month - 1
        year = now.year
        month_name = MONTHS_FR[idx] if language != "en" else MONTHS_EN[idx]

    if language == "en":
        month_name, year = english_month(month_name, year)
        return {
            "subject": f"Invoice(s) - Tutoring - {month_name} {year}",
            "body": f"""Hello,

I hope you are well.

Please find attached your invoice(s) for the tutoring lessons for {month_name} {year}.

You can pay directly by clicking the "Pay online" button in the PDF invoice.

Please proceed with payment at your earliest convenience, before 10 {month_name} {year}.

Best regards,
Professor+
"""
        }

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


def _collect_pdfs_recursively(invoice_folder):
    pdf_files = []
    for root, _, files in os.walk(invoice_folder):
        for f in files:
            if f.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, f))
    return pdf_files


def _match_family_invoices(parent_name, pdf_paths):
    tokens = [t for t in normalize_ascii(parent_name).split() if len(t) >= 2]
    matched = []
    for path in pdf_paths:
        hay = normalize_ascii(os.path.basename(path) + ' ' + os.path.basename(os.path.dirname(path)))
        if tokens and sum(1 for t in tokens if t in hay) >= max(1, min(2, len(tokens))):
            matched.append(path)
    return matched


def collect_invoice_diagnostics(invoice_folder, data):
    """
    Analyse le dossier de factures et explique quelles familles sont envoyables.

    Returns:
        dict avec:
          - found_pdfs
          - ready_families
          - missing_email_families
          - missing_pdf_families
    """
    result = {
        "found_pdfs": 0,
        "ready_families": [],
        "missing_email_families": [],
        "missing_pdf_families": [],
    }

    if not invoice_folder or not os.path.exists(invoice_folder):
        return result

    pdf_paths = _collect_pdfs_recursively(invoice_folder)
    result["found_pdfs"] = len(pdf_paths)

    for fam_id, fam in data.items():
        parent_name = fam.get("parent_name") or fam.get("family_name") or ""
        parent_email = fam.get("parent_email") or fam.get("email_client") or ""
        invoices = _match_family_invoices(parent_name, pdf_paths)
        language = fam.get("language", "fr")

        if invoices and parent_email:
            result["ready_families"].append({
                "family_id": fam_id,
                "parent_name": parent_name,
                "parent_email": parent_email,
                "invoices": invoices,
                "invoice_count": len(invoices),
                "language": language,
            })
        elif invoices and not parent_email:
            result["missing_email_families"].append({
                "family_id": fam_id,
                "parent_name": parent_name,
                "invoice_count": len(invoices),
                "sample_invoice": os.path.basename(invoices[0]) if invoices else "",
            })
        elif parent_email and not invoices:
            result["missing_pdf_families"].append({
                "family_id": fam_id,
                "parent_name": parent_name,
                "parent_email": parent_email,
            })

    return result


def get_families_from_folder(invoice_folder, data):
    """Récupère la liste des familles avec leurs factures (recherche récursive)."""
    return collect_invoice_diagnostics(invoice_folder, data)["ready_families"]


def _adapt_subject(subject, invoice_count, language):
    if language == "en":
        if invoice_count > 1:
            return subject.replace("Invoice -", "Invoices -").replace("Invoice(s)", "Invoices")
        return subject.replace("Invoice(s)", "Invoice")
    if invoice_count > 1:
        return subject.replace("Facture -", "Factures -").replace("Facture(s)", "Factures")
    return subject.replace("Facture(s)", "Facture")


def _adapt_body(body, invoice_count, language):
    final_body = body
    if language == "en":
        if invoice_count > 1:
            final_body = final_body.replace("your invoice(s)", "your invoices")
            final_body = final_body.replace("invoice(s)", "invoices")
        else:
            final_body = final_body.replace("invoice(s)", "invoice")
        return final_body

    if invoice_count > 1:
        final_body = final_body.replace("votre/vos facture(s)", "vos factures")
        final_body = final_body.replace("ci-joint votre facture", "ci-joint vos factures")
    else:
        final_body = final_body.replace("votre/vos facture(s)", "votre facture")
    return final_body


def run_send_invoices(secrets, data, invoice_folder,
                      custom_subject=None, custom_body=None,
                      selected_families=None, send_to_test=False,
                      callback=None,
                      custom_subject_en=None, custom_body_en=None,
                      custom_subject_carole=None, custom_body_carole=None):
    """Envoie les factures par email."""

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        gmail_config = secrets.get("gmail", {})
        sender_email = gmail_config.get("email")
        app_password = gmail_config.get("app_password")
        if not sender_email or not app_password:
            return {"success": False, "error": "Configuration email manquante dans secrets.yaml (gmail.email et gmail.app_password)"}

        template_fr = get_default_email_template(language="fr")
        template_en = get_default_email_template(language="en")
        subject_fr = custom_subject or template_fr["subject"]
        body_fr = custom_body or template_fr["body"]
        subject_en = custom_subject_en or template_en["subject"]
        body_en = custom_body_en or template_en["body"]

        update(10, "📧 Préparation des emails...")
        diagnostics = collect_invoice_diagnostics(invoice_folder, data)
        families = diagnostics["ready_families"]

        if not families:
            return {
                "success": False,
                "error": "Aucune facture trouvée ou aucune famille avec email",
                "found_pdfs": diagnostics["found_pdfs"],
                "matched_families": 0,
                "missing_email_families": diagnostics["missing_email_families"],
                "missing_pdf_families": diagnostics["missing_pdf_families"],
            }

        if selected_families:
            families = [f for f in families if f["family_id"] in selected_families]
        if not families:
            return {
                "success": False,
                "error": "Aucune famille sélectionnée avec facture et email",
                "found_pdfs": diagnostics["found_pdfs"],
                "matched_families": 0,
                "missing_email_families": diagnostics["missing_email_families"],
                "missing_pdf_families": diagnostics["missing_pdf_families"],
            }

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

                # Déterminer le template: Carole (notion_hors_tb) > EN > FR
                fam_data = data.get(family.get("family_id"), {})
                is_carole = fam_data.get("source") == "notion_hors_tb"
                
                if is_carole and custom_subject_carole:
                    raw_subject = custom_subject_carole
                    raw_body = custom_body_carole or body_en
                    lang = "en"
                else:
                    lang = "en" if is_english(family.get("language")) else "fr"
                    raw_subject = subject_en if lang == "en" else subject_fr
                    raw_body = body_en if lang == "en" else body_fr
                msg["Subject"] = _adapt_subject(raw_subject, family["invoice_count"], lang)
                msg.attach(MIMEText(_adapt_body(raw_body, family["invoice_count"], lang), "plain"))

                for invoice_path in family["invoices"]:
                    if os.path.exists(invoice_path):
                        with open(invoice_path, "rb") as f:
                            part = MIMEBase("application", "pdf")
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            filename = os.path.basename(invoice_path)
                            part.add_header("Content-Disposition", f"attachment; filename={filename}")
                            msg.attach(part)

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
            "found_pdfs": diagnostics["found_pdfs"],
            "matched_families": len(families),
            "missing_email_families": diagnostics["missing_email_families"],
            "missing_pdf_families": diagnostics["missing_pdf_families"],
        }

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "Erreur d'authentification Gmail. Vérifiez l'email et le mot de passe d'application."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_send_test_email(secrets, invoice_folder, data, family_ids=None, callback=None):
    return run_send_invoices(
        secrets, data, invoice_folder,
        selected_families=family_ids,
        send_to_test=True,
        callback=callback
    )