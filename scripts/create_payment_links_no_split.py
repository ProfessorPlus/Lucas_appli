"""
💳 Create Payment Links - NO SPLIT
Génère des liens de paiement Stripe SANS transfert (tout va sur le compte principal).
Utilise secrets_no_prof.yaml (clé Stripe différente, pas de split).

Même logique que create_payment_links.py mais simplifié :
- Pas de transfer_data
- Pas de on_behalf_of
- Pas de application_fee_amount
- Un seul lien par famille (pas de split par prof)
"""

import os
import json
import re
import unicodedata
from datetime import datetime

try:
    import stripe
except ImportError:
    stripe = None

try:
    from scripts.storage_manager import save_json, load_json
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False


def normalize(s):
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    if "," in s:
        p = [x.strip() for x in s.split(",", 1)]
        if len(p) == 2:
            s = f"{p[1]} {p[0]}"
    return s.strip()


def build_product_name(lessons):
    students = list({L["student"] for L in lessons if L.get("student")})
    students.sort()
    students = students[:2]

    if not students:
        return "Soutien scolaire"

    first = students[0]
    if "," in first:
        last_name, first_name = [s.strip() for s in first.split(",", 1)]
    else:
        parts = first.split()
        last_name = parts[-1]
        first_name = " ".join(parts[:-1]) if len(parts) > 1 else ""

    base = f"{last_name} {first_name}".strip()

    if len(students) == 2:
        second = students[1]
        if "," in second:
            _, second_first = [s.strip() for s in second.split(",", 1)]
        else:
            parts2 = second.split()
            second_first = parts2[0] if parts2 else second
        base = f"{base} & {second_first}"

    return f"Soutien scolaire | {base}"


