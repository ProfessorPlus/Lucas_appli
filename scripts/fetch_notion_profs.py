"""
📋 Fetch Unpaid from Notion — Consolidation n-2
================================================
Lit la base Notion "Paiements – Base Centrale" pour détecter les lignes
impayées d'un mois donné (typiquement n-2 par rapport à la date d'envoi).

Retourne les données structurées par famille avec :
- Professeur, Élève, Heures, Montant dû
- Payment link Stripe (pour désactivation ultérieure)
- Page ID Notion (pour référence)

Usage:
    from scripts.fetch_unpaid_notion import fetch_unpaid_n2, deactivate_old_payment_links

    result = fetch_unpaid_n2(secrets, target_year=2026, target_month=2)
    # result["families"] = {family_name_normalized: {
    #     "parent_name": ..., "total_amount": ..., "currency": ...,
    #     "rows": [{"prof": ..., "eleve": ..., "heures": ..., "montant": ..., "payment_link_id": ...}],
    #     "payment_link_ids": [...]
    # }}
"""

import time as _time
import re
import unicodedata
from datetime import datetime

import requests


REQUEST_DELAY = 0.25

MONTHS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]


def _normalize(s):
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("-", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s)
    if "," in s:
        p = [x.strip() for x in s.split(",", 1)]
        if len(p) == 2:
            s = f"{p[1]} {p[0]}"
    return s.strip()


def _get_text(props, prop_name):
    """Extrait le texte d'une propriété Notion (title ou rich_text)."""
    prop = props.get(prop_name, {})
    for key in ("title", "rich_text"):
        items = prop.get(key, [])
        if items:
            return items[0].get("plain_text", "").strip()
    return ""


def _get_number(props, prop_name):
    """Extrait un nombre d'une propriété Notion."""
    prop = props.get(prop_name, {})
    val = prop.get("number")
    return float(val) if val is not None else 0.0


def _get_checkbox(props, prop_name):
    prop = props.get(prop_name, {})
    return prop.get("checkbox", False)


def _get_date_start(props, prop_name):
    """Extrait la date de début d'une propriété date Notion (YYYY-MM-DD)."""
    prop = props.get(prop_name, {})
    date_obj = prop.get("date")
    if date_obj:
        return date_obj.get("start", "")
    return ""


def _get_url(props, prop_name):
    """Extrait une URL d'une propriété Notion."""
    prop = props.get(prop_name, {})
    return prop.get("url") or ""


def _pick_first_existing(db_properties, *names):
    for name in names:
        if name in db_properties:
            return name
    return names[0] if names else None


