"""
📥 Extract TutorBird
Extraction des leçons depuis l'API TutorBird
VERSION CLOUD - Compatible Streamlit Cloud avec Google Drive
"""

import os
import json
import re
import unicodedata
import requests
from datetime import datetime

# Import du storage manager pour compatibilité cloud
try:
    from scripts.storage_manager import save_json
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False


def _normalize_name(name):
    """Normalise un nom pour matching : minuscules, sans accents, mots triés."""
    if not isinstance(name, str):
        return ""
    s = name.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("-", " ").replace(",", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # Trier les mots pour que "Fatou Thiam" == "Thiam Fatou"
    return " ".join(sorted(s.split()))


def run_extraction(secrets, start_date, end_date, start_time, end_time, data_dir, callback=None, notion_families=None):
    """
    Extrait les leçons de TutorBird pour une période donnée.
    
    Args:
        secrets: Configuration YAML chargée
        start_date: Date de début (date)
        end_date: Date de fin (date)
        start_time: Heure de début (time)
        end_time: Heure de fin (time)
        data_dir: Dossier pour sauvegarder le JSON
        callback: Fonction callback(progress, message) pour UI
    
    Returns:
        dict: {"success": bool, "families": int, "lessons": int, "amount": float, "error": str}
    """
    
    def update(progress, message):
        if callback:
            callback(progress, message)
    
    try:
        TB_BASE = "https://api.tutorbird.com/v1"
        TB_API_KEY = secrets["tutorbird"]["api_key"]
        HEADERS = {"Authorization": f"Bearer {TB_API_KEY}", "Content-Type": "application/json"}
        
        # Combiner date + heure
        start_dt = datetime.combine(start_date, start_time)
        end_dt = datetime.combine(end_date, end_time)
        
        # ===============================
        # EXTRACTION DES ÉTUDIANTS
        # ===============================
        update(10, "📚 Récupération des étudiants...")
        
        r = requests.get(f"{TB_BASE}/students", headers=HEADERS, timeout=30)
        if not r.ok:
            return {"success": False, "error": f"Erreur API students: {r.status_code}"}
        
        students_raw = r.json().get("ItemSubset") or r.json().get("Items") or r.json()
        students = {}
        for s in students_raw:
            students[s["ID"]] = {
                "name": s.get("Name"),
                "family": s.get("FamilyID"),
                "family_name": s.get("FamilyName"),
            }
        
        # ===============================
        # EXTRACTION DES PARENTS
        # ===============================
        update(30, "👨‍👩‍👧 Récupération des parents...")
        
        r = requests.get(f"{TB_BASE}/parents", headers=HEADERS, timeout=30)
        if not r.ok:
            return {"success": False, "error": f"Erreur API parents: {r.status_code}"}
        
        parents_raw = r.json().get("ItemSubset") or r.json().get("Items") or r.json()
        parents = {}
        for p in parents_raw:
            parents.setdefault(p["FamilyID"], []).append(p)
        
        # ===============================
        # EXTRACTION DES EMAILS PROFS
        # ===============================
        update(40, "👨‍🏫 Récupération des emails professeurs...")
        
        teacher_emails = {}
        try:
            # Headers spécifiques requis par l'API TutorBird pour /teachers
            teacher_headers = {
                "Authorization": f"Bearer {TB_API_KEY}",
                "Content-Type": "application/json",
                "x-schoolbox-client-version": "1494",
                "x-schoolbox-version": "main",
                "origin": "https://app.tutorbird.com",
            }
            r = requests.get(
                f"{TB_BASE}/teachers",
                headers=teacher_headers,
                params={"orderby": "FullName"},
                timeout=30,
            )
            if r.ok:
                teachers_raw = r.json().get("ItemSubset") or r.json().get("Items") or r.json()
                if isinstance(teachers_raw, list):
                    for t in teachers_raw:
                        # FullName est le champ principal, Name en fallback
                        t_name = t.get("FullName") or t.get("Name") or ""
                        t_email = ""
                        email_obj = t.get("Email")
                        if isinstance(email_obj, dict):
                            t_email = email_obj.get("EmailAddress", "")
                        elif isinstance(email_obj, str):
                            t_email = email_obj
                        if t_name and t_email:
                            teacher_emails[t_name] = t_email
                    print(f"📧 {len(teacher_emails)} emails profs récupérés depuis TutorBird")
            else:
                print(f"⚠️ API /teachers non disponible ({r.status_code}) — les emails profs ne seront pas extraits")
        except Exception as e:
            print(f"⚠️ Erreur extraction emails profs: {e}")
        
        # Fonction pour choisir le bon parent
        def choose_parent(fam_id):
            plist = parents.get(fam_id, [])
            if not plist:
                return None, None
            
            def email_of(p):
                e = p.get("Email") or {}
                return e.get("EmailAddress")
            
            # Parent préféré avec email
            for p in plist:
                if p.get("IsPreferredInvoiceRecipient") and email_of(p):
                    return f"{p['LastName']} {p['FirstName']}", email_of(p)
            
            # Sinon n'importe quel parent avec email
            for p in plist:
                if email_of(p):
                    return f"{p['LastName']} {p['FirstName']}", email_of(p)
            
            # Sinon premier parent
            p = plist[0]
            return f"{p['LastName']} {p['FirstName']}", email_of(p)
        
        # ===============================
        # EXTRACTION DES LEÇONS
        # ===============================
        update(50, "📖 Récupération des leçons...")
        
        r = requests.get(
            f"{TB_BASE}/attendance",
            headers=HEADERS,
            params={
                "startDate": start_date.strftime("%Y-%m-%d"),
                "endDate": end_date.strftime("%Y-%m-%d")
            },
            timeout=30
        )
        if not r.ok:
            return {"success": False, "error": f"Erreur API attendance: {r.status_code}"}
        
        lessons_raw = r.json().get("ItemSubset") or r.json().get("Items") or r.json()
        
        # ===============================
        # TRAITEMENT DES DONNÉES
        # ===============================
        update(70, "🔄 Traitement des données...")
        
        families = {}
        
        for L in lessons_raw:
            dt_str = L.get("EventStartDate")
            if not dt_str:
                continue
            
            dt = datetime.fromisoformat(dt_str)
            
            # Filtrer par période exacte (avec heures)
            if not (start_dt <= dt <= end_dt):
                continue
            
            sid = (L.get("Student") or {}).get("ID")
            s_info = students.get(sid, {})
            fam_id = s_info.get("family")
            
            if not fam_id:
                continue
            
            # Créer la famille si elle n'existe pas
            if fam_id not in families:
                pname, pemail = choose_parent(fam_id)
                families[fam_id] = {
                    "family_id": fam_id,
                    "family_name": s_info.get("family_name"),
                    "parent_name": pname,
                    "parent_email": pemail,
                    "lessons": [],
                    "total_courses": 0.0,
                }
            
            amount = float(L.get("OriginalChargeAmount") or 0)
            
            # Ajouter la leçon avec TOUS les champs importants
            families[fam_id]["lessons"].append({
                "date": dt.strftime("%d.%m.%Y"),
                "time": dt.strftime("%H:%M"),
                "student": (L.get("Student") or {}).get("Name"),
                "teacher": (L.get("Teacher") or {}).get("Name"),
                "duration_min": L.get("EventDuration"),
                "amount": amount,
                "attendance_status": L.get("AttendanceStatus"),
            })
            
            families[fam_id]["total_courses"] += amount
        
        # ===============================
        # MERGE PROFS HORS TUTORBIRD (depuis Notion)
        # ===============================
        notion_count = 0
        notion_merged_into_tb = 0
        if notion_families:
            update(85, "📋 Ajout des profs hors TutorBird...")
            
            # Construire un index de noms normalisés → fam_id TutorBird
            tb_name_index = {}
            for tb_fam_id, tb_fam in families.items():
                parent = tb_fam.get("parent_name") or tb_fam.get("family_name") or ""
                norm_key = _normalize_name(parent)
                if norm_key:
                    tb_name_index[norm_key] = tb_fam_id
            
            for fam_id, fam_data in notion_families.items():
                notion_parent = fam_data.get("parent_name") or fam_data.get("family_name") or ""
                notion_norm = _normalize_name(notion_parent)
                
                # 1. Match exact par fam_id
                if fam_id in families:
                    families[fam_id]["lessons"].extend(fam_data.get("lessons", []))
                    families[fam_id]["total_courses"] += fam_data.get("total_courses", 0)
                    # Appliquer la devise Notion si définie
                    notion_currency = fam_data.get("currency", "")
                    if notion_currency:
                        families[fam_id]["currency"] = notion_currency
                    notion_count += 1
                    notion_merged_into_tb += 1
                    print(f"  🔗 Notion fusionné (id exact) : {notion_parent} → {fam_id}")
                    continue
                
                # 2. Match par nom normalisé (ex: "Fatou Thiam" ↔ "Thiam Fatou")
                matched_tb_id = tb_name_index.get(notion_norm)
                if matched_tb_id:
                    families[matched_tb_id]["lessons"].extend(fam_data.get("lessons", []))
                    families[matched_tb_id]["total_courses"] += fam_data.get("total_courses", 0)
                    # Appliquer la devise Notion (elle prime sur TutorBird)
                    notion_currency = fam_data.get("currency", "")
                    if notion_currency:
                        families[matched_tb_id]["currency"] = notion_currency
                    # Appliquer la langue Notion si définie
                    notion_lang = fam_data.get("language")
                    if notion_lang:
                        families[matched_tb_id]["language"] = notion_lang
                    notion_count += 1
                    notion_merged_into_tb += 1
                    tb_parent = families[matched_tb_id].get("parent_name", "")
                    print(f"  🔗 Notion fusionné (nom) : {notion_parent} → {tb_parent} ({matched_tb_id})")
                    continue
                
                # 3. Pas de match → nouvelle famille (100% Notion)
                families[fam_id] = fam_data
                notion_count += 1
                print(f"  ➕ Notion nouvelle famille : {notion_parent} ({fam_id})")
            
            if notion_merged_into_tb > 0:
                print(f"📋 {notion_merged_into_tb} famille(s) Notion fusionnée(s) avec TutorBird")
        
        # ===============================
        # SAUVEGARDE (locale + Google Drive si cloud)
        # ===============================
        update(90, "💾 Sauvegarde...")
        
        # Sauvegarde locale (toujours)
        os.makedirs(data_dir, exist_ok=True)
        output_path = os.path.join(data_dir, "full_output_tb_SIMPLE.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(families, f, indent=2, ensure_ascii=False)
        
        # Sauvegarder les emails des profs TutorBird
        if teacher_emails:
            teacher_emails_path = os.path.join(data_dir, "teacher_emails.json")
            with open(teacher_emails_path, "w", encoding="utf-8") as f:
                json.dump(teacher_emails, f, indent=2, ensure_ascii=False)
            if STORAGE_AVAILABLE:
                try:
                    save_json("teacher_emails.json", teacher_emails, folder="data")
                except Exception:
                    pass
        
        # Sauvegarde Google Drive (si disponible et sur le cloud)
        drive_saved = False
        if STORAGE_AVAILABLE:
            try:
                result = save_json("full_output_tb_SIMPLE.json", families, folder="data")
                if result.get("success") and result.get("drive_id"):
                    drive_saved = True
            except Exception as e:
                print(f"⚠️ Erreur sauvegarde Drive: {e}")
            
            # Archive mensuelle (pour rechargement des mois précédents)
            try:
                month_key = end_date.strftime("%Y-%m")
                archive_name = f"full_output_tb_{month_key}.json"
                save_json(archive_name, families, folder="data")
                print(f"📦 Archive mensuelle sauvegardée : {archive_name}")
            except Exception as e:
                print(f"⚠️ Erreur sauvegarde archive mensuelle: {e}")
        
        update(100, "✅ Terminé !")
        
        # Stats
        total_lessons = sum(len(f["lessons"]) for f in families.values())
        total_amount = sum(f["total_courses"] for f in families.values())
        
        return {
            "success": True,
            "families": len(families),
            "lessons": total_lessons,
            "amount": total_amount,
            "notion_profs_added": notion_count,
            "output_path": output_path,
            "drive_saved": drive_saved
        }
        
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Timeout - L'API TutorBird ne répond pas"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Erreur de connexion - Vérifiez votre connexion internet"}
    except Exception as e:
        return {"success": False, "error": str(e)}