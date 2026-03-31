"""
🔔 Send Payment Reminders
Envoie des rappels de paiement aux familles n'ayant pas encore payé.
Version robuste : lit les bonnes colonnes Notion et groupe par famille.
"""

import os
import smtplib
import unicodedata
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from difflib import SequenceMatcher
import time
import requests

MONTHS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def normalize(s):
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('-', ' ').replace('_', ' ')
    s = re.sub(r"\s+", " ", s)
    if ',' in s:
        p = [x.strip() for x in s.split(',', 1)]
        if len(p) == 2:
            s = f"{p[1]} {p[0]}"
    return s.strip()


def names_match(a, b):
    na = normalize(a)
    nb = normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    sa, sb = set(na.split()), set(nb.split())
    return sa == sb or len(sa & sb) >= 2 or SequenceMatcher(None, na, nb).ratio() > 0.82


def _pick_first_existing(db_properties, *names):
    for name in names:
        if name in db_properties:
            return name
    return names[0] if names else None


def _get_text_property(props, prop_name):
    prop = props.get(prop_name, {})
    if prop.get('title'):
        items = prop.get('title', [])
        return items[0].get('plain_text', '').strip() if items else ''
    if prop.get('rich_text'):
        items = prop.get('rich_text', [])
        return items[0].get('plain_text', '').strip() if items else ''
    return ''


def _get_email_property(props, prop_name):
    prop = props.get(prop_name, {})
    if prop.get('email'):
        return str(prop.get('email') or '').strip()
    if prop.get('rich_text'):
        items = prop.get('rich_text', [])
        return items[0].get('plain_text', '').strip() if items else ''
    return ''


def _first_non_empty_email(*values):
    for value in values:
        if value is None:
            continue
        email = str(value).strip()
        if email:
            return email
    return ''


def _extract_email_candidate(fam):
    """Retourne le meilleur email disponible dans les données TutorBird/converties.
    On accepte plusieurs clés car selon les scripts la donnée peut arriver sous
    parent_email, email_client, email, ou dans un sous-dict parent/client.
    """
    if not isinstance(fam, dict):
        return ''

    parent = fam.get('parent') if isinstance(fam.get('parent'), dict) else {}
    client = fam.get('client') if isinstance(fam.get('client'), dict) else {}

    return _first_non_empty_email(
        fam.get('parent_email'),
        fam.get('email_client'),
        fam.get('client_email'),
        fam.get('email'),
        parent.get('email'),
        parent.get('parent_email'),
        client.get('email'),
        client.get('email_client'),
    )


def _enrich_email_from_data(family_name, data):
    if not data:
        return ''
    for fam in data.values():
        candidate_name = (
            fam.get('parent_name')
            or fam.get('family_name')
            or fam.get('client_name')
            or fam.get('name')
            or ''
        )
        if names_match(candidate_name, family_name):
            return _extract_email_candidate(fam)
    return ''


def _list_invoice_family_names(invoice_folder):
    names = []
    if not invoice_folder or not os.path.exists(invoice_folder):
        return names
    for item in os.listdir(invoice_folder):
        item_path = os.path.join(invoice_folder, item)
        if os.path.isdir(item_path):
            names.append(item)
    return names


def get_default_reminder_template(month_name=None, year=None):
    if not month_name:
        now = datetime.now()
        month_name = MONTHS_FR[now.month - 1]
        year = now.year
    return {
        "subject": f"Rappel - Facture(s) en attente - Soutien scolaire - {month_name} {year}",
        "body": f"""Bonjour,

J'espère que vous allez bien.

Je me permets de vous relancer concernant la/les facture(s) de soutien scolaire du mois de {month_name} {year} qui reste(nt) en attente de règlement.

Vous trouverez ci-joint la/les facture(s) correspondante(s). Vous pouvez régler directement en cliquant sur le bouton "Payer en ligne" dans le PDF.

Merci de procéder au paiement dès que possible.

N'hésitez pas à me contacter si vous avez des questions ou si vous avez déjà effectué le paiement.

Cordialement,
Professor+
"""
    }


