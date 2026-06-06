"""
📋 Fetch Notion - Profs hors TutorBird
Lit la base de données Notion "Profs hors Tutorbird" et retourne les données
dans un format compatible avec le reste du pipeline (familles/leçons).

Colonnes Notion attendues :
- Famille (title)
- Professeur (rich_text)
- Élève (rich_text)
- Devise client (rich_text) - "EUR" ou "CHF"
- Taux horaire client (number)
- Taux horaire prof (number)
- Devise prof (rich_text)
- Heures faites (number)
- email client (email)
"""

import re
import time as _time
import requests
from datetime import datetime


# Pattern : "Ajouter 15 euros de frais de déplacement", insensible casse/accents.
# Captures la valeur numérique (int ou décimal avec , ou .). Cherché dans la
# colonne Notion "Détails heures" pour ajouter un supplément au total facturé.
_FRAIS_DEP_PATTERN = re.compile(
    r"\bajouter\s+(\d+(?:[.,]\d+)?)\s*(?:eur(?:os?)?|€)\s+(?:de\s+)?frais\s+de\s+d[ée]placement\b",
    re.IGNORECASE,
)


REQUEST_DELAY = 0.25


def _notion_query(token, database_id):
    """Query toutes les lignes d'une database Notion."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    
    all_rows = []
    cursor = None
    
    while True:
        payload = {}
        if cursor:
            payload["start_cursor"] = cursor
        
        _time.sleep(REQUEST_DELAY)
        r = requests.post(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            headers=headers,
            json=payload,
            timeout=30,
        )
        
        if r.status_code != 200:
            raise RuntimeError(f"Erreur Notion API {r.status_code}: {r.text[:200]}")
        
        data = r.json()
        all_rows.extend(data.get("results", []))
        
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    
    return all_rows


def _get_text(prop, prop_type="rich_text"):
    """Extrait le texte d'une propriété Notion."""
    if prop_type == "title":
        items = prop.get("title", [])
    elif prop_type == "rich_text":
        items = prop.get("rich_text", [])
    else:
        return ""
    
    if items:
        return items[0].get("plain_text", "").strip()
    return ""


def _get_number(prop):
    """Extrait un nombre d'une propriété Notion."""
    val = prop.get("number")
    return float(val) if val is not None else 0.0


def _get_email(prop):
    """Extrait un email d'une propriété Notion."""
    return prop.get("email") or ""


def fetch_notion_profs(secrets):
    """
    Lit la base Notion "Profs hors Tutorbird" et retourne la liste des entrées.
    
    Args:
        secrets: dict config (avec notion.token et notion.profs_hors_tutorbird_database_id)
    
    Returns:
        dict: {
            "success": bool,
            "entries": [
                {
                    "page_id": str,
                    "famille": str,
                    "professeur": str,
                    "eleve": str,
                    "devise_client": str,
                    "taux_horaire_client": float,
                    "taux_horaire_prof": float,
                    "devise_prof": str,
                    "heures_faites": float,
                    "email_client": str,
                }
            ],
            "error": str
        }
    """
    try:
        notion_cfg = secrets.get("notion", {})
        token = notion_cfg.get("token")
        db_id = notion_cfg.get("profs_hors_tutorbird_database_id")
        
        if not token:
            return {"success": False, "entries": [], "error": "Token Notion manquant"}
        if not db_id:
            return {"success": False, "entries": [], "error": "profs_hors_tutorbird_database_id manquant dans secrets.yaml"}
        
        rows = _notion_query(token, db_id)
        
        entries = []
        for row in rows:
            p = row.get("properties", {})
            
            famille = _get_text(p.get("Famille", {}), "title")
            professeur = _get_text(p.get("Professeur", {}), "rich_text")
            eleve = _get_text(p.get("Élève", {}), "rich_text")
            devise_client = _get_text(p.get("Devise client", {}), "rich_text") or "EUR"
            taux_horaire_client = _get_number(p.get("Taux horaire client", {}))
            taux_horaire_prof = _get_number(p.get("Taux horaire prof", {}))
            devise_prof = _get_text(p.get("Devise prof", {}), "rich_text") or "EUR"
            heures_faites = _get_number(p.get("Heures faites", {}))
            email_client = _get_email(p.get("email client", {}))
            email_prof = _get_email(p.get("email prof", {}))
            details_heures = _get_text(p.get("Détails heures", {}), "rich_text")
            langue = _get_text(p.get("Langue", {}), "rich_text") or _get_text(p.get("Langue", {}), "select") or ""
            language = "en" if str(langue).strip().lower() in {"anglais", "english", "en"} else "fr"
            # Colonne 'Mois' (texte ou select) : nom du mois durant lequel les cours
            # ont été effectués, ex 'Mai'. Utilisée sur la fiche de paie pour afficher
            # 'Mai 2026' au lieu de la date de fetch (qui n'a aucun sens pour Notion).
            mois_label = (
                _get_text(p.get("Mois", {}), "rich_text")
                or _get_text(p.get("Mois", {}), "select")
                or ""
            )

            if not famille and not professeur:
                continue

            entries.append({
                "page_id": row["id"],
                "famille": famille,
                "professeur": professeur,
                "eleve": eleve or famille,
                "devise_client": devise_client.upper(),
                "taux_horaire_client": taux_horaire_client,
                "taux_horaire_prof": taux_horaire_prof,
                "devise_prof": devise_prof.upper(),
                "heures_faites": heures_faites,
                "email_client": email_client,
                "email_prof": email_prof,
                "details_heures": details_heures,
                "language": language,
                "mois_label": mois_label,
            })
        
        return {"success": True, "entries": entries, "error": None}
    
    except Exception as e:
        return {"success": False, "entries": [], "error": str(e)}