def fetch_unpaid_n2(secrets, target_year, target_month, callback=None):
    """
    Récupère les lignes impayées de la base Notion "Paiements Base Centrale"
    pour un mois cible (typiquement n-2).

    Filtre : Date cours factures.start est dans le mois cible ET Payé ? = false.

    Args:
        secrets: dict config (notion.token, notion.paiements_database_id)
        target_year: année du mois cible (ex: 2026)
        target_month: mois cible 1-12 (ex: 2 pour Février)
        callback: fn(progress, message)

    Returns:
        dict: {
            "success": bool,
            "families": {
                normalized_name: {
                    "parent_name": str,
                    "total_amount": float,
                    "currency": str,
                    "rows": [
                        {
                            "page_id": str,
                            "prof": str,
                            "eleve": str,
                            "heures": str,
                            "montant": float,
                            "currency": str,
                            "payment_link_id": str,  # Stripe payment link ID ou URL
                            "date_cours_start": str,
                        }
                    ],
                    "payment_link_ids": [str],
                }
            },
            "month_label": str,  # ex: "Février 2026"
            "total_rows": int,
            "error": str | None,
        }
    """

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        notion_cfg = secrets.get("notion", {})
        token = notion_cfg.get("token")
        db_id = notion_cfg.get("paiements_database_id")

        if not token:
            return {"success": False, "families": {}, "error": "Token Notion manquant"}
        if not db_id:
            return {"success": False, "families": {}, "error": "paiements_database_id manquant"}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

        month_label = f"{MONTHS_FR[target_month - 1]} {target_year}"
        update(5, f"📋 Recherche des impayés — {month_label}...")

        # Déterminer les bornes du mois cible
        import calendar
        last_day = calendar.monthrange(target_year, target_month)[1]
        date_start = f"{target_year:04d}-{target_month:02d}-01"
        date_end = f"{target_year:04d}-{target_month:02d}-{last_day:02d}"

        # Récupérer les propriétés de la base pour détecter les noms de colonnes
        update(10, "📥 Lecture de la structure Notion...")
        _time.sleep(REQUEST_DELAY)
        r = requests.get(
            f"https://api.notion.com/v1/databases/{db_id}",
            headers=headers,
            timeout=30,
        )
        if r.status_code != 200:
            return {"success": False, "families": {}, "error": f"Erreur lecture base Notion: {r.status_code}"}

        db_properties = r.json().get("properties", {})
        paid_prop = _pick_first_existing(db_properties, "Payé ?", "Payé")
        amount_prop = _pick_first_existing(db_properties, "Montant dû Famille/Prof", "Montant total dû")

        # Query Notion avec filtre combiné : Payé = false AND Date cours factures dans le mois cible
        update(20, f"🔍 Requête Notion pour {month_label}...")

        all_rows = []
        cursor = None

        while True:
            payload = {
                "filter": {
                    "and": [
                        {
                            "property": paid_prop,
                            "checkbox": {"equals": False},
                        },
                        {
                            "property": "Date cours factures",
                            "date": {"on_or_after": date_start},
                        },
                        {
                            "property": "Date cours factures",
                            "date": {"on_or_before": date_end},
                        },
                    ]
                }
            }
            if cursor:
                payload["start_cursor"] = cursor

            _time.sleep(REQUEST_DELAY)
            resp = requests.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 2))
                _time.sleep(retry)
                continue
            if resp.status_code != 200:
                return {
                    "success": False,
                    "families": {},
                    "error": f"Erreur query Notion: {resp.status_code} — {resp.text[:300]}",
                }

            data = resp.json()
            all_rows.extend(data.get("results", []))

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

        update(60, f"📊 {len(all_rows)} ligne(s) impayée(s) trouvée(s) pour {month_label}")

        # Parser les résultats et regrouper par famille
        families = {}

        for row in all_rows:
            props = row.get("properties", {})

            famille = _get_text(props, "Famille")
            if not famille:
                continue

            prof = _get_text(props, "Professeur")
            eleve = _get_text(props, "Élève")
            heures = _get_text(props, "Heures")
            montant = _get_number(props, amount_prop)
            currency = _get_text(props, "Devise") or "CHF"
            date_cours_start = _get_date_start(props, "Date cours factures")

            # Payment link Stripe — peut être URL ou rich_text
            payment_link_raw = _get_url(props, "Payment link Stripe")
            if not payment_link_raw:
                payment_link_raw = _get_text(props, "Payment link Stripe")

            # Extraire le payment_link_id Stripe depuis l'URL si possible
            # Format typique: https://buy.stripe.com/xxx ou plink_xxx
            payment_link_id = ""
            if payment_link_raw:
                if payment_link_raw.startswith("plink_"):
                    payment_link_id = payment_link_raw
                elif "buy.stripe.com" in payment_link_raw:
                    # On garde l'URL complète pour le lookup dans payment_links_output.json
                    payment_link_id = payment_link_raw

            key = _normalize(famille)
            if key not in families:
                families[key] = {
                    "parent_name": famille,
                    "total_amount": 0.0,
                    "currency": currency.upper(),
                    "rows": [],
                    "payment_link_ids": [],
                }

            families[key]["total_amount"] += montant
            families[key]["rows"].append({
                "page_id": row["id"],
                "prof": prof,
                "eleve": eleve,
                "heures": heures,
                "montant": montant,
                "currency": currency.upper(),
                "payment_link_id": payment_link_id,
                "date_cours_start": date_cours_start,
            })

            if payment_link_id and payment_link_id not in families[key]["payment_link_ids"]:
                families[key]["payment_link_ids"].append(payment_link_id)

        update(80, f"✅ {len(families)} famille(s) avec impayés pour {month_label}")

        return {
            "success": True,
            "families": families,
            "month_label": month_label,
            "total_rows": len(all_rows),
            "error": None,
        }

    except Exception as e:
        return {"success": False, "families": {}, "error": str(e)}


