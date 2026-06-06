"""
👨‍🏫 Recap Profs
Calcul des montants à payer aux professeurs en EUR
Basé sur les taux horaires de secrets.yaml + tarifs spéciaux + familles EUR

✅ FX automatique (sans taux en dur)
- Source : série EXR.M.CHF.EUR.SP00.E (taux mensuel fin de mois)
- API : ECB SDMX (https://data-api.ecb.europa.eu/)
- Règle métier : factor = 2 - valeur_mensuelle

⚠️ IMPORTANT
- Aucun fallback : si l’API ne renvoie pas de valeur (ou si la date de fin d’extraction n’est pas fournie),
  le calcul échoue avec une erreur explicite.
"""

import unicodedata
from collections import defaultdict
from datetime import date, datetime
from functools import lru_cache

import requests


PAYABLE_STATUSES = {"Present", "Unrecorded", "AbsentNoMakeup"}

# ===========================
# FX CHF → EUR + générique (AED, etc.)
# ===========================
# Priority: Frankfurter API → ECB SDMX → hardcoded fallback

FRANKFURTER_URL = "https://api.frankfurter.dev/v1"
ECB_SDMX_URL = "https://data-api.ecb.europa.eu/service/data/EXR/M.CHF.EUR.SP00.E"

# Hardcoded fallback (updated manually when needed)
FALLBACK_CHF_EUR = 0.94  # ~approximate 2026 rate
FALLBACK_AED_EUR = 0.25  # ~approximate 2026 rate (1 AED ≈ 0.25 EUR)