def convert_notion_profs_to_families(entries, selected_profs=None):
    """
    Convertit les entrées Notion en format compatible full_output_tb_SIMPLE.json.
    
    FUSIONNE les entrées de même famille (ex: Carole avec 2 profs → 1 famille, 2 leçons).
    
    Args:
        entries: liste d'entrées (depuis fetch_notion_profs)
        selected_profs: set de noms de profs sélectionnés (None = tous)
    
    Returns:
        dict: {family_id: family_data} au même format que TutorBird
    """
    families = {}
    
    for entry in entries:
        prof = entry["professeur"]
        
        # Filtrer par profs sélectionnés
        if selected_profs is not None and prof not in selected_profs:
            continue
        
        heures = entry["heures_faites"]
        if heures <= 0:
            continue
        
        taux_client = entry["taux_horaire_client"]
        montant_total = round(taux_client * heures, 2)
        
        famille = entry["famille"]
        # ID basé sur la famille uniquement (pour fusionner les entrées multi-profs)
        safe_id = f"notion_{famille}".replace(" ", "_").lower()
        
        lesson = {
            "date": datetime.today().strftime("%d.%m.%Y"),
            "time": "00:00",
            "student": entry["eleve"],
            "teacher": prof,
            "duration_min": int(heures * 60),
            "amount": montant_total,
            "attendance_status": "Present",
            "source": "notion_hors_tb",
            "notion_taux_prof": entry["taux_horaire_prof"],
            "notion_devise_prof": entry["devise_prof"],
            "notion_devise_client": entry["devise_client"],
            "notion_taux_client": taux_client,
            "notion_details_heures": entry.get("details_heures", ""),
            "notion_mois_label": entry.get("mois_label", ""),
        }
        
        if safe_id in families:
            # Famille déjà existante → ajouter la leçon
            families[safe_id]["lessons"].append(lesson)
            families[safe_id]["total_courses"] += montant_total
        else:
            families[safe_id] = {
                "family_id": safe_id,
                "family_name": famille,
                "parent_name": famille,
                "parent_email": entry["email_client"],
                "lessons": [lesson],
                "total_courses": montant_total,
                "source": "notion_hors_tb",
                "currency": entry["devise_client"].lower(),
                "language": entry.get("language", "fr"),
            }

        # Frais de déplacement : parsing "Ajouter X euros de frais de déplacement"
        # dans la colonne Notion "Détails heures". Si match, on ajoute une
        # leçon-supplément distincte (visible en ligne dédiée sur le PDF,
        # comprise dans le total facturé et dans le lien Stripe).
        details_str = entry.get("details_heures", "") or ""
        m_frais = _FRAIS_DEP_PATTERN.search(details_str)
        if m_frais:
            try:
                frais_amount = float(m_frais.group(1).replace(",", "."))
            except ValueError:
                frais_amount = 0.0
            if frais_amount > 0:
                frais_lesson = {
                    "date": datetime.today().strftime("%d.%m.%Y"),
                    "time": "00:00",
                    "student": entry["eleve"],
                    "teacher": prof,
                    "duration_min": 0,
                    "amount": frais_amount,
                    "attendance_status": "Present",
                    "source": "notion_hors_tb",
                    "is_fee": True,
                    "description_override": "Frais de déplacement",
                    "notion_taux_prof": 0,
                    "notion_devise_prof": entry["devise_prof"],
                    "notion_devise_client": entry["devise_client"],
                    "notion_taux_client": 0,
                    "notion_details_heures": details_str,
                    "notion_mois_label": entry.get("mois_label", ""),
                }
                families[safe_id]["lessons"].append(frais_lesson)
                families[safe_id]["total_courses"] += frais_amount

    return families