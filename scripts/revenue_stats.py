"""
📊 Chiffre d'affaires par mois

Source : payment_links_output.json — le seul historique qui conserve montant + devise
+ date de facturation. La génération de factures n'écrit aucun récapitulatif de totaux,
et l'extraction courante ne couvre que le mois en cours.
"""

import json
import os

try:
    from scripts.storage_manager import load_json as storage_load_json
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False

CURRENCY_LABELS = {"EUR": "€", "CHF": "CHF", "AED": "AED"}


def load_payment_links(data_dir):
    """Charge les liens de paiement générés (Drive en priorité, puis fichier local)."""
    links = None

    if STORAGE_AVAILABLE:
        try:
            links = storage_load_json("payment_links_output.json", "data", default=None)
        except Exception:
            links = None

    if links is None:
        path = os.path.join(data_dir or "", "payment_links_output.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    links = json.load(fh)
            except Exception:
                links = None

    return links or []


def compute_monthly_revenue(links):
    """CA par mois : {'2026-09': {'totals': {'CHF': 3200.0}, 'links': 12, 'families': 8}}.

    Déduplique sur la même clé que create_payment_links (famille + prof + devise +
    montant + date) : un lien régénéré à l'identique ne doit pas compter deux fois.
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
            invoice_date[:7], {"totals": {}, "links": 0, "families": set()}
        )
        month["totals"][currency] = month["totals"].get(currency, 0.0) + amount
        month["links"] += 1
        month["families"].add(str(link.get("family_id") or link.get("parent") or ""))

    for month in months.values():
        month["families"] = len(month["families"])

    return months


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
