"""
🔄 Sync Stripe to Notion - NO SPLIT
Synchronise les paiements Stripe vers Notion en mode sans transfert.
Pas de matching par prof — on matche uniquement par famille + montant.
Pas de mise à jour des pages profs.

Utilisé quand le mode "tout recevoir sur mon compte" est activé.
"""

import time
import requests
from datetime import datetime
from typing import Any

try:
    import stripe
except ImportError:
    stripe = None

REQUEST_DELAY = 0.20


def _stripe_to_plain_dict(obj: Any):
    """Convertit un objet Stripe/Mapping en dict Python simple quand possible."""
    if not obj:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    try:
        return dict(obj)
    except Exception:
        pass

    data = {}
    # Fallback minimal pour les StripeObject qui ne se convertissent pas directement.
    for key in [
        "parent_name", "family_name", "customer_name", "name", "full_name",
        "billing_name", "receipt_email", "email", "family_id"
    ]:
        try:
            value = obj[key]
        except Exception:
            try:
                value = getattr(obj, key)
            except Exception:
                value = None
        if value not in (None, ""):
            data[key] = value
    return data


def _first_non_empty(*values):
    for value in values:
        if isinstance(value, str):
            if value.strip():
                return value.strip()
        elif value not in (None, ""):
            return value
    return ""


def _metadata_value(metadata, *keys):
    data = _stripe_to_plain_dict(metadata)
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_charge_family_name(ch):
    """Essaie plusieurs sources pour retrouver le nom de la famille/parent."""
    # 1) Metadata directement sur la charge
    family_name = _metadata_value(
        getattr(ch, "metadata", None),
        "parent_name", "family_name", "customer_name", "name", "full_name", "billing_name"
    )

    # 2) Metadata du PaymentIntent (très fréquent avec Payment Links / Checkout)
    payment_intent_id = getattr(ch, "payment_intent", None)
    if not family_name and payment_intent_id and stripe is not None:
        try:
            pi = stripe.PaymentIntent.retrieve(payment_intent_id)
            family_name = _metadata_value(
                getattr(pi, "metadata", None),
                "parent_name", "family_name", "customer_name", "name", "full_name", "billing_name"
            )
        except Exception:
            pass

    # 3) Customer Stripe
    customer_id = getattr(ch, "customer", None)
    if not family_name and customer_id and stripe is not None:
        try:
            customer = stripe.Customer.retrieve(customer_id)
            family_name = _first_non_empty(
                _metadata_value(
                    getattr(customer, "metadata", None),
                    "parent_name", "family_name", "customer_name", "name", "full_name"
                ),
                getattr(customer, "name", None),
                getattr(customer, "email", None),
            )
        except Exception:
            pass

    # 4) Billing details de la charge
    if not family_name:
        billing_details = getattr(ch, "billing_details", None)
        family_name = _first_non_empty(
            _metadata_value(billing_details, "name", "full_name", "billing_name"),
            getattr(billing_details, "name", None) if billing_details else None,
        )

    # 5) Derniers fallback utiles
    if not family_name:
        family_name = _first_non_empty(
            getattr(ch, "description", None),
            getattr(ch, "receipt_email", None),
        )

    return family_name.strip() if isinstance(family_name, str) else ""


def normalize_name(n):
    if not n:
        return ""
    return " ".join(n.lower().strip().replace(",", " ").replace("&", " ").split())


def names_match(n1, n2):
    w1, w2 = set(normalize_name(n1).split()), set(normalize_name(n2).split())
    if not w1 or not w2:
        return False
    return w1 == w2 or len(w1 & w2) >= 2 or (len(w1) == 2 and w1.issubset(w2)) or (len(w2) == 2 and w2.issubset(w1))


