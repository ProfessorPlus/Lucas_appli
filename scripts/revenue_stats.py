"""
📊 Chiffre d'affaires par mois

Source principale : les archives d'extraction TutorBird (`full_output_tb_YYYY-MM.json`),
écrites à chaque extraction — ce sont les vrais cours facturés du mois.
Repli : payment_links_output.json, pour les mois antérieurs à l'archivage.

Aucune extraction n'est relancée ici : run_extraction écrase l'extraction courante,
on se contente donc de relire les archives déjà sauvegardées.
"""

import json
import os

from scripts.send_payment_reminders import normalize

try:
    from scripts.storage_manager import load_json as storage_load_json
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False

CURRENCY_LABELS = {"EUR": "€", "CHF": "CHF", "AED": "AED"}
SOURCE_LABELS = {"tutorbird": "TutorBird", "liens": "Liens Stripe"}


def _load_data_file(filename, data_dir):
    """Lit un JSON du dossier data (local puis Drive via storage_manager)."""
    if STORAGE_AVAILABLE:
        try:
            content = storage_load_json(filename, "data", default=None)
            if content:
                return content
        except Exception:
            pass

    path = os.path.join(data_dir or "", filename)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass

    return None


def load_month_extraction(month_key, data_dir):
    """Archive TutorBird d'un mois ('2026-09'), ou None si elle n'existe pas."""
    return _load_data_file(f"full_output_tb_{month_key}.json", data_dir)


def load_payment_links(data_dir):
    """Liens de paiement générés (historique cumulé)."""
    return _load_data_file("payment_links_output.json", data_dir) or []


def revenue_from_families(families, euro_parents=None):
    """Totaux par devise d'une extraction TutorBird.

    Mêmes règles que la page d'accueil : les absences signalées ne sont pas
    facturées, et la devise vient de la famille sinon de la liste des familles EUR.
    """
    totals = {}
    counted = 0
    euro_set = {normalize(p) for p in (euro_parents or [])}

    for fam in (families or {}).values():
        lessons = [
            lesson for lesson in fam.get("lessons", [])
            if lesson.get("attendance_status") != "AbsentNotice"
        ]
        amount = sum(float(lesson.get("amount") or 0) for lesson in lessons)
        if amount <= 0:
            continue

        currency = (fam.get("currency") or "").upper()
        if not currency:
            parent = fam.get("parent_name") or fam.get("family_name") or ""
            currency = "EUR" if normalize(parent) in euro_set else "CHF"

        totals[currency] = totals.get(currency, 0.0) + amount
        counted += 1

    return totals, counted


def revenue_from_links(links):
    """CA par mois depuis les liens de paiement, en repli de l'archive TutorBird.

    Déduplique sur la même clé que create_payment_links (famille + prof + devise +
    montant + date) : un lien régénéré à l'identique ne compte pas deux fois, mais
    deux professeurs sur une même famille restent bien distincts.
    """
    months = {}
    seen = set()

    for link in links or []:
        invoice_date = str(link.get("invoice_date") or "").strip()
        if len(invoice_date) < 7:
            continue

        try:
            amount = float(link.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue

        key = (
            str(link.get("family_id", "")),
            str(link.get("teacher", "")).strip().lower(),
            str(link.get("currency", "")).lower(),
            round(amount, 2),
            invoice_date,
        )
        if key in seen:
            continue
        seen.add(key)

        currency = (link.get("currency") or "CHF").upper()
        month = months.setdefault(
            invoice_date[:7], {"totals": {}, "families": set()}
        )
        month["totals"][currency] = month["totals"].get(currency, 0.0) + amount
        month["families"].add(str(link.get("family_id") or link.get("parent") or ""))

    for month in months.values():
        month["families"] = len(month["families"])

    return months


def compute_monthly_revenue(month_keys, data_dir, euro_parents=None, callback=None):
    """CA de chaque mois : archive TutorBird si disponible, sinon liens de paiement.

    L'équivalent EUR est calculé ici une bonne fois pour toutes (au taux du mois
    concerné) : la page peut être re-rendue sans relancer d'appels de change.

    Retourne {'2026-09': {'totals': {...}, 'eur': 3400.0, 'families': 8, 'source': 'tutorbird'}}
    """
    link_revenue = revenue_from_links(load_payment_links(data_dir))
    results = {}

    keys = list(month_keys or [])
    for i, month_key in enumerate(keys):
        if callback:
            callback(int(i / max(len(keys), 1) * 100), f"📊 {month_key}...")

        entry = None
        families = load_month_extraction(month_key, data_dir)
        if families:
            totals, counted = revenue_from_families(families, euro_parents)
            if totals:
                entry = {"totals": totals, "families": counted, "source": "tutorbird"}

        if entry is None:
            fallback = link_revenue.get(month_key)
            if fallback:
                entry = {
                    "totals": fallback["totals"],
                    "families": fallback["families"],
                    "source": "liens",
                }

        if entry is not None:
            entry["eur"] = to_eur_month(entry["totals"], month_key)
            results[month_key] = entry

    if callback:
        callback(100, "✅ CA calculé")

    return results


def to_eur_month(totals, month_key):
    """Équivalent EUR au taux du mois 'AAAA-MM'. Retourne 0.0 si le taux est indisponible."""
    year = month = None
    try:
        year, month = int(str(month_key)[:4]), int(str(month_key)[5:7])
    except (TypeError, ValueError):
        pass

    try:
        return to_eur(totals, year, month)
    except Exception:
        return 0.0


def to_eur(totals, year=None, month=None):
    """Équivalent EUR d'un dict {devise: montant}, au taux du mois demandé si fourni."""
    from scripts.recap_profs import fetch_chf_eur_rate, fetch_fx_rate

    total = 0.0
    for currency, amount in (totals or {}).items():
        if not amount:
            continue
        if currency == "EUR":
            total += amount
        elif currency == "CHF":
            rate, _ = fetch_chf_eur_rate(year, month)
            total += amount * rate
        else:
            rate, _ = fetch_fx_rate(currency, "EUR", year, month)
            total += amount * rate
    return total


def format_totals(totals):
    """'3 200 CHF + 450 €' — devises natives, sans conversion."""
    parts = []
    for currency in sorted(totals or {}):
        amount = totals[currency]
        if amount:
            label = CURRENCY_LABELS.get(currency, currency)
            parts.append(f"{amount:,.0f} {label}".replace(",", " "))
    return " + ".join(parts) if parts else "—"
