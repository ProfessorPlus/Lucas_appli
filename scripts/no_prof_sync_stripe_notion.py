"""
🔄 Sync Stripe to Notion - NO SPLIT
Synchronise les paiements Stripe vers Notion en mode sans transfert.
Matching principal : famille + montant.
Fallbacks : email + montant, puis montant unique.
Pas de mise à jour des pages profs.
"""

import time
import traceback
from datetime import datetime

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
    # Stripe SDK v15+ : to_dict_recursive() ou to_dict()
    if hasattr(obj, "to_dict_recursive"):
        try:
            return obj.to_dict_recursive()
        except Exception:
            pass
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            pass
    # Fallback par attributs connus — JAMAIS dict(obj) qui crash sur SDK v15
    result = {}
    for attr in ("metadata", "billing_details", "payment_intent", "customer",
                 "id", "amount", "currency", "status", "created", "receipt_url",
                 "receipt_email", "description", "balance_transaction"):
        try:
            val = getattr(obj, attr, None)
            if val is not None:
                result[attr] = val
        except Exception:
            pass
    return result


def _metadata_dict(obj):
    """Extrait les metadata d'un objet Stripe en dict Python."""
    raw_meta = getattr(obj, "metadata", None)
    if raw_meta is None:
        data = _to_dict(obj)
        raw_meta = data.get("metadata")
    if raw_meta is None:
        return {}
    if isinstance(raw_meta, dict):
        return raw_meta
    if hasattr(raw_meta, "to_dict"):
        try:
            return raw_meta.to_dict()
        except Exception:
            pass
    if hasattr(raw_meta, "to_dict_recursive"):
        try:
            return raw_meta.to_dict_recursive()
        except Exception:
            pass
    # Fallback par clés connues
    result = {}
    for key in ("mode", "parent_name", "family_name", "parent_email", "customer_email",
                "email", "teacher_names", "product_name", "invoice_date", "currency",
                "family_id", "source_label", "includes_previous_months", "gross_amount",
                "parent", "customer_name", "name"):
        try:
            val = raw_meta.get(key)
            if val is not None:
                result[key] = val
        except Exception:
            pass
    return result


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


def _extract_charge_identity(charge):
    family_name = _metadata_value(
        charge,
        "parent_name",
        "family_name",
        "parent",
        "customer_name",
        "name",
    )
    email = _metadata_value(charge, "parent_email", "customer_email", "email")

    charge_dict = _to_dict(charge)
    billing_details = _to_dict(charge_dict.get("billing_details") or getattr(charge, "billing_details", None))
    if not family_name:
        family_name = _first_non_empty(
            billing_details.get("name"),
            charge_dict.get("description"),
        )
    if not email:
        email = _first_non_empty(
            billing_details.get("email"),
            charge_dict.get("receipt_email"),
        )

    payment_intent_ref = charge_dict.get("payment_intent") or getattr(charge, "payment_intent", None)
    if payment_intent_ref:
        try:
            pi = stripe.PaymentIntent.retrieve(payment_intent_ref) if isinstance(payment_intent_ref, str) else payment_intent_ref
            if not family_name:
                family_name = _metadata_value(pi, "parent_name", "family_name", "parent", "customer_name", "name")
            if not email:
                email = _metadata_value(pi, "parent_email", "customer_email", "email")
        except Exception:
            pass

    customer_ref = charge_dict.get("customer") or getattr(charge, "customer", None)
    if customer_ref:
        try:
            customer = stripe.Customer.retrieve(customer_ref) if isinstance(customer_ref, str) else customer_ref
            customer_dict = _to_dict(customer)
            if not family_name:
                family_name = _metadata_value(customer, "parent_name", "family_name", "parent", "customer_name", "name")
            if not family_name:
                family_name = _first_non_empty(customer_dict.get("name"))
            if not email:
                email = _metadata_value(customer, "parent_email", "customer_email", "email")
            if not email:
                email = _first_non_empty(customer_dict.get("email"))
        except Exception:
            pass

    return {
        "family_name": family_name,
        "email": email,
    }