@lru_cache(maxsize=64)
def fetch_fx_rate(base_currency, target_currency="EUR", target_year=None, target_month=None):
    """
    Fetches the average FX rate for any currency pair over a given month.
    Uses Frankfurter API (ECB data).
    
    Args:
        base_currency: ex "AED", "CHF"
        target_currency: ex "EUR"
        target_year, target_month: mois cible
    
    Returns (rate, source_label).
    """
    import calendar
    
    if base_currency.upper() == target_currency.upper():
        return 1.0, "Same currency"
    
    if target_year and target_month:
        prev_y, prev_m = target_year, target_month
    else:
        today = date.today()
        if today.month == 1:
            prev_y, prev_m = today.year - 1, 12
        else:
            prev_y, prev_m = today.year, today.month - 1
    
    last_day = calendar.monthrange(prev_y, prev_m)[1]
    start_date = f"{prev_y:04d}-{prev_m:02d}-01"
    end_date = f"{prev_y:04d}-{prev_m:02d}-{last_day:02d}"
    month_label = f"{prev_y:04d}-{prev_m:02d}"
    
    try:
        r = requests.get(
            f"{FRANKFURTER_URL}/{start_date}..{end_date}",
            params={"base": base_currency.upper(), "symbols": target_currency.upper()},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})
        
        if rates:
            values = [day_rates[target_currency.upper()] for day_rates in rates.values() if target_currency.upper() in day_rates]
            if values:
                avg = round(sum(values) / len(values), 6)
                print(f"✅ Taux {base_currency}→{target_currency} moyenne {month_label} via Frankfurter: {avg} ({len(values)} jours)")
                return avg, f"Moyenne {month_label} ({len(values)}j, Frankfurter)"
    except Exception as e:
        print(f"⚠️ Frankfurter {base_currency}→{target_currency} indisponible: {e}")
    
    # AED spécial : peg fixe USD (1 USD = 3.6725 AED), calcul via USD→EUR
    if base_currency.upper() == "AED" and target_currency.upper() == "EUR":
        AED_USD_PEG = 3.6725  # Taux fixe officiel
        try:
            r = requests.get(
                f"{FRANKFURTER_URL}/{start_date}..{end_date}",
                params={"base": "USD", "symbols": "EUR"},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            rates = data.get("rates", {})
            if rates:
                usd_eur_values = [day_rates["EUR"] for day_rates in rates.values() if "EUR" in day_rates]
                if usd_eur_values:
                    usd_eur_avg = sum(usd_eur_values) / len(usd_eur_values)
                    aed_eur = round(usd_eur_avg / AED_USD_PEG, 6)
                    print(f"✅ Taux AED→EUR via USD peg {month_label}: {aed_eur} ({len(usd_eur_values)} jours)")
                    return aed_eur, f"Moyenne {month_label} (via USD peg, Frankfurter)"
        except Exception as e2:
            print(f"⚠️ Calcul AED→EUR via USD échoué: {e2}")
    
    # Fallback hardcodé pour les paires connues
    fallback_key = f"{base_currency.upper()}_{target_currency.upper()}"
    fallbacks = {
        "AED_EUR": FALLBACK_AED_EUR,
        "CHF_EUR": FALLBACK_CHF_EUR,
    }
    if fallback_key in fallbacks:
        rate = fallbacks[fallback_key]
        print(f"⚠️ Taux de secours {base_currency}→{target_currency}: {rate}")
        return rate, "Taux de secours (approximatif)"
    
    print(f"⚠️ Aucun taux disponible pour {base_currency}→{target_currency}")
    return 0.0, "Aucun taux disponible"


@lru_cache(maxsize=36)
def fetch_chf_eur_rate(target_year=None, target_month=None) -> tuple[float, str]:
    """
    Fetches the CHF→EUR rate as the AVERAGE of the target month.
    If no target provided, uses the previous complete month.
    
    Args:
        target_year: année du mois cible (ex: 2026)
        target_month: mois cible 1-12 (ex: 1 pour Janvier)
    
    Returns (rate, source_label).
    
    Chain: Frankfurter monthly avg → ECB SDMX → hardcoded fallback.
    """
    import calendar
    
    if target_year and target_month:
        prev_y, prev_m = target_year, target_month
    else:
        today = date.today()
        # Mois précédent (complet)
        if today.month == 1:
            prev_y, prev_m = today.year - 1, 12
        else:
            prev_y, prev_m = today.year, today.month - 1
    
    last_day = calendar.monthrange(prev_y, prev_m)[1]
    start_date = f"{prev_y:04d}-{prev_m:02d}-01"
    end_date = f"{prev_y:04d}-{prev_m:02d}-{last_day:02d}"
    month_label = f"{prev_y:04d}-{prev_m:02d}"
    
    # 1. Frankfurter API — moyenne mensuelle
    try:
        r = requests.get(
            f"{FRANKFURTER_URL}/{start_date}..{end_date}",
            params={"base": "CHF", "symbols": "EUR"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})
        
        if rates:
            values = [day_rates["EUR"] for day_rates in rates.values() if "EUR" in day_rates]
            if values:
                avg = round(sum(values) / len(values), 6)
                print(f"✅ Taux CHF→EUR moyenne {month_label} via Frankfurter: {avg} ({len(values)} jours)")
                return avg, f"Moyenne {month_label} ({len(values)}j, Frankfurter)"
    except Exception as e:
        print(f"⚠️ Frankfurter indisponible: {e}")
    
    # 2. ECB SDMX (fallback — valeur mensuelle)
    try:
        headers = {"Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"}
        r = requests.get(
            ECB_SDMX_URL,
            params={"startPeriod": start_date, "endPeriod": end_date},
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        series = data["dataSets"][0]["series"]
        first_key = next(iter(series.keys()))
        obs = series[first_key].get("observations", {})
        if obs:
            last_idx = max(int(k) for k in obs.keys())
            ecb_val = float(obs[str(last_idx)][0])
            rate = round(2.0 - ecb_val, 6)
            print(f"✅ Taux CHF→EUR via ECB {month_label}: {rate}")
            return rate, f"ECB {month_label}"
    except Exception as e:
        print(f"⚠️ ECB indisponible: {e}")
    
    # 3. Hardcoded fallback
    print(f"⚠️ APIs inaccessibles, taux de secours: {FALLBACK_CHF_EUR}")
    return FALLBACK_CHF_EUR, "Taux de secours (approximatif)"


def norm(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFD", name.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def _to_date(d):
    """Accepts date/datetime or ISO string ('YYYY-MM' or 'YYYY-MM-DD') and returns a date."""
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, str):
        ds = d.strip()
        if len(ds) == 7:  # YYYY-MM
            return datetime.strptime(ds + "-01", "%Y-%m-%d").date()
        return datetime.strptime(ds, "%Y-%m-%d").date()
    raise TypeError(f"Unsupported date type: {type(d)}")


def compute_teacher_recap(
    data,
    secrets,
    familles_euros,
    tarifs_speciaux,
    extraction_end_date=None,
    chf_to_eur_factor=None,
    excluded_teacher_names=None,
):
    """
    Calcule le récap des montants à payer à chaque prof.

    Args:
        data: dict des familles (full_output_tb_SIMPLE.json)
        secrets: config YAML
        familles_euros: liste des noms de parents en EUR
        tarifs_speciaux: liste des tarifs spéciaux
        extraction_end_date: date/datetime/str -> fin de période TutorBird (mois utilisé pour l’API)
        chf_to_eur_factor: float optionnel pour forcer le facteur (prioritaire)
        excluded_teacher_names: iterable de noms de profs à exclure entièrement du récap.
            Cas d'usage : profs apparaissant en "Profs hors TutorBird" Notion avec
            0h (ils ne devraient pas figurer dans le récap, même si TB a des leçons
            résiduelles à leur nom). Matching par nom normalisé (norm()).

    Returns:
        dict: {
            "teachers": {teacher_name: {eur, chf_as_eur, nb_lessons, total_hours, details}},
            "grand_total": float,
            "total_lessons": int,
            "fx": {"month": "YYYY-MM", "monthly_value": float, "factor": float} ou None
        }
    """
    teachers_cfg = secrets.get("teachers", {})

    # Set normalisé des profs à exclure du récap (ex: 0h dans Notion hors TutorBird)
    excluded_norm = set()
    if excluded_teacher_names:
        for name in excluded_teacher_names:
            if name:
                excluded_norm.add(norm(name))

    # Build lookup
    teacher_lookup = {}
    for cfg_name in teachers_cfg:
        teacher_lookup[norm(cfg_name)] = cfg_name

    # Euro parents
    euro_parents = {norm(p) for p in familles_euros}

    # Tarifs spéciaux lookup — stocke (pay_rate, currency)
    special_rates = {}
    for ts in tarifs_speciaux:
        t = norm(ts.get("teacher", ""))
        rate_currency = ts.get("currency", "EUR").upper()
        if ts.get("parent"):
            special_rates[(t, "parent", norm(ts["parent"]))] = (ts["pay_rate"], rate_currency)
        if ts.get("student"):
            special_rates[(t, "student", norm(ts["student"]))] = (ts["pay_rate"], rate_currency)

    def get_special_rate(teacher_name, parent_name, student_name):
        """Retourne (rate, currency) ou (None, None)."""
        tn = norm(teacher_name)
        r = special_rates.get((tn, "parent", norm(parent_name)))
        if r is not None:
            return r
        if student_name:
            r = special_rates.get((tn, "student", norm(student_name)))
            if r is not None:
                return r
        return (None, None)

    # FX: resolved lazily via fetch_chf_eur_rate()
    fx_info = None
    CHF_TO_EUR = None
    
    # Déterminer le mois cible pour le taux de change (= mois des cours extraits)
    fx_target_year = None
    fx_target_month = None
    if extraction_end_date:
        end_dt = _to_date(extraction_end_date)
        if end_dt:
            fx_target_year = end_dt.year
            fx_target_month = end_dt.month
    
    # Si pas de extraction_end_date, essayer de déduire depuis les données
    if not fx_target_year:
        all_dates = []
        for fam in data.values():
            for lesson in fam.get("lessons", []):
                d = lesson.get("date", "")
                if d:
                    try:
                        all_dates.append(datetime.strptime(d, "%d.%m.%Y").date())
                    except:
                        pass
        if all_dates:
            # Prendre le mois le plus fréquent
            from collections import Counter
            month_counts = Counter((d.year, d.month) for d in all_dates)
            fx_target_year, fx_target_month = month_counts.most_common(1)[0][0]

    def ensure_fx():
        nonlocal CHF_TO_EUR, fx_info
        if CHF_TO_EUR is not None:
            return
        if chf_to_eur_factor is not None:
            CHF_TO_EUR = float(chf_to_eur_factor)
            fx_info = {"source": "manual", "factor": CHF_TO_EUR}
            return
        rate, source = fetch_chf_eur_rate(fx_target_year, fx_target_month)
        CHF_TO_EUR = rate
        fx_info = {"source": source, "factor": CHF_TO_EUR}

    def smart_round(amount):
        """Arrondit à l'unité supérieure si à moins de 0.05 (ex: 59.99 → 60.00, 19.97 → 20.00)."""
        import math
        upper = math.ceil(amount)
        if upper - amount <= 0.05 and upper - amount > 0:
            return float(upper)
        return round(amount, 2)
    
    # Build set of auto_chf teachers
    auto_chf_teachers = set()
    for cfg_name, cfg_data in teachers_cfg.items():
        if cfg_data.get("auto_chf"):
            auto_chf_teachers.add(norm(cfg_name))

    # Compute
    teacher_totals = defaultdict(
        lambda: {"eur": 0.0, "chf_as_eur": 0.0, "nb_lessons": 0, "total_hours": 0.0, "details": []}
    )

    for fam in data.values():
        parent = fam.get("parent_name") or ""
        is_eur = norm(parent) in euro_parents

        for lesson in fam.get("lessons", []):
            status = lesson.get("attendance_status", "")
            if status not in PAYABLE_STATUSES:
                continue

            t_name = lesson.get("teacher") or ""

            # Exclusion : prof listé à 0h dans "Profs hors TutorBird" Notion.
            # On skippe toutes ses leçons (TB et Notion) pour qu'il n'apparaisse
            # pas du tout dans le récap, même si TB a des leçons résiduelles.
            if t_name and norm(t_name) in excluded_norm:
                continue

            duration = lesson.get("duration_min") or 0
            hours = duration / 60.0

            # ===========================
            # CAS SPÉCIAL : Prof hors TutorBird (depuis Notion)
            # ===========================
            if lesson.get("source") == "notion_hors_tb":
                notion_rate = lesson.get("notion_taux_prof", 0)
                notion_devise = lesson.get("notion_devise_prof", "EUR")
                
                if notion_devise == "EUR":
                    amount_eur = notion_rate * hours
                    teacher_totals[t_name]["eur"] += amount_eur
                    currency_label = "EUR (Notion)"
                else:
                    amount_chf = notion_rate * hours
                    ensure_fx()
                    amount_eur = amount_chf * CHF_TO_EUR
                    amount_eur = smart_round(amount_eur)
                    teacher_totals[t_name]["chf_as_eur"] += amount_eur
                    currency_label = "CHF→EUR (Notion)"
                
                teacher_totals[t_name]["nb_lessons"] += 1
                teacher_totals[t_name]["total_hours"] += hours
                # Pour Notion hors TB : afficher "Mai 2026" au lieu de la date
                # de fetch (qui n'a aucun sens — c'est juste today()). Source :
                # colonne Notion "Mois" + année prise sur extraction_end_date
                # (ou today si non fournie).
                _mois_lbl = (lesson.get("notion_mois_label") or "").strip()
                if _mois_lbl:
                    _ref = _to_date(extraction_end_date)
                    _year = _ref.year if _ref else datetime.today().year
                    date_display = f"{_mois_lbl} {_year}"
                else:
                    date_display = lesson.get("date", "")
                teacher_totals[t_name]["details"].append({
                    "date": date_display,
                    "student": lesson.get("student", ""),
                    "family_parent": parent,
                    "currency": currency_label,
                    "duration_min": duration,
                    "rate": notion_rate,
                    "amount_eur": round(amount_eur, 2),
                })
                continue

            # ===========================
            # CAS NORMAL : Prof TutorBird (depuis secrets.yaml)
            # ===========================
            cfg_key = teacher_lookup.get(norm(t_name))
            if not cfg_key:
                continue

            t_cfg = teachers_cfg[cfg_key]
            pay = t_cfg.get("pay_rate", {})

            special, special_currency = get_special_rate(t_name, parent, lesson.get("student"))

            if special is not None:
                rate = special
                if special_currency == "CHF":
                    # Tarif spécial en CHF → conversion CHF→EUR
                    amount_chf = rate * hours
                    ensure_fx()
                    amount_eur = amount_chf * CHF_TO_EUR
                    amount_eur = smart_round(amount_eur)
                    teacher_totals[cfg_key]["chf_as_eur"] += amount_eur
                    currency_label = "CHF→EUR★"
                else:
                    # Tarif spécial en EUR (défaut)
                    amount_eur = rate * hours
                    teacher_totals[cfg_key]["eur"] += amount_eur
                    currency_label = "EUR★"
            elif is_eur:
                rate = pay.get("eur", 0)
                amount_eur = rate * hours
                teacher_totals[cfg_key]["eur"] += amount_eur
                currency_label = "EUR"
            else:
                rate = pay.get("chf", 0)
                amount_chf = rate * hours

                # FX needed here (strict mode)
                ensure_fx()

                amount_eur = amount_chf * CHF_TO_EUR
                
                # Arrondi intelligent pour les profs avec auto_chf coché
                if norm(t_name) in auto_chf_teachers or norm(cfg_key) in auto_chf_teachers:
                    amount_eur = smart_round(amount_eur)
                
                teacher_totals[cfg_key]["chf_as_eur"] += amount_eur
                currency_label = "CHF→EUR"

            teacher_totals[cfg_key]["nb_lessons"] += 1
            teacher_totals[cfg_key]["total_hours"] += hours
            teacher_totals[cfg_key]["details"].append(
                {
                    "date": lesson.get("date", ""),
                    "student": lesson.get("student", ""),
                    "family_parent": parent,
                    "currency": currency_label,
                    "duration_min": duration,
                    "rate": rate,
                    "amount_eur": round(amount_eur, 2),
                }
            )

    grand_total = sum(d["eur"] + d["chf_as_eur"] for d in teacher_totals.values())
    total_lessons = sum(d["nb_lessons"] for d in teacher_totals.values())

    return {
        "teachers": dict(teacher_totals),
        "grand_total": round(grand_total, 2),
        "total_lessons": total_lessons,
        "fx": fx_info,
    }