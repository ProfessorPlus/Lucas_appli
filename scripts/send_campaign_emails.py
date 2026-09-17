"""
📣 Send Campaign Emails
Relance commerciale : envoi d'un email type aux familles ayant reçu une facture
un mois donné (ex : message de rentrée scolaire).

Différence avec send_payment_reminders.py : aucune pièce jointe, aucun filtre
sur le statut de paiement — on s'adresse à d'anciens clients pour les faire revenir.
"""

import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from scripts.send_payment_reminders import (
    normalize,
    names_match,
    _extract_email_candidate,
    _get_text_property,
    _get_email_property,
)

MONTHS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

FAMILY_PLACEHOLDER = "{famille}"


def get_default_campaign_template(month_name=None, year=None):
    """Template de relance de rentrée. month_name/year servent juste à dater l'objet."""
    if not year:
        year = datetime.now().year
    return {
        "subject": f"Nouvelle année scolaire {year} — Professor+ vous accompagne",
        "body": """Bonjour,

J'espère que vous allez bien et que cette nouvelle année scolaire démarre bien pour vous.

Ce serait un plaisir de continuer à accompagner votre enfant cette année. Que ce soit en mathématiques, en allemand, en physique, en chimie ou en biologie, nos professeurs sont disponibles pour un soutien scolaire sur-mesure, à votre rythme.

N'hésitez pas à revenir vers moi pour organiser les premiers cours, ou simplement pour en discuter ensemble.

Au plaisir de vous retrouver cette année.

Cordialement,
Professor+
""",
    }


def list_families_in_folder(invoice_folder):
    """Noms de familles d'un dossier de factures (un sous-dossier = une famille)."""
    if not invoice_folder or not os.path.exists(invoice_folder):
        return []

    names = []
    for item in sorted(os.listdir(invoice_folder)):
        if os.path.isdir(os.path.join(invoice_folder, item)):
            names.append(item)
    return names


def fetch_emails_from_notion(secrets, callback=None):
    """Construit {nom de famille normalisé: email} depuis la base Paiements Notion.

    La base Paiements accumule l'historique des lignes facturées : c'est la seule
    source d'email pour une famille qui n'apparaît plus dans l'extraction du mois.
    """
    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        token = secrets["notion"]["token"]
        db_id = secrets["notion"]["paiements_database_id"]
    except (KeyError, TypeError):
        return {"success": False, "error": "Configuration Notion manquante (notion.token / notion.paiements_database_id)."}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    emails = {}
    cursor = None
    pages = 0

    try:
        while True:
            payload = {"page_size": 100}
            if cursor:
                payload["start_cursor"] = cursor

            time.sleep(0.25)
            response = requests.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if response.status_code == 429:
                time.sleep(int(response.headers.get("Retry-After", 2)))
                continue
            if response.status_code != 200:
                return {"success": False, "error": f"Notion {response.status_code}: {response.text[:300]}"}

            body = response.json()
            for row in body.get("results", []):
                props = row.get("properties", {})
                family_name = _get_text_property(props, "Famille")
                email = _get_email_property(props, "Email parent")
                if family_name and email:
                    emails.setdefault(normalize(family_name), email)

            pages += 1
            update(min(90, pages * 10), f"📥 {len(emails)} email(s) trouvé(s) dans Notion...")

            if not body.get("has_more"):
                break
            cursor = body.get("next_cursor")

        return {"success": True, "emails": emails}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fill_missing_emails(recipients, notion_emails):
    """Complète les emails vides depuis une map {nom normalisé: email}. Retourne le nombre rempli."""
    if not notion_emails:
        return 0

    filled = 0
    for recipient in recipients:
        if recipient.get("email"):
            continue

        name = recipient.get("family_name", "")
        email = notion_emails.get(normalize(name), "")
        if not email:
            for notion_key, notion_email in notion_emails.items():
                if names_match(notion_key, name):
                    email = notion_email
                    break

        if email:
            recipient["email"] = email
            recipient["email_source"] = "notion"
            filled += 1

    return filled


def build_campaign_recipients(invoice_folder, data, notion_emails=None):
    """Familles du dossier de factures, enrichies du meilleur email disponible.

    Ordre de recherche : extraction courante -> base Notion -> vide (à saisir à la main).
    """
    recipients = []

    for folder_name in list_families_in_folder(invoice_folder):
        display_name = folder_name.replace("_", " ").strip()
        email = ""
        source = ""

        for fam in (data or {}).values():
            candidate = fam.get("parent_name") or fam.get("family_name") or ""
            if candidate and names_match(candidate, display_name):
                email = _extract_email_candidate(fam)
                if email:
                    source = "extraction"
                    if candidate.strip():
                        display_name = candidate.strip()
                break

        recipients.append({
            "folder_name": folder_name,
            "family_name": display_name,
            "email": email,
            "email_source": source,
        })

    fill_missing_emails(recipients, notion_emails)
    recipients.sort(key=lambda r: normalize(r["family_name"]))
    return recipients


def run_send_campaign(secrets, recipients, subject, body,
                      send_to_test=False, callback=None):
    """Envoie l'email de campagne. {famille} est remplacé par le nom de la famille."""
    def update(progress, message):
        if callback:
            callback(progress, message)

    gmail_config = (secrets or {}).get("gmail", {})
    sender_email = gmail_config.get("email")
    app_password = gmail_config.get("app_password")

    if not sender_email or not app_password:
        return {"success": False, "error": "Configuration email manquante dans secrets.yaml (gmail.email / gmail.app_password)."}
    if not subject or not body:
        return {"success": False, "error": "L'objet et le corps du message sont obligatoires."}

    targets = [r for r in (recipients or []) if r.get("email")]
    if not targets:
        return {"success": False, "error": "Aucun destinataire avec une adresse email."}

    try:
        update(10, "🔌 Connexion au serveur email...")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "error": "Erreur d'authentification Gmail (vérifie le mot de passe d'application)."}
    except Exception as e:
        return {"success": False, "error": f"Connexion SMTP impossible : {e}"}

    sent = 0
    errors = []
    total = len(targets)

    try:
        for i, recipient in enumerate(targets):
            progress = int(10 + (i / max(total, 1) * 85))
            family_name = recipient.get("family_name", "")
            destination = sender_email if send_to_test else recipient["email"]

            update(progress, f"📧 {family_name}...")
            try:
                message = MIMEMultipart()
                message["From"] = sender_email
                message["To"] = destination
                message["Subject"] = subject.replace(FAMILY_PLACEHOLDER, family_name)
                message.attach(MIMEText(body.replace(FAMILY_PLACEHOLDER, family_name), "plain", "utf-8"))
                server.sendmail(sender_email, destination, message.as_string())
                sent += 1
            except Exception as e:
                errors.append(f"{family_name}: {e}")
    finally:
        try:
            server.quit()
        except Exception:
            pass

    update(100, "✅ Terminé !")
    return {
        "success": True,
        "sent": sent,
        "total": total,
        "errors": errors,
        "test_mode": send_to_test,
    }