def get_unpaid_families_from_notion(secrets, callback=None, data=None, invoice_folder=None):
    """Retourne les familles non payées depuis Notion, regroupées par famille.
    Si invoice_folder est fourni, on garde prioritairement les familles présentes dans le dossier de factures.
    """

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        NOTION_TOKEN = secrets['notion']['token']
        DB_PAIEMENTS = secrets['notion']['paiements_database_id']

        HEADERS = {
            'Authorization': f'Bearer {NOTION_TOKEN}',
            'Content-Type': 'application/json',
            'Notion-Version': '2022-06-28',
        }

        def notion_request(method, endpoint, json_data=None):
            time.sleep(0.25)
            url = f'https://api.notion.com/v1/{endpoint}'
            if method == 'GET':
                r = requests.get(url, headers=HEADERS, timeout=30)
            elif method == 'POST':
                r = requests.post(url, headers=HEADERS, json=json_data, timeout=30)
            else:
                return None
            if r.status_code == 429:
                retry = int(r.headers.get('Retry-After', 2))
                time.sleep(retry)
                return notion_request(method, endpoint, json_data)
            if r.status_code in [200, 201]:
                return r.json() if r.text else {'ok': True}
            print(f"⚠️ Notion {method} {endpoint} -> {r.status_code}: {r.text[:500]}")
            return None

        update(10, '📥 Chargement des données Notion...')
        db_info = notion_request('GET', f'databases/{DB_PAIEMENTS}')
        if not db_info:
            return {'success': False, 'error': 'Impossible de lire la base Notion.'}

        db_properties = db_info.get('properties', {})
        paid_prop = _pick_first_existing(db_properties, 'Payé ?', 'Payé')
        amount_prop = _pick_first_existing(db_properties, 'Montant dû Famille/Prof', 'Montant total dû')

        all_rows = []
        cursor = None
        while True:
            payload = {
                'filter': {
                    'property': paid_prop,
                    'checkbox': {'equals': False}
                }
            }
            if cursor:
                payload['start_cursor'] = cursor
            data_resp = notion_request('POST', f'databases/{DB_PAIEMENTS}/query', payload)
            if not data_resp:
                break
            all_rows.extend(data_resp.get('results', []))
            if not data_resp.get('has_more'):
                break
            cursor = data_resp.get('next_cursor')

        update(50, f'📊 {len(all_rows)} ligne(s) non payée(s) trouvée(s)')

        folder_family_names = _list_invoice_family_names(invoice_folder)
        grouped = {}
        for row in all_rows:
            props = row.get('properties', {})
            family_name = _get_text_property(props, 'Famille')
            if not family_name:
                continue

            if folder_family_names and not any(names_match(folder_name, family_name) for folder_name in folder_family_names):
                continue

            email = _get_email_property(props, 'Email parent')
            if not email:
                email = _enrich_email_from_data(family_name, data)

            amount = props.get(amount_prop, {}).get('number', 0) or 0
            date_cours = None
            if props.get('Date cours factures', {}).get('date'):
                date_cours = props['Date cours factures']['date'].get('start')

            key = normalize(family_name)
            item = grouped.setdefault(key, {
                'parent_name': family_name,
                'parent_email': email,
                'amount': 0.0,
                'date': date_cours,
                'page_ids': [],
                'rows': 0,
            })
            if not item['parent_email'] and email:
                item['parent_email'] = email
            if date_cours and not item['date']:
                item['date'] = date_cours
            item['amount'] += float(amount or 0)
            item['page_ids'].append(row['id'])
            item['rows'] += 1

        unpaid = list(grouped.values())
        unpaid.sort(key=lambda x: normalize(x['parent_name']))
        return {'success': True, 'unpaid': unpaid}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def run_send_reminders(secrets, data, invoice_folder, data_dir,
                       custom_subject=None, custom_body=None,
                       selected_families=None, send_to_test=False,
                       callback=None,
                       custom_subject_carole=None, custom_body_carole=None):
    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        gmail_config = secrets.get('gmail', {})
        sender_email = gmail_config.get('email')
        app_password = gmail_config.get('app_password')
        if not sender_email or not app_password:
            return {'success': False, 'error': 'Configuration email manquante dans secrets.yaml'}

        update(5, '📥 Récupération des impayés depuis Notion...')
        result = get_unpaid_families_from_notion(secrets, callback, data=data, invoice_folder=invoice_folder)
        if not result['success']:
            return result

        unpaid_families = result['unpaid']
        if selected_families:
            unpaid_families = [f for f in unpaid_families if f['parent_name'] in selected_families]
        if not unpaid_families:
            return {'success': True, 'sent': 0, 'message': 'Aucune famille avec paiement en attente', 'total': 0}

        # Tenter une seconde enrichissement email si nécessaire
        for fam in unpaid_families:
            if not fam.get('parent_email'):
                fam['parent_email'] = _enrich_email_from_data(fam['parent_name'], data)

        template = get_default_reminder_template()
        subject = custom_subject or template['subject']
        body = custom_body or template['body']

        update(20, f"📊 {len(unpaid_families)} famille(s) à relancer")
        update(30, '🔌 Connexion au serveur email...')
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, app_password)

        sent = 0
        errors = []
        total = len(unpaid_families)

        for i, family in enumerate(unpaid_families):
            progress = int(30 + (i / max(total, 1) * 65))
            recipient = sender_email if send_to_test else family.get('parent_email', '')
            if not recipient:
                errors.append(f"{family['parent_name']}: email manquant")
                continue

            update(progress, f"📧 Rappel à {family['parent_name']}...")
            try:
                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = recipient
                
                # Déterminer le template: Carole (notion_hors_tb) ou standard
                is_carole = False
                if data and custom_subject_carole:
                    for fam in data.values():
                        if fam.get("source") == "notion_hors_tb" and names_match(fam.get("parent_name", ""), family['parent_name']):
                            is_carole = True
                            break
                
                if is_carole:
                    msg['Subject'] = custom_subject_carole
                    msg.attach(MIMEText(custom_body_carole or body, 'plain'))
                else:
                    msg['Subject'] = subject
                    msg.attach(MIMEText(body, 'plain'))

                attached_count = 0
                if invoice_folder and os.path.exists(invoice_folder):
                    parent_norm = normalize(family['parent_name'])
                    for item in os.listdir(invoice_folder):
                        item_path = os.path.join(invoice_folder, item)
                        if os.path.isdir(item_path):
                            folder_norm = normalize(item)
                            score = SequenceMatcher(None, folder_norm, parent_norm).ratio()
                            if score > 0.7 or folder_norm == parent_norm or names_match(folder_norm, parent_norm):
                                for pdf in os.listdir(item_path):
                                    if pdf.lower().endswith('.pdf'):
                                        invoice_path = os.path.join(item_path, pdf)
                                        with open(invoice_path, 'rb') as f:
                                            part = MIMEBase('application', 'pdf')
                                            part.set_payload(f.read())
                                            encoders.encode_base64(part)
                                            part.add_header('Content-Disposition', f'attachment; filename={pdf}')
                                            msg.attach(part)
                                            attached_count += 1
                                break
                        elif item.lower().endswith('.pdf'):
                            pdf_lower = item.lower()
                            name_parts = parent_norm.split()
                            if any(part in pdf_lower for part in name_parts if len(part) > 2):
                                invoice_path = os.path.join(invoice_folder, item)
                                with open(invoice_path, 'rb') as f:
                                    part = MIMEBase('application', 'pdf')
                                    part.set_payload(f.read())
                                    encoders.encode_base64(part)
                                    part.add_header('Content-Disposition', f'attachment; filename={item}')
                                    msg.attach(part)
                                    attached_count += 1

                server.sendmail(sender_email, recipient, msg.as_string())
                sent += 1
            except Exception as e:
                errors.append(f"{family['parent_name']}: {str(e)}")

        server.quit()
        update(100, '✅ Terminé !')
        return {
            'success': True,
            'sent': sent,
            'total': total,
            'errors': errors,
            'test_mode': send_to_test,
        }
    except smtplib.SMTPAuthenticationError:
        return {'success': False, 'error': "Erreur d'authentification Gmail"}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def should_send_automatic_reminder():
    return datetime.now().day == 11


def get_reminder_settings_path(config_dir):
    return os.path.join(config_dir, 'reminder_settings.yaml')