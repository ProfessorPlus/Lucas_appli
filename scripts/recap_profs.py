"""
👨‍🏫 Recap Profs
Calcul des montants à payer aux professeurs en EUR
Basé sur les taux horaires de secrets.yaml + tarifs spéciaux + familles EUR
"""

import unicodedata
from collections import defaultdict


CHF_TO_EUR = 1.0896  # 1 CHF = 1.0896 EUR

PAYABLE_STATUSES = {"Present", "Unrecorded", "AbsentNoMakeup"}


def norm(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFD", name.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def compute_teacher_recap(data, secrets, familles_euros, tarifs_speciaux):
    """
    Calcule le récap des montants à payer à chaque prof.
    
    Args:
        data: dict des familles (full_output_tb_SIMPLE.json)
        secrets: config YAML
        familles_euros: liste des noms de parents en EUR
        tarifs_speciaux: liste des tarifs spéciaux
    
    Returns:
        dict: {
            "teachers": {teacher_name: {eur, chf_as_eur, nb_lessons, total_hours, details}},
            "grand_total": float,
            "total_lessons": int,
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

    # Compute
    teacher_totals = defaultdict(lambda: {
        "eur": 0.0, "chf_as_eur": 0.0, "nb_lessons": 0,
        "total_hours": 0.0, "details": []
    })

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
                amount_eur = amount_chf * CHF_TO_EUR
                teacher_totals[cfg_key]["chf_as_eur"] += amount_eur
                currency_label = "CHF→EUR"

            teacher_totals[cfg_key]["nb_lessons"] += 1
            teacher_totals[cfg_key]["total_hours"] += hours
            teacher_totals[cfg_key]["details"].append({
                "date": lesson.get("date", ""),
                "student": lesson.get("student", ""),
                "family_parent": parent,
                "currency": currency_label,
                "duration_min": duration,
                "rate": rate,
                "amount_eur": round(amount_eur, 2),
            })

    grand_total = sum(d["eur"] + d["chf_as_eur"] for d in teacher_totals.values())
    total_lessons = sum(d["nb_lessons"] for d in teacher_totals.values())

    return {
        "teachers": dict(teacher_totals),
        "grand_total": round(grand_total, 2),
        "total_lessons": total_lessons,
    }