def run_create_payment_links_no_split(
    data,
    secrets_no_prof,
    familles_euros,
    data_dir,
    callback=None,
    payment_method_types=None,
    target_family_ids=None,
    skip_if_exists=True,
):
    """
    Génère les liens de paiement Stripe SANS aucun split/transfert.
    Tout va sur le compte Stripe défini dans secrets_no_prof.

    Args:
        data: données familles (full_output_tb_SIMPLE.json)
        secrets_no_prof: config depuis secrets_no_prof.yaml
        familles_euros: liste des familles en EUR
        data_dir: dossier de données
        callback: fonction progress
        payment_method_types: méthodes de paiement
        target_family_ids: familles ciblées (None = toutes)
        skip_if_exists: éviter les doublons
    """

    if stripe is None:
        return {"success": False, "error": "Module stripe non installé. pip install stripe"}

    def update(progress, message):
        if callback:
            callback(progress, message)

    try:
        stripe.api_key = secrets_no_prof["stripe"]["platform_secret_key"]

        # Charger les liens existants
        existing_index = set()
        output_path = os.path.join(data_dir, "payment_links_output.json")

        prev = None
        if STORAGE_AVAILABLE and skip_if_exists:
            prev = load_json("payment_links_output.json", "data", default=None)

        if prev is None and skip_if_exists and os.path.exists(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    prev = json.load(f)
            except Exception:
                prev = []

        if prev:
            for it in prev:
                existing_index.add((
                    str(it.get("family_id", "")),
                    (it.get("currency") or "").lower(),
                    float(it.get("amount") or 0),
                    str(it.get("invoice_date") or ""),
                ))

        def already_exists(fam_id, currency, total_amount, invoice_date):
            key = (str(fam_id), currency.lower(), float(total_amount), str(invoice_date))
            key2 = (str(fam_id), currency.lower(), float(total_amount), "")
            return key in existing_index or key2 in existing_index

        FAMILLES_EUROS = {name.lower(): True for name in familles_euros}

        def is_eur_family(name):
            if not isinstance(name, str):
                return False
            return name.lower().strip() in FAMILLES_EUROS

        output_links = []
        today = datetime.today().strftime("%Y-%m-%d")
        absences_ignorees = 0

        all_items = list(data.items())
        if target_family_ids:
            target_set = {str(x) for x in target_family_ids}
            all_items = [(fid, fam) for (fid, fam) in all_items if str(fid) in target_set]

        total_families = len(all_items)
        current = 0

        for fam_id, fam in all_items:
            current += 1
            progress = int(current / max(total_families, 1) * 80)

            parent_name = fam.get("parent_name") or fam.get("family_name") or ""
            parent_email = fam.get("parent_email") or ""

            update(progress, f"🔄 {parent_name} ({current}/{total_families})")

            currency = "eur" if is_eur_family(parent_name) else "chf"
            lessons = fam.get("lessons", [])
            if not lessons:
                continue

            # Calculer le montant total facturable (toutes leçons confondues, pas de split par prof)
            billable_lessons = []
            for L in lessons:
                if L.get("attendance_status") == "AbsentNotice":
                    absences_ignorees += 1
                    continue
                billable_lessons.append(L)

            total_amount = sum(float(L.get("amount") or 0) for L in billable_lessons)
            if total_amount <= 0:
                continue

            # Skip si déjà créé
            if skip_if_exists and already_exists(fam_id, currency, total_amount, today):
                continue

            total_cents = int(round(total_amount * 100))
            product_name = build_product_name(billable_lessons)

            price = stripe.Price.create(
                unit_amount=total_cents,
                currency=currency,
                product_data={"name": product_name},
            )

            customer_id = None
            if parent_email:
                res = stripe.Customer.list(email=parent_email, limit=1)
                if res.data:
                    customer_id = res.data[0].id

            params = {
                "line_items": [{"price": price.id, "quantity": 1}],
                "customer_creation": "if_required" if customer_id else "always",
                # PAS de on_behalf_of
                # PAS de transfer_data
                # PAS de application_fee_amount
                "restrictions": {"completed_sessions": {"limit": 1}},
                "metadata": {
                    "currency": currency,
                    "family_id": fam_id,
                    "parent_name": parent_name,
                    "parent_email": parent_email,
                    "product_name": product_name,
                    "invoice_date": today,
                    "mode": "no_split",
                },
                "payment_intent_data": {
                    "metadata": {
                        "gross_amount": f"{total_amount:.2f} {currency.upper()}",
                        "invoice_date": today,
                        "product_name": product_name,
                        "mode": "no_split",
                    }
                },
                "after_completion": {"type": "hosted_confirmation"},
            }

            ALLOWED_PM = {"card", "link", "klarna", "twint"}
            pm_types = list(payment_method_types) if payment_method_types else None
            if currency != "chf" and pm_types:
                pm_types = [pm for pm in pm_types if pm != "twint"]
            if pm_types:
                filtered = [pm for pm in pm_types if pm in ALLOWED_PM]
                params["payment_method_types"] = filtered if filtered else ["card"]

            params = {k: v for k, v in params.items() if v is not None}

            link = stripe.PaymentLink.create(**params)

            output_links.append({
                "family_id": fam_id,
                "parent": parent_name,
                "teacher": "— (tout sur compte principal)",
                "currency": currency,
                "students_label": product_name,
                "amount": total_amount,
                "teacher_pay": 0,
                "payment_link": link.url,
                "invoice_date": today,
                "mode": "no_split",
            })

        update(90, "💾 Sauvegarde...")

        os.makedirs(data_dir, exist_ok=True)

        merged = prev if prev else []
        merged.extend(output_links)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)

        if STORAGE_AVAILABLE:
            try:
                save_json("payment_links_output.json", merged, folder="data")
            except Exception:
                pass

        update(100, "✅ Terminé !")

        return {
            "success": True,
            "links_count": len(output_links),
            "total_merged": len(merged),
            "absences_ignorees": absences_ignorees,
            "output_path": output_path,
            "links": output_links[:10],
        }

    except stripe.error.AuthenticationError:
        return {"success": False, "error": "Erreur d'authentification Stripe - Vérifiez la clé API dans secrets_no_prof.yaml"}
    except Exception as e:
        return {"success": False, "error": str(e)}