def run_sync_stripe_notion_no_split(secrets_no_prof, secrets_notion, since_date=None, callback=None):
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
                payload = {}
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

        def get_text_property(props, prop_name):
            prop = props.get(prop_name, {})
            if prop.get("title"):
                items = prop.get("title", [])
                return items[0].get("plain_text", "").strip() if items else ""
            if prop.get("rich_text"):
                items = prop.get("rich_text", [])
                return items[0].get("plain_text", "").strip() if items else ""
            return ""

        def get_email_property(props, prop_name):
            prop = props.get(prop_name, {})
            if prop.get("email"):
                return str(prop.get("email") or "").strip()
            if prop.get("rich_text"):
                items = prop.get("rich_text", [])
                return items[0].get("plain_text", "").strip() if items else ""
            return ""

        def get_number_property(props, *names):
            for name in names:
                if name in props:
                    value = props.get(name, {}).get("number")
                    if value is not None:
                        return float(value)
            return 0.0

        def get_checkbox_property(props, *names):
            for name in names:
                if name in props:
                    return bool(props.get(name, {}).get("checkbox", False))
            return False

        def get_date_property(props, prop_name):
            prop = props.get(prop_name, {})
            date_val = prop.get("date")
            if date_val and date_val.get("start"):
                return date_val["start"][:10]  # YYYY-MM-DD
            return ""

        def parse_notion_row(row):
            props = row.get("properties", {})
            return {
                "page_id": row["id"],
                "famille": get_text_property(props, "Famille"),
                "professeur": get_text_property(props, "Professeur"),
                "eleve": get_text_property(props, "Élève"),
                "invoice_date": get_date_property(props, "Invoice date"),
                "montant": get_number_property(props, "Montant dû Famille/Prof", "Montant total dû"),
                "paid": get_checkbox_property(props, "Payé ?", "Payé"),
                "pid": int(get_number_property(props, "id paiements") or 0),
            }

        def build_patch_properties(db_properties, payment):
            props = {}
            if "Payé ?" in db_properties:
                props["Payé ?"] = {"checkbox": True}
            elif "Payé" in db_properties:
                props["Payé"] = {"checkbox": True}

            if "Date des paiements" in db_properties:
                props["Date des paiements"] = {"date": {"start": payment["date_payment"]}}
            if "Montant réel versé par Stripe" in db_properties:
                props["Montant réel versé par Stripe"] = {"number": round(payment["montant_net"], 2)}
            return props

        def update_dashboard():
            if not ROOT_PAGE:
                return
            rows = [parse_notion_row(r) for r in query_all_notion_rows()]
            total_rows = len([r for r in rows if r["famille"]])
            paid_rows = len([r for r in rows if r["famille"] and r["paid"]])
            for block in get_children(ROOT_PAGE):
                if block.get("type") != "paragraph":
                    continue
                rich_text = block.get("paragraph", {}).get("rich_text", [])
                first_text = rich_text[0].get("plain_text", "") if rich_text else ""
                if "Bilan" in first_text:
                    notion_request("DELETE", f"blocks/{block['id']}")
            text = f"Bilan – paiements effectués : {paid_rows} / {total_rows} paiements totaux{' ✅' if total_rows and paid_rows == total_rows else ''}"
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

        # 1) Stripe
        update(5, "💳 Récupération des paiements Stripe (no-split)...")
        params = {"limit": 100}
        if since_date:
            params["created"] = {"gte": int(since_date.timestamp())}

        charges = stripe.Charge.list(**params)
        stripe_payments = []
        for charge in charges.auto_paging_iter():
            if getattr(charge, "status", None) != "succeeded":
                continue
            amount = (getattr(charge, "amount", 0) or 0) / 100
            currency = str(getattr(charge, "currency", "chf") or "chf").upper()
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

            identity = _extract_charge_identity(charge)
            meta = _metadata_dict(charge)
            
            # Extraire prof, élève, invoice_date depuis les metadata Stripe
            teacher_names = meta.get("teacher_names", "")
            product_name = meta.get("product_name", "")
            invoice_date = meta.get("invoice_date", "")
            
            # Extraire le nom de l'élève depuis product_name: "Soutien scolaire | Forgione Alexander"
            student_name = ""
            if product_name and "|" in product_name:
                student_name = product_name.split("|", 1)[1].strip()
            
            stripe_payments.append({
                "charge_id": getattr(charge, "id", ""),
                "family_name": identity.get("family_name", ""),
                "email": identity.get("email", ""),
                "amount": round(amount, 2),
                "montant_net": round(montant_net, 2),
                "currency": currency,
                "date_payment": datetime.fromtimestamp(getattr(charge, "created", int(time.time()))).strftime("%Y-%m-%d"),
                "teacher": teacher_names,
                "student": student_name,
                "invoice_date": invoice_date,
            })

        update(30, f"📊 {len(stripe_payments)} paiement(s) Stripe trouvé(s)")

        # 2) Notion
        update(40, "📥 Récupération des données Notion...")
        db_info = notion_request("GET", f"databases/{DB_PAIEMENTS}")
        if not db_info:
            return {"success": False, "error": "Impossible de lire la structure de la base Notion."}
        db_properties = db_info.get("properties", {})
        notion_rows = [parse_notion_row(r) for r in query_all_notion_rows()]
        notion_rows = [r for r in notion_rows if r["famille"]]
        update(55, f"📊 {len(notion_rows)} ligne(s) Notion trouvée(s)")

        # 3) Matching par 4 colonnes: Professeur + Élève + Invoice date + Montant
        update(60, "🔄 Matching Stripe ↔ Notion (Prof + Élève + Invoice date + Montant)...")
        synced = 0
        already_paid = 0
        no_match = []
        duplicates_warning = []
        matched_ids = set()
        total = len(stripe_payments)

        for i, payment in enumerate(stripe_payments):
            progress = int(60 + (i / max(total, 1) * 35))
            amount = round(payment["amount"], 2)
            sp_teacher = payment.get("teacher", "")
            sp_student = payment.get("student", "")
            sp_invoice_date = payment.get("invoice_date", "")
            sp_family = payment.get("family_name", "")
            
            print(f"  🔍 Stripe: {sp_family} | prof={sp_teacher} | élève={sp_student} | date={sp_invoice_date} | {amount} {payment['currency']}")
            
            # Trouver les lignes Notion qui matchent les 4 critères
            matching_rows = []
            for row in notion_rows:
                if row["page_id"] in matched_ids:
                    continue
                
                # 1. Montant (tolérance 0.01)
                if abs(round(row["montant"], 2) - amount) >= 0.01:
                    continue
                
                # 2. Invoice date — préférence, pas filtre dur
                date_matches = True
                if sp_invoice_date and row.get("invoice_date"):
                    date_matches = (row["invoice_date"] == sp_invoice_date)
                
                # 3. Professeur (au moins un prof en commun)
                prof_match = True
                if sp_teacher and row.get("professeur"):
                    # Les profs peuvent être séparés par virgule
                    notion_profs = {p.strip().lower() for p in row["professeur"].split(",")}
                    stripe_profs = {p.strip().lower() for p in sp_teacher.split("/")}
                    prof_match = bool(notion_profs & stripe_profs) or any(
                        names_match(np, sp) for np in notion_profs for sp in stripe_profs
                    )
                    if not prof_match:
                        continue
                
                # 4. Élève (nom de l'élève dans le product_name)
                eleve_match = True
                if sp_student and row.get("eleve"):
                    eleve_match = names_match(row["eleve"], sp_student)
                    if not eleve_match:
                        # Essayer match partiel (l'élève Notion peut avoir plusieurs noms)
                        notion_eleves = row["eleve"].replace("&", ",")
                        for ne in notion_eleves.split(","):
                            if names_match(ne.strip(), sp_student):
                                eleve_match = True
                                break
                    if not eleve_match:
                        continue
                
                row["_date_matches"] = date_matches
                matching_rows.append(row)
            
            # Trier : préférer les lignes avec date exacte, puis par pid décroissant
            exact_date = [r for r in matching_rows if r.get("_date_matches", True)]
            chosen = exact_date if exact_date else matching_rows
            chosen.sort(key=lambda r: r.get("pid", 0), reverse=True)
            
            if not exact_date and matching_rows:
                print(f"    ℹ️ Pas de match date exacte ({sp_invoice_date}), fallback sans date")
            
            # Séparer payés et non payés
            unpaid = [r for r in chosen if not r["paid"]]
            paid = [r for r in chosen if r["paid"]]
            
            # Détecter les vrais doublons (lignes identiques sur les 4 colonnes)
            if len(unpaid) > 1:
                # Grouper par (prof+élève+invoice_date+montant) pour trouver les vrais doublons
                seen_keys = {}
                for r in unpaid:
                    key = (r.get("professeur", "").lower(), r.get("eleve", "").lower(), r.get("invoice_date", ""), round(r["montant"], 2))
                    seen_keys.setdefault(key, []).append(r)
                
                for key, rows in seen_keys.items():
                    if len(rows) > 1:
                        duplicates_warning.append(
                            f"{rows[0]['famille']} | {key[0]} | {key[1]} | {key[3]} "
                            f"→ {len(rows)} lignes identiques non payées"
                        )
            
            if unpaid:
                chosen = unpaid[0]  # pid le plus haut
                update(progress, f"✅ {sp_family or chosen['famille']}")
                patch_props = build_patch_properties(db_properties, payment)
                result = notion_request("PATCH", f"pages/{chosen['page_id']}", {"properties": patch_props})
                if result:
                    synced += 1
                    matched_ids.add(chosen["page_id"])
                    print(f"    ✅ Marqué payé: {chosen['famille']} (pid={chosen.get('pid')})")
                else:
                    no_match.append(f"{sp_family} | {amount} {payment['currency']} (échec API)")
            elif paid:
                already_paid += 1
            else:
                no_match.append(f"{sp_family} | {sp_teacher} | {sp_student} | {amount} {payment['currency']}")

        # 4) Dashboard
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
        return {"success": False, "error": "Erreur d'authentification Stripe - Vérifiez la clé dans secrets_no_prof.yaml"}
    except Exception as e:
        return {"success": False, "error": f"{str(e)}\n{traceback.format_exc()}"}