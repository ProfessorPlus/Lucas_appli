"""
🔄 Sync Stripe to Notion - NO SPLIT
Synchronise les paiements Stripe vers Notion en mode sans transfert.
Matching par famille + montant.
Pas de mise à jour des pages profs.
"""

import time
import traceback
from datetime import date, datetime, time as dt_time

import requests

try:
    import stripe
except ImportError:
    stripe = None


REQUEST_DELAY = 0.20


def normalize_name(value):
    if not value:
        return ""
    return " ".join(
        str(value).lower().strip().replace(",", " ").replace("&", " ").split()
    )


def names_match(name1, name2):
    w1 = set(normalize_name(name1).split())
    w2 = set(normalize_name(name2).split())
    if not w1 or not w2:
        return False
    return (
        w1 == w2
        or len(w1 & w2) >= 2
        or (len(w1) == 2 and w1.issubset(w2))
        or (len(w2) == 2 and w2.issubset(w1))
    )


def _to_dict(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        try:
            return obj.to_dict_recursive()
        except Exception:
            pass
    try:
        return dict(obj)
    except Exception:
        return {}


def _metadata_dict(obj):
    data = _to_dict(obj)
    meta = data.get("metadata") or {}
    if isinstance(meta, dict):
        return meta
    if hasattr(meta, "to_dict_recursive"):
        try:
            return meta.to_dict_recursive()
        except Exception:
            return {}
    try:
        return dict(meta)
    except Exception:
        return {}


def _first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _metadata_value(obj, *keys):
    meta = _metadata_dict(obj)
    for key in keys:
        value = meta.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _extract_family_name(charge):
    family_name = _metadata_value(
        charge,
        "parent_name",
        "family_name",
        "parent",
        "customer_name",
        "name",
    )
    if family_name:
        return family_name

    payment_intent_id = getattr(charge, "payment_intent", None)
    if payment_intent_id:
        try:
            pi = stripe.PaymentIntent.retrieve(payment_intent_id) if isinstance(payment_intent_id, str) else payment_intent_id
            family_name = _metadata_value(
                pi,
                "parent_name",
                "family_name",
                "parent",
                "customer_name",
                "name",
            )
            if family_name:
                return family_name
        except Exception:
            pass

    customer_id = getattr(charge, "customer", None)
    if customer_id:
        try:
            customer = stripe.Customer.retrieve(customer_id) if isinstance(customer_id, str) else customer_id
            family_name = _metadata_value(
                customer,
                "parent_name",
                "family_name",
                "parent",
                "customer_name",
                "name",
            )
            if family_name:
                return family_name
            customer_dict = _to_dict(customer)
            family_name = _first_non_empty(customer_dict.get("name"), customer_dict.get("email"))
            if family_name:
                return family_name
        except Exception:
            pass

    billing_details = _to_dict(getattr(charge, "billing_details", None))
    family_name = _first_non_empty(billing_details.get("name"), billing_details.get("email"))
    if family_name:
        return family_name

    charge_dict = _to_dict(charge)
    return _first_non_empty(charge_dict.get("description"), charge_dict.get("receipt_email"))


def _since_to_epoch(since_date):
    if not since_date:
        return None
    if isinstance(since_date, datetime):
        return int(since_date.timestamp())
    if isinstance(since_date, date):
        return int(datetime.combine(since_date, dt_time(0, 0)).timestamp())
    return None


def run_sync_stripe_notion_no_split(secrets_no_prof, secrets_notion, since_date=None, callback=None):
    """Synchronise les paiements Stripe vers Notion en mode no-split."""

    if stripe is None:
        return {"success": False, "error": "Module stripe non installé. pip install stripe"}

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        stripe.api_key = secrets_no_prof["stripe"]["platform_secret_key"]

        NOTION_TOKEN = secrets_notion["notion"]["token"]
        DB_PAIEMENTS = secrets_notion["notion"]["paiements_database_id"]
        ROOT_PAGE = secrets_notion["notion"].get("root_page_paiements")

        HEADERS = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

        def notion_request(method, endpoint, json_data=None):
            time.sleep(REQUEST_DELAY)
            url = f"https://api.notion.com/v1/{endpoint}"
            if method == "GET":
                r = requests.get(url, headers=HEADERS, timeout=30)
            elif method == "POST":
                r = requests.post(url, headers=HEADERS, json=json_data, timeout=30)
            elif method == "PATCH":
                r = requests.patch(url, headers=HEADERS, json=json_data, timeout=30)
            elif method == "DELETE":
                r = requests.delete(url, headers=HEADERS, timeout=30)
            else:
                return None

            if r.status_code == 429:
                retry = int(r.headers.get("Retry-After", 2))
                time.sleep(retry)
                return notion_request(method, endpoint, json_data)

            if r.status_code in (200, 201):
                return r.json() if r.text else {"ok": True}

            print(f"⚠️ Notion {method} {endpoint} -> {r.status_code}: {r.text[:500]}")
            return None

        def get_children(block_id):
            results = []
            cursor = None
            while True:
                endpoint = f"blocks/{block_id}/children?page_size=100"
                if cursor:
                    endpoint += f"&start_cursor={cursor}"
                data = notion_request("GET", endpoint)
                if not data:
                    break
                results.extend(data.get("results", []))
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
            return results

        def query_all_notion_rows():
            rows = []
            cursor = None
            while True:
                payload = {"page_size": 100}
                if cursor:
                    payload["start_cursor"] = cursor
                result = notion_request("POST", f"databases/{DB_PAIEMENTS}/query", payload)
                if not result:
                    break
                rows.extend(result.get("results", []))
                if not result.get("has_more"):
                    break
                cursor = result.get("next_cursor")
            return rows

        def parse_notion_row(row):
            props = row.get("properties", {})
            famille = ""
            famille_prop = props.get("Famille", {})
            if famille_prop.get("title"):
                items = famille_prop.get("title", [])
                if items:
                    famille = items[0].get("plain_text", "").strip()
            elif famille_prop.get("rich_text"):
                items = famille_prop.get("rich_text", [])
                if items:
                    famille = items[0].get("plain_text", "").strip()

            montant = props.get("Montant total dû", {}).get("number")
            if montant is None:
                montant = props.get("Montant dû Famille/Prof", {}).get("number", 0)

            paid = False
            if "Payé ?" in props:
                paid = bool(props.get("Payé ?", {}).get("checkbox", False))
            elif "Payé" in props:
                paid = bool(props.get("Payé", {}).get("checkbox", False))

            return {
                "page_id": row["id"],
                "famille": famille,
                "montant": float(montant or 0),
                "paid": paid,
            }

        def build_patch_properties(database_properties, payment):
            props = {}
            if "Payé ?" in database_properties:
                props["Payé ?"] = {"checkbox": True}
            elif "Payé" in database_properties:
                props["Payé"] = {"checkbox": True}

            if "Date des paiements" in database_properties:
                props["Date des paiements"] = {"date": {"start": payment["date_payment"]}}
            if "Montant réel versé par Stripe" in database_properties:
                props["Montant réel versé par Stripe"] = {"number": round(payment["montant_net"], 2)}
            return props

        def update_dashboard():
            if not ROOT_PAGE:
                return
            all_rows = query_all_notion_rows()
            parsed = [parse_notion_row(r) for r in all_rows]
            total_rows = len([r for r in parsed if r["famille"]])
            paid_rows = len([r for r in parsed if r["famille"] and r["paid"]])
            for block in get_children(ROOT_PAGE):
                if block.get("type") != "paragraph":
                    continue
                rich_text = block.get("paragraph", {}).get("rich_text", [])
                first_text = rich_text[0].get("plain_text", "") if rich_text else ""
                if "Bilan" in first_text:
                    notion_request("DELETE", f"blocks/{block['id']}")

            text = (
                f"Bilan – paiements effectués : {paid_rows} / {total_rows} paiements totaux"
                f"{' ✅' if total_rows and paid_rows == total_rows else ''}"
            )
            notion_request(
                "PATCH",
                f"blocks/{ROOT_PAGE}/children",
                {
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": text},
                                        "annotations": {"bold": True},
                                    }
                                ]
                            },
                        }
                    ]
                },
            )

        update(5, "💳 Récupération des paiements Stripe (no-split)...")
        params = {"limit": 100}
        epoch = _since_to_epoch(since_date)
        if epoch:
            params["created"] = {"gte": epoch}

        charges = stripe.Charge.list(**params)
        stripe_payments = []
        for charge in charges.auto_paging_iter():
            if getattr(charge, "status", None) != "succeeded":
                continue

            amount = (getattr(charge, "amount", 0) or 0) / 100
            currency = str(getattr(charge, "currency", "chf")).upper()
            montant_net = amount
            balance_transaction = getattr(charge, "balance_transaction", None)
            if balance_transaction:
                try:
                    bt_id = balance_transaction if isinstance(balance_transaction, str) else getattr(balance_transaction, "id", None)
                    if bt_id:
                        bt = stripe.BalanceTransaction.retrieve(bt_id)
                        montant_net = (getattr(bt, "net", 0) or 0) / 100
                except Exception:
                    montant_net = amount

            family_name = _extract_family_name(charge)
            stripe_payments.append({
                "charge_id": getattr(charge, "id", ""),
                "family_name": family_name,
                "amount": round(amount, 2),
                "montant_net": round(montant_net, 2),
                "currency": currency,
                "date_payment": datetime.fromtimestamp(getattr(charge, "created", int(time.time()))).strftime("%Y-%m-%d"),
            })

        update(30, f"📊 {len(stripe_payments)} paiement(s) Stripe trouvé(s)")
        update(40, "📥 Récupération des données Notion...")

        db_info = notion_request("GET", f"databases/{DB_PAIEMENTS}")
        if not db_info:
            return {"success": False, "error": "Impossible de lire la structure de la base Notion."}

        database_properties = db_info.get("properties", {})
        all_notion_rows = query_all_notion_rows()
        notion_rows = [parse_notion_row(row) for row in all_notion_rows if parse_notion_row(row)["famille"]]

        update(55, f"📊 {len(notion_rows)} ligne(s) Notion trouvée(s)")
        update(60, "🔄 Matching Stripe ↔ Notion (famille + montant)...")

        synced = 0
        already_paid = 0
        no_match = []
        duplicates_warning = []
        matched_ids = set()
        total = len(stripe_payments)

        for i, payment in enumerate(stripe_payments):
            progress = int(60 + (i / max(total, 1) * 35))
            candidates = []
            for row in notion_rows:
                family_match = names_match(row["famille"], payment["family_name"])
                amount_match = abs(round(row["montant"], 2) - round(payment["amount"], 2)) < 0.01
                if family_match and amount_match:
                    candidates.append(row)

            unpaid_candidates = [row for row in candidates if not row["paid"] and row["page_id"] not in matched_ids]
            paid_candidates = [row for row in candidates if row["paid"]]

            if len(unpaid_candidates) > 1:
                duplicates_warning.append(
                    f"{payment['family_name']} | {payment['amount']} {payment['currency']} → {len(unpaid_candidates)} lignes non payées possibles"
                )

            if unpaid_candidates:
                chosen = unpaid_candidates[0]
                update(progress, f"✅ {payment['family_name']}")
                patch_props = build_patch_properties(database_properties, payment)
                if not patch_props:
                    return {
                        "success": False,
                        "error": "La base Notion ne contient pas les propriétés attendues pour la mise à jour.",
                    }
                result = notion_request("PATCH", f"pages/{chosen['page_id']}", {"properties": patch_props})
                if result:
                    synced += 1
                    matched_ids.add(chosen["page_id"])
                else:
                    no_match.append(
                        f"{payment['family_name']} | {payment['amount']} {payment['currency']} (échec mise à jour Notion)"
                    )
            elif paid_candidates:
                already_paid += 1
            else:
                no_match.append(f"{payment['family_name']} | {payment['amount']} {payment['currency']}")

        update(95, "📊 Mise à jour du dashboard...")
        update_dashboard()
        update(100, "✅ Sync no-split terminée !")

        return {
            "success": True,
            "synced": synced,
            "already_paid": already_paid,
            "not_found": no_match[:20],
            "total_not_found": len(no_match),
            "duplicates_warning": duplicates_warning[:20],
            "total_duplicates_warning": len(duplicates_warning),
            "student_unknown": 0,
            "total_charges": len(stripe_payments),
        }

    except stripe.error.AuthenticationError:
        return {
            "success": False,
            "error": "Erreur d'authentification Stripe - Vérifiez la clé dans secrets_no_prof.yaml",
        }
    except Exception as e:
        return {"success": False, "error": f"{str(e)}\n{traceback.format_exc()}"}
