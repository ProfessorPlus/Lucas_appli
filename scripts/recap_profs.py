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

# ECB SDMX endpoint for: EXR.M.CHF.EUR.SP00.E
ECB_SDMX_URL = "https://data-api.ecb.europa.eu/service/data/EXR/M.CHF.EUR.SP00.E"


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


def _month_start_end(y: int, m: int) -> tuple[str, str]:
    # ECB accepts endPeriod with day=31 even for shorter months.
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-31"


@lru_cache(maxsize=36)
def fetch_chf_eur_monthly_value(y: int, m: int) -> float:
    """
    Returns the monthly end-of-period CHF/EUR value for the given year/month
    from the ECB SDMX API (EXR.M.CHF.EUR.SP00.E).
    """
    start, end = _month_start_end(y, m)
    headers = {"Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"}

    r = requests.get(
        ECB_SDMX_URL,
        params={"startPeriod": start, "endPeriod": end},
        headers=headers,
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()

    series = data["dataSets"][0]["series"]
    first_key = next(iter(series.keys()))
    obs = series[first_key].get("observations", {})
    if not obs:
        raise RuntimeError(f"Aucune valeur API trouvée pour CHF/EUR sur {y:04d}-{m:02d}.")

    # last observation within range
    last_idx = max(int(k) for k in obs.keys())
    value = obs[str(last_idx)][0]
    return float(value)


def compute_chf_to_eur_factor(extraction_end_date) -> float:
    """
    Option 1 (rigoureuse) : utilise le mois de la date de fin d'extraction TutorBird.
    Règle métier : factor = 2 - valeur_mensuelle.
    """
    d = _to_date(extraction_end_date)
    if d is None:
        raise RuntimeError(
            "Aucune valeur API trouvée : 'extraction_end_date' est manquant "
            "(impossible de déterminer le mois pour CHF→EUR)."
        )
    v = fetch_chf_eur_monthly_value(d.year, d.month)
    return round(2.0 - v, 6)


def compute_teacher_recap(
    data,
    secrets,
    familles_euros,
    tarifs_speciaux,
    extraction_end_date=None,
    chf_to_eur_factor=None,
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

    Returns:
        dict: {
            "teachers": {teacher_name: {eur, chf_as_eur, nb_lessons, total_hours, details}},
            "grand_total": float,
            "total_lessons": int,
            "fx": {"month": "YYYY-MM", "monthly_value": float, "factor": float} ou None
        }
    """
    teachers_cfg = secrets.get("teachers", {})

    # Build lookup
    teacher_lookup = {}
    for cfg_name in teachers_cfg:
        teacher_lookup[norm(cfg_name)] = cfg_name

    # Euro parents
    euro_parents = {norm(p) for p in familles_euros}

    # Tarifs spéciaux lookup
    special_rates = {}
    for ts in tarifs_speciaux:
        t = norm(ts.get("teacher", ""))
        if ts.get("parent"):
            special_rates[(t, "parent", norm(ts["parent"]))] = ts["pay_rate"]
        if ts.get("student"):
            special_rates[(t, "student", norm(ts["student"]))] = ts["pay_rate"]

    def get_special_rate(teacher_name, parent_name, student_name):
        tn = norm(teacher_name)
        r = special_rates.get((tn, "parent", norm(parent_name)))
        if r is not None:
            return r
        if student_name:
            r = special_rates.get((tn, "student", norm(student_name)))
            if r is not None:
                return r
        return None

    # We'll resolve FX only if needed (i.e., we actually encounter CHF lessons),
    # BUT without fallback: if needed and API/date missing => error.
    fx_info = None
    CHF_TO_EUR = None

    def ensure_fx():
        nonlocal CHF_TO_EUR, fx_info
        if CHF_TO_EUR is not None:
            return
        if chf_to_eur_factor is not None:
            CHF_TO_EUR = float(chf_to_eur_factor)
            fx_info = {"month": None, "monthly_value": None, "factor": CHF_TO_EUR}
            return
        d = _to_date(extraction_end_date)
        if d is None:
            raise RuntimeError(
                "Aucune valeur API trouvée : impossible de convertir CHF→EUR car "
                "'extraction_end_date' n'a pas été fourni."
            )
        monthly_value = fetch_chf_eur_monthly_value(d.year, d.month)
        CHF_TO_EUR = round(2.0 - monthly_value, 6)
        fx_info = {"month": f"{d.year:04d}-{d.month:02d}", "monthly_value": monthly_value, "factor": CHF_TO_EUR}

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
            duration = lesson.get("duration_min") or 0
            hours = duration / 60.0

            cfg_key = teacher_lookup.get(norm(t_name))
            if not cfg_key:
                continue

            t_cfg = teachers_cfg[cfg_key]
            pay = t_cfg.get("pay_rate", {})

            special = get_special_rate(t_name, parent, lesson.get("student"))

            if special is not None:
                rate = special
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