def deactivate_old_payment_links(secrets, unpaid_families, payment_links_output=None, callback=None):
    """
    Désactive les anciens liens Stripe des familles ayant des impayés n-2.
    
    Cherche les payment_link_id dans :
    1. Les données Notion (families[key]["payment_link_ids"])
    2. Le fichier payment_links_output.json (par family_id + invoice_date matching)
    
    Args:
        secrets: config avec stripe.platform_secret_key (ou stripe_no_split)
        unpaid_families: dict retourné par fetch_unpaid_n2()["families"]
        payment_links_output: liste des liens depuis payment_links_output.json (optionnel)
        callback: fn(progress, message)
    
    Returns:
        dict: {"success": bool, "deactivated": int, "errors": list, "skipped": int}
    """
    try:
        import stripe
    except ImportError:
        return {"success": False, "deactivated": 0, "errors": ["Module stripe non installé"], "skipped": 0}

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        # Déterminer la clé Stripe
        stripe_cfg = secrets.get("stripe_no_split") or secrets.get("stripe", {})
        api_key = stripe_cfg.get("platform_secret_key", "")
        if not api_key:
            api_key = secrets.get("stripe", {}).get("platform_secret_key", "")
        if not api_key:
            return {"success": False, "deactivated": 0, "errors": ["Clé Stripe manquante"], "skipped": 0}

        stripe.api_key = api_key

        # Collecter tous les payment_link_ids à désactiver
        link_ids_to_deactivate = set()

        # 1. Depuis les données Notion
        for key, fam_data in unpaid_families.items():
            for link_id_or_url in fam_data.get("payment_link_ids", []):
                if link_id_or_url:
                    link_ids_to_deactivate.add(link_id_or_url)

        # 2. Depuis payment_links_output.json — matcher par famille et chercher les anciens liens
        if payment_links_output:
            unpaid_parent_names = {_normalize(f["parent_name"]) for f in unpaid_families.values()}
            for entry in payment_links_output:
                parent = entry.get("parent") or entry.get("parent_name") or ""
                link_id = entry.get("payment_link_id") or ""
                if _normalize(parent) in unpaid_parent_names and link_id:
                    link_ids_to_deactivate.add(link_id)

        if not link_ids_to_deactivate:
            return {"success": True, "deactivated": 0, "errors": [], "skipped": 0}

        update(10, f"🔒 Désactivation de {len(link_ids_to_deactivate)} ancien(s) lien(s)...")

        deactivated = 0
        errors = []
        skipped = 0

        for i, link_ref in enumerate(link_ids_to_deactivate):
            progress = int(10 + (i / max(len(link_ids_to_deactivate), 1) * 85))

            # Déterminer le vrai payment_link_id Stripe
            plink_id = None
            if link_ref.startswith("plink_"):
                plink_id = link_ref
            elif "buy.stripe.com" in link_ref:
                # Essayer de trouver le plink_id dans payment_links_output
                if payment_links_output:
                    for entry in payment_links_output:
                        if entry.get("payment_link") == link_ref:
                            plink_id = entry.get("payment_link_id")
                            break
                if not plink_id:
                    # Extraire depuis l'URL (dernier segment)
                    parts = link_ref.rstrip("/").split("/")
                    candidate = parts[-1] if parts else ""
                    if candidate and not candidate.startswith("plink_"):
                        # Ce n'est pas un ID valide, on skip
                        skipped += 1
                        continue
                    plink_id = candidate
            else:
                skipped += 1
                continue

            if not plink_id:
                skipped += 1
                continue

            try:
                stripe.PaymentLink.modify(plink_id, active=False)
                deactivated += 1
                update(progress, f"🔒 Désactivé : {plink_id[:20]}...")
            except stripe.error.InvalidRequestError as e:
                if "already inactive" in str(e).lower() or "not found" in str(e).lower():
                    skipped += 1
                else:
                    errors.append(f"{plink_id}: {str(e)}")
            except Exception as e:
                errors.append(f"{plink_id}: {str(e)}")

        update(100, f"✅ {deactivated} lien(s) désactivé(s)")

        return {
            "success": True,
            "deactivated": deactivated,
            "errors": errors,
            "skipped": skipped,
        }

    except Exception as e:
        return {"success": False, "deactivated": 0, "errors": [str(e)], "skipped": 0}