def run_sync_stripe_notion_no_split(secrets_no_prof, secrets_notion, since_date=None, callback=None):
    """
    Synchronise les paiements Stripe vers Notion en mode no-split.
    
    Args:
        secrets_no_prof: Config Stripe (depuis secrets_no_prof.yaml)
        secrets_notion: Config Notion (depuis secrets.yaml — même Notion)
        since_date: Date depuis laquelle synchroniser
        callback: Fonction callback(progress, message)
    
    Returns:
        dict avec synced, already_paid, no_match, etc.
    """
    
    if stripe is None:
        return {"success": False, "error": "Module stripe non installé. pip install stripe"}
    
    def update(progress, message):
        if callback:
            callback(progress, message)
    
    try:
        # Stripe depuis secrets_no_prof
        stripe.api_key = secrets_no_prof["stripe"]["platform_secret_key"]
        
        # Notion depuis secrets normal (même DB)
        NOTION_TOKEN = secrets_notion["notion"]["token"]
        DB_PAIEMENTS = secrets_notion["notion"]["paiements_database_id"]
        ROOT_PAGE = secrets_notion["notion"]["root_page_paiements"]
        
        HEADERS = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        
        def notion_request(method, endpoint, json_data=None):
            time.sleep(REQUEST_DELAY)
            url = f"https://api.notion.com/v1/{endpoint}"
            if method == "POST":
                r = requests.post(url, headers=HEADERS, json=json_data, timeout=30)
            elif method == "PATCH":
                r = requests.patch(url, headers=HEADERS, json=json_data, timeout=30)
            elif method == "GET":
                r = requests.get(url, headers=HEADERS, timeout=30)
            elif method == "DELETE":
                r = requests.delete(url, headers=HEADERS, timeout=30)
            else:
                return None
            
            if r.status_code == 429:
                retry = int(r.headers.get("Retry-After", 2))
                time.sleep(retry)
                return notion_request(method, endpoint, json_data)
            
            if r.status_code in [200, 201]:
                return r.json() if r.text else {"ok": True}
            return None
        
        def get_children(block_id):
            results = []
            cursor = None
            while True:
                url = f"blocks/{block_id}/children?page_size=100"
                if cursor:
                    url += f"&start_cursor={cursor}"
                data = notion_request("GET", url)
                if not data:
                    break
                results.extend(data.get("results", []))
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
            return results
        
        # ===========================
        # ÉTAPE 1: Récupérer les paiements Stripe
        # ===========================
        update(5, "💳 Récupération des paiements Stripe (no-split)...")
        
        params = {"limit": 100}
        if since_date:
            params["created"] = {"gte": int(since_date.timestamp())}
        
        charges = stripe.Charge.list(**params)
        stripe_payments = []
        
        for ch in charges.data:
            if ch.status != "succeeded":
                continue
            
            # En mode no-split, pas de transfer_data
            # Récupérer le net depuis balance_transaction
            montant_net = ch.amount / 100
            if ch.balance_transaction:
                try:
                    bt = stripe.BalanceTransaction.retrieve(ch.balance_transaction)
                    montant_net = bt.net / 100
                except Exception:
                    pass
            
            # Extraire le nom de la famille de façon robuste (charge / PI / customer / billing details)
            family_name = _extract_charge_family_name(ch)
            
            stripe_payments.append({
                "charge_id": ch.id,
                "family_name": family_name,
                "amount": ch.amount / 100,
                "montant_net": montant_net,
                "currency": (ch.currency or "chf").upper(),
                "date_payment": datetime.fromtimestamp(ch.created).strftime("%Y-%m-%d"),
            })
        
        update(30, f"📊 {len(stripe_payments)} paiements Stripe trouvés")
        
        # ===========================
        # ÉTAPE 2: Récupérer les lignes Notion non payées
        # ===========================
        update(40, "📥 Récupération des données Notion...")
        
        all_notion_rows = []
        cursor = None
        
        while True:
            payload = {}
            if cursor:
                payload["start_cursor"] = cursor
            
            result = notion_request("POST", f"databases/{DB_PAIEMENTS}/query", payload)
            if not result:
                break
            
            all_notion_rows.extend(result.get("results", []))
            
            if not result.get("has_more"):
                break
            cursor = result.get("next_cursor")
        
        # Parser les lignes Notion
        notion_rows = []
        for row in all_notion_rows:
            p = row["properties"]
            
            famille = ""
            famille_prop = p.get("Famille", {})
            if famille_prop.get("title"):
                famille = famille_prop["title"][0]["plain_text"] if famille_prop["title"] else ""
            
            montant = p.get("Montant total dû", {}).get("number", 0) or 0
            paid = p.get("Payé ?", {}).get("checkbox", False)
            
            if famille:
                notion_rows.append({
                    "page_id": row["id"],
                    "famille": famille,
                    "montant": montant,
                    "paid": paid,
                })
        
        update(55, f"📊 {len(notion_rows)} lignes Notion trouvées")
        
        # ===========================
        # ÉTAPE 3: Matching par famille + montant
        # ===========================
        update(60, "🔄 Matching Stripe ↔ Notion...")
        
        synced = 0
        already_paid = 0
        no_match = []
        matched_ids = set()
        
        total = len(stripe_payments)
        
        for i, sp in enumerate(stripe_payments):
            progress = int(60 + (i / max(total, 1) * 35))
            
            found_unpaid = None
            found_paid = None
            
            for nr in notion_rows:
                # Matcher par famille + montant (tolérance 0.01)
                family_match = names_match(nr["famille"], sp["family_name"])
                amount_match = abs(round(nr["montant"], 2) - round(sp["amount"], 2)) < 0.01
                
                if family_match and amount_match:
                    if not nr["paid"] and nr["page_id"] not in matched_ids:
                        found_unpaid = nr
                        break
                    elif nr["paid"]:
                        found_paid = nr
            
            if found_unpaid:
                update(progress, f"✅ {sp['family_name']}")
                
                # Marquer comme payé
                result = notion_request("PATCH", f"pages/{found_unpaid['page_id']}", {
                    "properties": {
                        "Payé ?": {"checkbox": True},
                        "Date des paiements": {"date": {"start": sp["date_payment"]}},
                    }
                })
                
                if result:
                    synced += 1
                    matched_ids.add(found_unpaid["page_id"])
            
            elif found_paid:
                already_paid += 1
            
            else:
                no_match.append(f"{sp['family_name']} | {sp['amount']} {sp['currency']}")
        
        # ===========================
        # ÉTAPE 4: Mettre à jour le dashboard
        # ===========================
        update(95, "📊 Mise à jour du dashboard...")
        
        total_rows = len(all_notion_rows)
        paid_rows = synced + sum(1 for nr in notion_rows if nr["paid"])
        
        for b in get_children(ROOT_PAGE):
            if b["type"] == "paragraph":
                rt = b.get("paragraph", {}).get("rich_text", [])
                if rt and "Bilan" in rt[0].get("plain_text", ""):
                    notion_request("DELETE", f"blocks/{b['id']}")
        
        text = f"Bilan – paiements effectués : {paid_rows} / {total_rows} paiements totaux{' ✅' if paid_rows == total_rows else ''}"
        notion_request("PATCH", f"blocks/{ROOT_PAGE}/children", {
            "children": [{"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}, "annotations": {"bold": True}}]}}]
        })
        
        update(100, "✅ Sync no-split terminée !")
        
        return {
            "success": True,
            "synced": synced,
            "already_paid": already_paid,
            "not_found": no_match[:20],
            "total_not_found": len(no_match),
            "student_unknown": 0,
            "total_charges": len(stripe_payments),
        }
        
    except stripe.error.AuthenticationError:
        return {"success": False, "error": "Erreur d'authentification Stripe - Vérifiez la clé dans secrets_no_prof.yaml"}
    except Exception as e:
        import traceback
        return {"success": False, "error": f"{str(e)}\n{traceback.format_exc()}"}