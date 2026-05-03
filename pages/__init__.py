"""
Pages de l'application Professor+ Admin
VERSION 2.1 - Avec onglets régénération
"""

import streamlit as st
import os
import json
import io
import zipfile
from datetime import datetime, time
import calendar

# Import des scripts
from scripts.extract_tutorbird import run_extraction
from scripts.update_notion import run_update_notion, run_update_notion_selective, run_scan_and_compare, run_add_missing_rows
from scripts.create_payment_links import run_create_payment_links
from scripts.generate_invoices import run_generate_invoices
from scripts.send_invoices_email import run_send_invoices, get_default_email_template, get_families_from_folder, collect_invoice_diagnostics, get_default_multimonth_template
from scripts.sync_stripe_notion import run_sync_stripe_notion
from scripts.activate_twint import get_twint_status, activate_twint_for_accounts
from scripts.cleanup_notion import run_cleanup_duplicates, run_scan_notion_dates, run_delete_old_rows
from scripts.send_payment_reminders import run_send_reminders, get_default_reminder_template, get_unpaid_families_from_notion, should_send_automatic_reminder
from scripts.recap_profs import compute_teacher_recap
from scripts.generate_prof_pdfs import generate_all_pdfs_to_bytes, generate_single_pdf_to_bytes, generate_all_pdfs_as_zip
from scripts.create_payment_links_no_split import run_create_payment_links_no_split
from scripts.no_prof_sync_stripe_notion import run_sync_stripe_notion_no_split
from scripts.fetch_notion_profs import fetch_notion_profs, convert_notion_profs_to_families
from scripts.fetch_unpaid_notion import fetch_unpaid_n2, deactivate_old_payment_links
from scripts.storage_manager import list_invoice_folders, load_invoice_folder, load_json as storage_load_json
from scripts.config_loader import is_streamlit_cloud
from scripts.quotes_data import get_random_hadith, get_random_life_quote, get_progress_message


def _try_load_data(ctx):
    """
    Essaie de charger les données extraites depuis :
    1. Le fichier local (extraction récente)
    2. Google Drive (extraction précédente)
    Retourne le dict des familles ou {} si rien trouvé.
    """
    data = ctx["load_extracted_data"]()
    if data:
        return data
    
    # Fallback : essayer depuis Google Drive via storage_manager
    try:
        drive_data = storage_load_json("full_output_tb_SIMPLE.json", "data", default=None)
        if drive_data:
            # Sauvegarder localement pour les prochains appels
            import json
            local_path = os.path.join(ctx["DATA_DIR"], "full_output_tb_SIMPLE.json")
            os.makedirs(ctx["DATA_DIR"], exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(drive_data, f, indent=2, ensure_ascii=False)
            st.session_state.has_extracted = True
            return drive_data
    except Exception as e:
        print(f"⚠️ Erreur chargement Drive: {e}")
    
    return {}


def _render_no_data_warning(page_label="cette fonctionnalité"):
    """Affiche un avertissement quand les données ne sont pas disponibles,
    avec un bouton pour aller à l'extraction."""
    st.warning(f"""
    ⚠️ **Aucune donnée disponible** — Pour utiliser {page_label}, vous devez d'abord
    extraire les données depuis TutorBird (ou avoir une extraction précédente sauvegardée sur Google Drive).
    """)
    if st.button("📥 Aller à l'extraction TutorBird", key=f"goto_extract_{page_label}"):
        st.session_state.current_page = "extract"
        st.rerun()


def _update_metadata(secrets, key_name, value=None, date_value=None):
    """Met à jour une ligne dans System-Metadata Notion.
    
    Args:
        secrets: config avec notion.token et notion.metadata_database_id
        key_name: ex "last_invoice_sent_date" ou "last_reminder_sent_date"
        value: nombre (optionnel, pour la colonne Valeur)
        date_value: date ISO string (optionnel, pour la colonne Invoice date mail)
    """
    try:
        import requests as _req
        import time as _t
        notion_cfg = secrets.get("notion", {})
        token = notion_cfg.get("token")
        metadata_db = notion_cfg.get("metadata_database_id")
        if not token or not metadata_db:
            return
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
        
        # Chercher la ligne existante
        _t.sleep(0.25)
        r = _req.post(f"https://api.notion.com/v1/databases/{metadata_db}/query", headers=headers, json={}, timeout=10)
        if r.status_code != 200:
            return
        
        page_id = None
        for row in r.json().get("results", []):
            p = row.get("properties", {})
            cle = p.get("Clé", {}).get("title", [])
            if cle and cle[0].get("plain_text", "").strip() == key_name:
                page_id = row["id"]
                break
        
        props = {}
        if value is not None:
            props["Valeur"] = {"number": value}
        if date_value:
            props["Invoice date mail"] = {"date": {"start": date_value}}
        
        if not props:
            return
        
        if page_id:
            # Update existing
            _t.sleep(0.25)
            _req.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=headers, json={"properties": props}, timeout=10)
        else:
            # Create new
            props["Clé"] = {"title": [{"text": {"content": key_name}}]}
            _t.sleep(0.25)
            _req.post(f"https://api.notion.com/v1/pages", headers=headers, json={
                "parent": {"database_id": metadata_db},
                "properties": props
            }, timeout=10)
        
        print(f"✅ Metadata updated: {key_name}")
    except Exception as e:
        print(f"⚠️ Metadata update failed for {key_name}: {e}")


def page_accueil(ctx):
    st.markdown("""
    <div class="header-card">
        <h1>🎓 Professor+ Admin</h1>
        <p>Gestion complète de votre activité de soutien scolaire</p>
    </div>
    """, unsafe_allow_html=True)
    
    secrets = ctx["load_secrets"]()
    data = _try_load_data(ctx)
    latest = ctx["get_latest_invoice_folder"]()
    
    nb_profs = len(secrets.get("teachers", {})) if secrets else 0
    nb_families = len(data) if data else 0
    
    # Calculer montants par devise
    familles_euros = ctx["load_familles_euros"]() if secrets else []
    from scripts.update_notion import normalize_name
    euro_parents = {normalize_name(n) for n in familles_euros} if familles_euros else set()
    
    total_chf = 0
    total_eur = 0
    total_aed = 0
    if data:
        for fam in data.values():
            parent = fam.get("parent_name") or fam.get("family_name") or ""
            lessons = [L for L in fam.get("lessons", []) if L.get("attendance_status") != "AbsentNotice"]
            amount = sum(float(L.get("amount") or 0) for L in lessons)
            currency = (fam.get("currency") or "").upper()
            if not currency:
                currency = "EUR" if normalize_name(parent) in euro_parents else "CHF"
            if currency == "EUR":
                total_eur += amount
            elif currency == "AED":
                total_aed += amount
            else:
                total_chf += amount
    
    has_multiple = sum(1 for t in (total_eur, total_chf, total_aed) if t > 0) > 1
    if has_multiple:
        # Calculer le total EUR équivalent
        try:
            from scripts.recap_profs import fetch_chf_eur_rate, fetch_fx_rate
            chf_eur_rate, _ = fetch_chf_eur_rate()
            aed_eur_rate = 0
            if total_aed > 0:
                aed_eur_rate, _ = fetch_fx_rate("AED", "EUR")
            total_eur_equiv = total_eur + (total_chf * chf_eur_rate) + (total_aed * aed_eur_rate)
            parts = []
            if total_chf > 0:
                parts.append(f"{total_chf:,.0f} CHF")
            if total_eur > 0:
                parts.append(f"{total_eur:,.0f} €")
            if total_aed > 0:
                parts.append(f"{total_aed:,.0f} AED")
            amount_display = " + ".join(parts)
            amount_sub = f"≈ {total_eur_equiv:,.0f} € total"
        except Exception:
            parts = []
            if total_chf > 0:
                parts.append(f"{total_chf:,.0f} CHF")
            if total_eur > 0:
                parts.append(f"{total_eur:,.0f} €")
            if total_aed > 0:
                parts.append(f"{total_aed:,.0f} AED")
            amount_display = " + ".join(parts)
            amount_sub = ""
        amount_size = "font-size: 1.1rem;"
    elif total_eur > 0:
        amount_display = f"{total_eur:,.0f} €"
        amount_sub = ""
        amount_size = ""
    elif total_aed > 0:
        amount_display = f"{total_aed:,.0f} AED"
        amount_sub = ""
        amount_size = ""
    else:
        amount_display = f"{total_chf:,.0f} CHF"
        amount_sub = ""
        amount_size = ""
    
    # Calculer le net EUR (CA total EUR - part profs)
    net_eur_display = "—"
    net_eur_sub = ""
    try:
        if data and secrets:
            tarifs_speciaux = ctx["load_tarifs_speciaux"]() if callable(ctx.get("load_tarifs_speciaux")) else []
            # Déterminer la date d'extraction pour le FX
            extraction_end = None
            if st.session_state.get("extract_dates"):
                extraction_end = st.session_state["extract_dates"].get("end_date")
            recap = compute_teacher_recap(
                data, secrets, familles_euros, tarifs_speciaux,
                extraction_end_date=extraction_end,
            )
            profs_total_eur = recap.get("grand_total", 0)
            # total_eur_equiv est déjà calculé plus haut (ou on le recalcule)
            if total_eur > 0 and total_chf > 0:
                from scripts.recap_profs import fetch_chf_eur_rate as _fetch_rate
                _rate, _ = _fetch_rate()
                ca_total_eur = total_eur + (total_chf * _rate)
            elif total_eur > 0:
                ca_total_eur = total_eur
            else:
                from scripts.recap_profs import fetch_chf_eur_rate as _fetch_rate
                _rate, _ = _fetch_rate()
                ca_total_eur = total_chf * _rate
            net_eur = ca_total_eur - profs_total_eur
            net_eur_display = f"{net_eur:,.0f} €"
            net_eur_sub = f"CA {ca_total_eur:,.0f} € − Profs {profs_total_eur:,.0f} €"
    except Exception as _e:
        print(f"⚠️ Erreur calcul net EUR: {_e}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="stat-card"><div class="stat-label">👨‍🏫 Professeurs</div><div class="stat-value">{nb_profs}</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="stat-card"><div class="stat-label">👨‍👩‍👧 Familles</div><div class="stat-value">{nb_families}</div></div>', unsafe_allow_html=True)
    with col3:
        sub_html = f'<div style="font-size: 0.75rem; color: #666; margin-top: 2px;">{amount_sub}</div>' if amount_sub else ""
        st.markdown(f'<div class="stat-card"><div class="stat-label">💰 À facturer</div><div class="stat-value" style="{amount_size}">{amount_display}</div>{sub_html}</div>', unsafe_allow_html=True)
    with col4:
        net_sub_html = f'<div style="font-size: 0.75rem; color: #666; margin-top: 2px;">{net_eur_sub}</div>' if net_eur_sub else ""
        st.markdown(f'<div class="stat-card"><div class="stat-label">💶 Mon net EUR</div><div class="stat-value" style="color: #28a745;">{net_eur_display}</div>{net_sub_html}</div>', unsafe_allow_html=True)
    
    # ===========================
    # SECTION PAIEMENTS
    # ===========================
    st.markdown('<div class="section-title">💳 Suivi des paiements</div>', unsafe_allow_html=True)
    
    choices = _invoice_folder_choices()
    if choices:
        folder_labels = [c[0] for c in choices]
        selected_idx = st.selectbox("📁", range(len(folder_labels)), format_func=lambda i: folder_labels[i], key="home_folder_select", label_visibility="collapsed")
        selected_home_folder = choices[selected_idx][1] if selected_idx is not None else None
    else:
        selected_home_folder = None
        st.caption("Aucun dossier de factures trouvé.")
    
    if secrets and selected_home_folder:
        try:
            import requests as _req
            NOTION_TOKEN = secrets["notion"]["token"]
            DB_PAIEMENTS = secrets["notion"]["paiements_database_id"]
            HEADERS_N = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
            
            _r = _req.post(f"https://api.notion.com/v1/databases/{DB_PAIEMENTS}/query", headers=HEADERS_N, json={"page_size": 100}, timeout=15)
            
            if _r.status_code == 200:
                all_rows = _r.json().get("results", [])
                folder_dt = _parse_invoice_folder_dt(selected_home_folder.get("month", ""))
                
                month_rows = []
                for row in all_rows:
                    p = row.get("properties", {})
                    invoice_date = p.get("Invoice date", {}).get("date")
                    row_date = invoice_date["start"][:7] if invoice_date and invoice_date.get("start") else None
                    
                    if folder_dt and row_date and row_date == folder_dt.strftime("%Y-%m"):
                        is_paid = p.get("Payé ?", {}).get("checkbox", False)
                        month_rows.append({"paid": is_paid})
                
                total_payments = len(month_rows)
                paid_count = sum(1 for r in month_rows if r["paid"])
                unpaid_count = total_payments - paid_count
                
                if total_payments > 0:
                    pct = int(paid_count / total_payments * 100)
                    color = "#28a745" if pct == 100 else "#f0ad4e" if pct >= 50 else "#dc3545"
                    
                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1:
                        st.markdown(f'<div class="stat-card"><div class="stat-label">✅ Payés</div><div class="stat-value" style="color: #28a745;">{paid_count}</div></div>', unsafe_allow_html=True)
                    with col_p2:
                        st.markdown(f'<div class="stat-card"><div class="stat-label">⏳ En attente</div><div class="stat-value" style="color: {"#dc3545" if unpaid_count > 0 else "#28a745"};">{unpaid_count}</div></div>', unsafe_allow_html=True)
                    with col_p3:
                        st.markdown(f'<div class="stat-card"><div class="stat-label">📊 Progression</div><div class="stat-value" style="color: {color};">{paid_count}/{total_payments}</div></div>', unsafe_allow_html=True)
                    st.progress(pct / 100)
                    progress_msg = get_progress_message(pct)
                    st.caption(progress_msg)
                else:
                    st.caption("Aucune ligne Notion trouvée pour ce mois.")
        except Exception:
            st.caption("Données paiement non disponibles.")
    
    # ===========================
    # HISTORIQUE ENVOIS
    # ===========================
    st.markdown('<div class="section-title">📧 Historique des envois</div>', unsafe_allow_html=True)
    
    invoice_sent_date = "—"
    reminder_sent_date = "—"
    reminder_count = 0
    
    if secrets:
        try:
            import requests as _req
            metadata_db = secrets["notion"].get("metadata_database_id")
            if metadata_db:
                _r = _req.post(
                    f"https://api.notion.com/v1/databases/{metadata_db}/query",
                    headers={"Authorization": f"Bearer {secrets['notion']['token']}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"},
                    json={}, timeout=10
                )
                if _r.status_code == 200:
                    for row in _r.json().get("results", []):
                        p = row.get("properties", {})
                        cle = p.get("Clé", {}).get("title", [])
                        key_name = cle[0].get("plain_text", "").strip() if cle else ""
                        
                        if key_name == "last_invoice_sent_date":
                            d = p.get("Invoice date mail", {}).get("date")
                            if d and d.get("start"):
                                invoice_sent_date = d["start"][:10]
                        elif key_name == "last_reminder_sent_date":
                            d = p.get("Invoice date mail", {}).get("date")
                            if d and d.get("start"):
                                reminder_sent_date = d["start"][:10]
                            val = p.get("Valeur", {}).get("number")
                            if val:
                                reminder_count = int(val)
        except Exception:
            pass
    
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        st.markdown(f'<div class="stat-card"><div class="stat-label">📨 Factures envoyées le</div><div class="stat-value" style="font-size: 1.1rem;">{invoice_sent_date}</div></div>', unsafe_allow_html=True)
    with col_h2:
        st.markdown(f'<div class="stat-card"><div class="stat-label">🔔 Dernière relance le</div><div class="stat-value" style="font-size: 1.1rem;">{reminder_sent_date}</div></div>', unsafe_allow_html=True)
    with col_h3:
        st.markdown(f'<div class="stat-card"><div class="stat-label">📊 Nb relances</div><div class="stat-value">{reminder_count}</div></div>', unsafe_allow_html=True)
    
    # Alerte rappel automatique le 11
    if should_send_automatic_reminder():
        st.warning("🔔 **C'est le 11 du mois !** Pensez à envoyer les rappels de paiement aux familles qui n'ont pas encore payé.")
    
    # ===========================
    # CITATIONS
    # ===========================
    st.markdown("---")
    
    hadith = get_random_hadith(st.session_state)
    life_quote = get_random_life_quote(st.session_state)
    
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1a5632 0%, #2d8a56 100%); border-radius: 12px; padding: 20px; color: white; min-height: 140px;">
            <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; opacity: 0.8; margin-bottom: 8px;">🕌 Hadith du jour</div>
            <div style="font-size: 0.95rem; font-style: italic; line-height: 1.5;">« {hadith['text']} »</div>
            <div style="font-size: 0.75rem; margin-top: 10px; opacity: 0.8;">— {hadith['narrator']} · {hadith['source']}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_q2:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1a3a5c 0%, #2a5a8c 100%); border-radius: 12px; padding: 20px; color: white; min-height: 140px;">
            <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; opacity: 0.8; margin-bottom: 8px;">💡 Citation du jour</div>
            <div style="font-size: 0.95rem; font-style: italic; line-height: 1.5;">"{life_quote['text']}"</div>
            <div style="font-size: 0.75rem; margin-top: 10px; opacity: 0.8;">— {life_quote['author']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("")
    
    st.markdown('<div class="section-title">⚡ Actions rapides</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📥 Extraction TutorBird", width="stretch", key="home_extract"):
            st.session_state.current_page = "extract"
            st.rerun()
    with col2:
        if st.button("💳 Créer liens paiement", width="stretch", key="home_payment"):
            st.session_state.current_page = "payment"
            st.rerun()
    with col3:
        if st.button("📄 Générer Factures", width="stretch", key="home_invoices"):
            st.session_state.current_page = "invoices"
            st.rerun()
    
    st.markdown('<div class="section-title">📋 Workflow recommandé</div>', unsafe_allow_html=True)
    
    st.info("""
    **📌 Ordre recommandé pour la facturation :**
    1. **Extraire TutorBird** - Récupérer les leçons du mois
    2. **Créer liens paiement** - Générer les liens Stripe
    3. **Générer Factures** - Créer les PDFs
    4. **Envoyer Factures** - Envoyer par email
    5. **Ajouter lignes Notion** - Ajouter dans la DB paiements + sous-pages profs
    6. **Sync Stripe→Notion** - Marquer les paiements reçus
    """)


def page_extract(ctx):
    st.markdown('<div class="section-title">📥 Extraction TutorBird</div>', unsafe_allow_html=True)
    
    st.info("Sélectionnez la période pour extraire les leçons depuis TutorBird.")
    
    today = datetime.today()
    
    # ===========================
    # SÉLECTION RAPIDE
    # ===========================
    st.markdown("**⚡ Sélection rapide**")
    
    # Calcul mois précédent
    if today.month == 1:
        prev_y, prev_m = today.year - 1, 12
    else:
        prev_y, prev_m = today.year, today.month - 1
    
    # Calcul avant-précédent
    if prev_m == 1:
        prev2_y, prev2_m = prev_y - 1, 12
    else:
        prev2_y, prev2_m = prev_y, prev_m - 1
    
    MONTHS_FR = ctx["MONTHS_FR"]
    
    col_q1, col_q2, col_q3 = st.columns(3)
    with col_q1:
        if st.button(f"📅 {MONTHS_FR[prev_m - 1]} {prev_y}", width="stretch", key="quick_prev"):
            st.session_state.extract_quick_month = (prev_y, prev_m)
            st.rerun()
    with col_q2:
        if st.button(f"📅 {MONTHS_FR[prev2_m - 1]} {prev2_y}", width="stretch", key="quick_prev2"):
            st.session_state.extract_quick_month = (prev2_y, prev2_m)
            st.rerun()
    with col_q3:
        if st.button(f"📅 {MONTHS_FR[today.month - 1]} {today.year} (en cours)", width="stretch", key="quick_current"):
            st.session_state.extract_quick_month = (today.year, today.month)
            st.rerun()
    
    # Appliquer la sélection rapide
    quick = st.session_state.get("extract_quick_month")
    if quick:
        qy, qm = quick
        first_day = datetime(qy, qm, 1).date()
        last_day = datetime(qy, qm, calendar.monthrange(qy, qm)[1]).date()
    else:
        first_day = today.replace(day=1)
        last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("📅 Date de début", value=first_day, format="DD/MM/YYYY")
    with col2:
        end_date = st.date_input("📅 Date de fin", value=last_day, format="DD/MM/YYYY")
    
    full_day = st.checkbox("🗓️ Journée entière (00:00 → 23:59)", value=True)
    
    if full_day:
        start_time = time(0, 0)
        end_time = time(23, 59)
    else:
        col1, col2 = st.columns(2)
        with col1:
            start_time = st.time_input("Heure de début", value=time(0, 0))
        with col2:
            end_time = st.time_input("Heure de fin", value=time(23, 59))
    
    st.markdown("---")
    
    # ===========================
    # SECTION PROFS HORS TUTORBIRD (Notion)
    # ===========================
    st.markdown('<div class="section-title">📋 Profs hors TutorBird (Notion)</div>', unsafe_allow_html=True)
    
    secrets = ctx["load_secrets"]()
    notion_entries = []
    selected_notion_profs = set()
    
    if secrets and secrets.get("notion", {}).get("profs_hors_tutorbird_database_id"):
        # Charger les données Notion
        if "notion_profs_data" not in st.session_state or st.button("🔄 Rafraîchir depuis Notion", key="refresh_notion_profs"):
            with st.spinner("Chargement depuis Notion..."):
                result = fetch_notion_profs(secrets)
                if result["success"]:
                    st.session_state.notion_profs_data = result["entries"]
                else:
                    st.error(f"❌ Erreur Notion: {result['error']}")
                    st.session_state.notion_profs_data = []
        
        notion_entries = st.session_state.get("notion_profs_data", [])
        
        if notion_entries:
            st.success(f"✅ **{len(notion_entries)}** entrée(s) trouvée(s) dans Notion")
            
            # Afficher le tableau
            table_data = []
            for e in notion_entries:
                table_data.append({
                    "Famille": e["famille"],
                    "Professeur": e["professeur"],
                    "Élève": e["eleve"],
                    "Heures": e["heures_faites"],
                    "Taux client": f"{e['taux_horaire_client']} {e['devise_client']}",
                    "Taux prof": f"{e['taux_horaire_prof']} {e['devise_prof']}",
                    "Total client": f"{e['taux_horaire_client'] * e['heures_faites']:.0f} {e['devise_client']}",
                })
            
            st.dataframe(table_data, hide_index=True, use_container_width=True)
            
            # Sélection des profs
            all_profs = list({e["professeur"] for e in notion_entries if e["professeur"]})
            all_profs.sort()
            
            selected_list = st.multiselect(
                "👨‍🏫 Profs hors TutorBird à inclure",
                all_profs,
                default=all_profs,
                key="notion_profs_select"
            )
            selected_notion_profs = set(selected_list)
            
            if selected_notion_profs:
                selected_entries = [e for e in notion_entries if e["professeur"] in selected_notion_profs]
                # Grouper par devise
                totals_by_currency = {}
                for e in selected_entries:
                    devise = e["devise_client"]
                    totals_by_currency[devise] = totals_by_currency.get(devise, 0) + e["taux_horaire_client"] * e["heures_faites"]
                total_str = " + ".join(f"**{amt:,.0f} {cur}**" for cur, amt in totals_by_currency.items())
                st.info(f"📊 **{len(selected_entries)}** entrée(s) sélectionnée(s) — Total client : {total_str}")
        else:
            st.info("Aucune entrée dans la base Notion « Profs hors TutorBird ».")
    else:
        st.warning("⚠️ `profs_hors_tutorbird_database_id` non configuré dans secrets.yaml")
    
    st.markdown("---")
    
    # Info pour modification de factures
    st.info("💡 **Besoin de modifier des factures ?** Utilisez l'onglet *« Régénérer certaines familles »* dans **Créer liens paiement**, puis *« Régénérer certaines factures »* dans **Générer factures**.")
    
    if st.button("🚀 Lancer l'extraction", type="primary", width="stretch"):
        if not secrets:
            st.error("❌ Fichier secrets.yaml non trouvé !")
            return
        
        progress_bar = st.progress(0)
        status = st.empty()
        
        def callback(progress, message):
            progress_bar.progress(progress)
            status.info(message)
        
        # Convertir les profs Notion sélectionnés en format familles
        notion_families = None
        if notion_entries and selected_notion_profs:
            notion_families = convert_notion_profs_to_families(notion_entries, selected_notion_profs)
        
        result = run_extraction(
            secrets, start_date, end_date, start_time, end_time,
            ctx["DATA_DIR"], callback,
            notion_families=notion_families,
        )
        
        if result["success"]:
            st.session_state.has_extracted = True
            st.session_state.extract_dates = {"start": start_date, "end": end_date}

            report_path = os.path.join(ctx["DATA_DIR"], "payment_links_report.json")
            if os.path.exists(report_path):
                os.remove(report_path)

            links_path = os.path.join(ctx["DATA_DIR"], "payment_links_output.json")
            if os.path.exists(links_path):
                os.remove(links_path)
            
            notion_msg = ""
            if result.get("notion_profs_added", 0) > 0:
                notion_msg = f"\n            - 📋 **{result['notion_profs_added']}** prof(s) hors TutorBird ajouté(s)"
            
            # Décomposition par devise — au niveau LEÇON pour gérer les familles
            # qui mélangent TutorBird (CHF) + Notion hors TB (EUR/AED)
            try:
                _data_for_split = ctx["load_extracted_data"]() or {}
                _familles_euros_for_split = ctx["load_familles_euros"]() if callable(ctx.get("load_familles_euros")) else []
                _euro_parents_norm = set()
                for _fe in _familles_euros_for_split or []:
                    _name = _fe if isinstance(_fe, str) else _fe.get("parent_name", "")
                    if _name:
                        _euro_parents_norm.add(_name.lower().strip())
                
                amounts_by_currency = {}
                for _fid, _fam in _data_for_split.items():
                    _parent = _fam.get("parent_name", "")
                    _is_euro_family = _parent.lower().strip() in _euro_parents_norm
                    
                    # Itérer leçon par leçon pour avoir la vraie devise
                    for _lesson in _fam.get("lessons", []):
                        _amt = float(_lesson.get("amount") or 0)
                        if _amt == 0:
                            continue
                        
                        # Détection devise leçon par leçon :
                        # 1. Si la leçon vient de Notion (source notion_hors_tb) → notion_devise_client
                        # 2. Sinon (leçon TutorBird) → CHF par défaut, EUR si famille dans familles_euros.yaml
                        _lesson_source = _lesson.get("source", "")
                        _notion_cur = _lesson.get("notion_devise_client", "")
                        
                        if _lesson_source == "notion_hors_tb" or _notion_cur:
                            # Leçon Notion : utiliser notion_devise_client
                            _lesson_cur = (_notion_cur or "EUR").upper()
                        else:
                            # Leçon TutorBird : CHF par défaut, EUR si marquée euros
                            _lesson_cur = "EUR" if _is_euro_family else "CHF"
                        
                        amounts_by_currency[_lesson_cur] = amounts_by_currency.get(_lesson_cur, 0) + _amt
            except Exception as _e:
                print(f"⚠️ Erreur recalcul amounts_by_currency: {_e}")
                amounts_by_currency = result.get("amounts_by_currency", {})
            
            if len(amounts_by_currency) > 1:
                parts = []
                for cur in sorted(amounts_by_currency.keys()):
                    amt = amounts_by_currency[cur]
                    parts.append(f"{amt:,.2f} {cur}")
                amount_display = " + ".join(parts)
            elif amounts_by_currency:
                _cur, _amt = next(iter(amounts_by_currency.items()))
                amount_display = f"{_amt:,.2f} {_cur}"
            else:
                amount_display = f"{result['amount']:,.2f} CHF"
            
            # Calculer le net EUR (CA total EUR - part profs)
            net_msg = ""
            try:
                from scripts.recap_profs import compute_teacher_recap, fetch_fx_rate, fetch_chf_eur_rate
                _data_for_net = ctx["load_extracted_data"]()
                _secrets = ctx["load_secrets"]() if callable(ctx.get("load_secrets")) else None
                _familles_euros = ctx["load_familles_euros"]() if callable(ctx.get("load_familles_euros")) else []
                _tarifs_speciaux = ctx["load_tarifs_speciaux"]() if callable(ctx.get("load_tarifs_speciaux")) else []
                _extraction_end = None
                if st.session_state.get("extract_dates"):
                    _extraction_end = st.session_state["extract_dates"].get("end_date")
                if _data_for_net and _secrets:
                    _recap = compute_teacher_recap(
                        _data_for_net, _secrets, _familles_euros, _tarifs_speciaux,
                        extraction_end_date=_extraction_end,
                    )
                    _profs_total_eur = _recap.get("grand_total", 0)
                    
                    # Convertir le CA total en EUR
                    _chf_eur_rate, _ = fetch_chf_eur_rate()
                    _aed_eur_rate, _ = fetch_fx_rate("AED", "EUR")
                    _ca_eur = 0
                    for cur, amt in amounts_by_currency.items():
                        cur_up = cur.upper()
                        if cur_up == "EUR":
                            _ca_eur += amt
                        elif cur_up == "CHF":
                            _ca_eur += amt * _chf_eur_rate
                        elif cur_up == "AED":
                            _ca_eur += amt * _aed_eur_rate
                    
                    _net_eur = _ca_eur - _profs_total_eur
                    net_msg = f"\n            - 💶 **Net : {_net_eur:,.2f} €** (CA {_ca_eur:,.2f} € − Profs {_profs_total_eur:,.2f} €)"
            except Exception as _e:
                print(f"⚠️ Erreur calcul net dans extraction: {_e}")
            
            st.success(f"""
            ✅ **Extraction terminée !**
            - 📁 **{result['families']}** familles
            - 📚 **{result['lessons']}** leçons
            - 💰 **{amount_display}** total{notion_msg}{net_msg}
            """)
            
            if st.button("🏠 Retour à l'accueil", key="extract_home_btn"):
                st.session_state.current_page = "accueil"
                st.rerun()
        else:
            st.error(f"❌ Erreur : {result['error']}")


def page_twint(ctx):
    st.markdown('<div class="section-title">⚡ Activation Twint</div>', unsafe_allow_html=True)
    
    secrets = ctx["load_secrets"]()
    if not secrets:
        st.error("❌ Fichier secrets.yaml non trouvé !")
        return
    
    if st.button("🔍 Vérifier le statut Twint", width="stretch"):
        progress = st.progress(0)
        status = st.empty()
        
        def callback(progress_val, message):
            progress.progress(progress_val)
            status.info(message)
        
        result = get_twint_status(secrets, callback)
        
        if result["success"]:
            st.markdown("### 📊 Statut des comptes")
            
            for acc in result["accounts"]:
                if acc["has_connect"]:
                    emoji = "✅" if acc["twint_status"] == "active" else "⏳" if acc["twint_status"] == "pending" else "❌"
                    st.write(f"{emoji} **{acc['name']}** : {acc['twint_status']}")
                else:
                    st.write(f"⚪ **{acc['name']}** : Pas de compte Connect")
        else:
            st.error(f"❌ Erreur : {result['error']}")
    
    st.markdown("---")
    
    st.markdown("### ⚡ Activer Twint")
    
    teachers = secrets.get("teachers", {})
    accounts_to_activate = []
    
    for name, info in teachers.items():
        connect_id = info.get("connect_account_id")
        if connect_id:
            accounts_to_activate.append({"name": name, "id": connect_id})
    
    if accounts_to_activate:
        selected = st.multiselect(
            "Sélectionner les comptes à activer",
            [a["name"] for a in accounts_to_activate],
            default=[a["name"] for a in accounts_to_activate]
        )
        
        if st.button("⚡ Activer Twint", type="primary", width="stretch"):
            ids = [a["id"] for a in accounts_to_activate if a["name"] in selected]
            
            result = activate_twint_for_accounts(secrets, ids)
            
            if result["success"]:
                st.success(f"✅ {result['activated']} compte(s) activé(s)")
                if result["errors"]:
                    for err in result["errors"]:
                        st.warning(f"⚠️ {err}")
            else:
                st.error(f"❌ Erreur : {result['error']}")
    else:
        st.warning("⚠️ Aucun compte Connect configuré")


def page_cleanup(ctx):
    st.markdown('<div class="section-title">🧹 Nettoyage Notion</div>', unsafe_allow_html=True)
    
    st.info("""
    Cette page regroupe tous les outils de nettoyage Notion :
    - **Scanner les dates** : voir quelles dates de factures sont présentes
    - **Supprimer les anciennes lignes** : nettoyer les données obsolètes
    - **Nettoyer les doublons** : supprimer les pages élèves en double
    """)
    
    secrets = ctx["load_secrets"]()
    if not secrets:
        st.error("❌ Fichier secrets.yaml non trouvé !")
        return
    
    tab1, tab2, tab3 = st.tabs(["📅 Scanner les dates", "🗑️ Supprimer anciennes lignes", "🔍 Nettoyer doublons"])
    
    # ===========================
    # TAB 1: Scanner les dates
    # ===========================
    with tab1:
        st.markdown("### 📅 Dates de factures présentes dans Notion")
        
        if st.button("🔍 Scanner les dates", width="stretch", key="scan_dates"):
            progress = st.progress(0)
            status = st.empty()
            
            def callback(p, m):
                progress.progress(p)
                status.info(m)
            
            result = run_scan_notion_dates(secrets, callback)
            
            if result["success"]:
                st.session_state.notion_dates_scan = result
                st.success(f"✅ Scan terminé : **{result['count']}** date(s) trouvée(s)")
            else:
                st.error(f"❌ Erreur : {result['error']}")
        
        # Afficher les résultats du scan
        if st.session_state.get("notion_dates_scan"):
            scan = st.session_state.notion_dates_scan
            
            st.markdown(f"**📊 {scan['total_rows']} lignes** dans la base Notion")
            st.markdown(f"**📅 Date la plus récente** : {scan['latest_readable']}")
            
            with st.expander("📋 Toutes les dates", expanded=True):
                for d in scan["dates"]:
                    st.write(f"• {d['readable']} ({d['iso']})")
    
    # ===========================
    # TAB 2: Supprimer anciennes lignes
    # ===========================
    with tab2:
        st.markdown("### 🗑️ Supprimer les anciennes lignes")
        
        st.warning("""
        ⚠️ **Attention** : Cette action supprime définitivement les lignes Notion ET les sous-pages des professeurs correspondantes.
        
        **Recommandation** : Supprimez les lignes antérieures à la date de facture la plus récente.
        """)
        
        # Récupérer la date la plus récente si scan effectué
        latest_date = None
        if st.session_state.get("notion_dates_scan"):
            latest_date = st.session_state.notion_dates_scan.get("latest_date")
        
        if latest_date:
            st.info(f"💡 Date la plus récente détectée : **{st.session_state.notion_dates_scan['latest_readable']}**")
            use_latest = st.checkbox("Garder uniquement à partir de cette date (recommandé)", value=True)
            
            if use_latest:
                keep_from = latest_date
            else:
                keep_from = st.date_input("📅 Garder à partir de", value=datetime.strptime(latest_date, "%Y-%m-%d"))
                keep_from = keep_from.strftime("%Y-%m-%d")
        else:
            st.warning("⚠️ Scannez d'abord les dates pour voir les options disponibles.")
            keep_from = st.date_input("📅 Garder à partir de", value=datetime.today())
            keep_from = keep_from.strftime("%Y-%m-%d")
        
        dry_run = st.checkbox("🔍 Mode aperçu (ne supprime rien)", value=True, key="delete_dry_run")
        
        if st.button("🗑️ Lancer la suppression", type="primary", width="stretch", key="delete_old"):
            progress = st.progress(0)
            status = st.empty()
            
            def callback(p, m):
                progress.progress(p)
                status.info(m)
            
            result = run_delete_old_rows(secrets, keep_from, dry_run=dry_run, callback=callback)
            
            if result["success"]:
                if dry_run:
                    st.warning(f"""
                    🔍 **Aperçu** :
                    - {result['deleted_rows']} ligne(s) DB à supprimer
                    - {result['deleted_pages']} sous-page(s) prof à supprimer
                    - {result['kept_rows']} ligne(s) conservées
                    """)
                else:
                    st.success(f"""
                    ✅ **Suppression terminée** :
                    - {result['deleted_rows']} ligne(s) DB supprimées
                    - {result['deleted_pages']} sous-page(s) prof supprimées
                    """)
                
                if result.get("details_pages"):
                    with st.expander("📋 Détails des sous-pages supprimées"):
                        for p in result["details_pages"]:
                            st.write(f"• {p['prof']} → {p['date_title']}")
            else:
                st.error(f"❌ Erreur : {result['error']}")
    
    # ===========================
    # TAB 3: Nettoyer doublons
    # ===========================
    with tab3:
        st.markdown("### 🔍 Nettoyer les doublons de pages élèves")
        
        st.info("Détecte et supprime les pages élèves en doublon (ex: 'Louis Clémence' et 'Louis, Clémence')")
        
        dry_run = st.checkbox("🔍 Mode aperçu (ne supprime rien)", value=True, key="dup_dry_run")
        
        if st.button("🧹 Lancer le nettoyage", type="primary", width="stretch", key="cleanup_dup"):
            progress = st.progress(0)
            status = st.empty()
            
            def callback(p, m):
                progress.progress(p)
                status.info(m)
            
            result = run_cleanup_duplicates(secrets, dry_run=dry_run, callback=callback)
            
            if result["success"]:
                if dry_run:
                    st.warning(f"🔍 **Aperçu** : {result['duplicates_found']} doublons trouvés")
                else:
                    st.success(f"✅ {result['deleted']} doublons supprimés")
                
                if result.get("details"):
                    with st.expander("📋 Détails"):
                        for d in result["details"]:
                            st.write(f"- {d['prof']} / {d['date']} : garder '{d['keep']}', supprimer '{d['delete']}'")
            else:
                st.error(f"❌ Erreur : {result['error']}")

def page_payment(ctx):
    st.markdown('<div class="section-title">💳 Créer les liens de paiement</div>', unsafe_allow_html=True)
    
    # Chargement des données avec fallback Drive
    data = _try_load_data(ctx)
    secrets = ctx["load_secrets"]()
    
    if not secrets:
        st.error("❌ Fichier secrets.yaml non trouvé !")
        return
    
    if not data:
        _render_no_data_warning("les liens de paiement")
        return
    
    configured_teachers = set(secrets.get("teachers", {}).keys())
    
    # ===========================
    # VÉRIFICATION DES PROFS AVANT TOUT
    # ===========================
    # Récupérer tous les profs de TutorBird (exclure ceux venant de Notion hors TB)
    tutorbird_teachers = set()
    notion_hors_tb_teachers = set()
    for fam_id, fam in data.items():
        is_notion_source = (
            fam.get("source") in ("notion_hors_tb", "notion_hors_tutorbird")
            or fam.get("is_hors_tutorbird")
        )
        for L in fam.get("lessons", []):
            teacher = L.get("teacher", "")
            if not teacher:
                continue
            if is_notion_source or L.get("source") == "notion_hors_tb":
                notion_hors_tb_teachers.add(teacher)
            else:
                tutorbird_teachers.add(teacher)
    
    # Fonction de normalisation pour comparaison
    def normalize_for_compare(s):
        if not s:
            return ""
        import unicodedata
        s = s.lower().strip()
        s = unicodedata.normalize('NFD', s)
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        s = s.replace("-", " ").replace("_", " ").replace(",", " ")
        return " ".join(s.split())
    
    # Créer un mapping normalisé des profs configurés
    configured_normalized = {normalize_for_compare(t): t for t in configured_teachers}
    
    # Trouver les profs non configurés
    missing_teachers = []
    matched_teachers = []
    
    # Normaliser les noms des profs Notion pour comparaison
    notion_teachers_normalized = {normalize_for_compare(t) for t in notion_hors_tb_teachers}
    
    for tb_teacher in tutorbird_teachers:
        tb_norm = normalize_for_compare(tb_teacher)
        
        # Si ce prof est aussi dans Notion hors TB (même nom normalisé), on l'ignore
        if tb_norm in notion_teachers_normalized:
            continue
        
        # Vérifier match exact ou similaire
        found = False
        for cfg_norm, cfg_original in configured_normalized.items():
            # Match exact normalisé
            if tb_norm == cfg_norm:
                found = True
                matched_teachers.append({"tutorbird": tb_teacher, "config": cfg_original})
                break
            # Match partiel (ex: "Ricardo H" vs "Ricardo Hounsinou")
            if tb_norm in cfg_norm or cfg_norm in tb_norm:
                found = True
                matched_teachers.append({"tutorbird": tb_teacher, "config": cfg_original})
                break
        
        if not found:
            missing_teachers.append(tb_teacher)
    
    # ===========================
    # AFFICHAGE STATUT DES PROFS
    # ===========================
    if missing_teachers:
        st.error(f"❌ **{len(missing_teachers)} professeur(s) non configuré(s)** - Vous devez les ajouter avant de générer les liens")
        
        for teacher in missing_teachers:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"• **{teacher}**")
            with col2:
                if st.button(f"➕ Ajouter", key=f"add_missing_{teacher}"):
                    st.session_state.prefill_new_teacher_name = teacher
                    st.session_state.return_to_page = "payment"
                    st.session_state.current_page = "config"
                    st.rerun()
        
        st.markdown("---")
    else:
        msg = f"✅ **{len(matched_teachers)} professeur(s)** - Tous les profs TutorBird sont configurés"
        if notion_hors_tb_teachers:
            msg += f"  •  **{len(notion_hors_tb_teachers)}** prof(s) hors TutorBird (Notion)"
        st.success(msg)
    
    # ===========================
    # ONGLETS
    # ===========================
    tab1, tab2 = st.tabs(["🚀 Générer tous les liens", "🔄 Régénérer pour certaines familles"])
    
    # ===========================
    # TAB 1: Générer tous les liens
    # ===========================
    with tab1:
        # RAPPORT - SEULEMENT si on vient de générer (pas à chaque visite)
        report_path = os.path.join(ctx["DATA_DIR"], "payment_links_report.json")
        
        # Afficher le rapport SEULEMENT si flag actif
        if st.session_state.get("show_payment_report") and os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            
            nb_expected = report.get("expected_families_count", 0)
            nb_created = report.get("created_families_count", 0)
            nb_links = report.get("links_count", 0)
            profs_inconnus_raw = report.get("profs_inconnus", [])
            missing_families = report.get("missing_families", [])
            
            # Filtrer les profs inconnus
            profs_inconnus = [p for p in profs_inconnus_raw if p not in configured_teachers]
            
            all_ok = (len(missing_families) == 0 and len(profs_inconnus) == 0)
            
            # Récupérer les stats d'absences
            absences_ignorees = report.get("absences_ignorees", 0)
            absences_facturees = report.get("absences_facturees", 0)
            
            if all_ok:
                st.success(f"""
                ✅ **Tous les liens de paiement ont été générés avec succès !**
                - 🔗 **{nb_links}** liens créés
                - 👨‍👩‍👧 **{nb_created}/{nb_expected}** familles traitées
                - ❌ **{absences_ignorees}** absence(s) signalée(s) (non facturées)
                - ⚠️ **{absences_facturees}** absence(s) sans rattrapage (facturées)
                """)
            else:
                st.warning(f"""
                ⚠️ **Liens générés avec des avertissements**
                - 🔗 **{nb_links}** liens créés
                - 👨‍👩‍👧 **{nb_created}/{nb_expected}** familles traitées
                - ❌ **{absences_ignorees}** absence(s) signalée(s) (non facturées)
                - ⚠️ **{absences_facturees}** absence(s) sans rattrapage (facturées)
                """)
            
            if profs_inconnus:
                st.error("❌ **Profs inconnus détectés**")
                for p in profs_inconnus:
                    if st.button(f"➕ Ajouter : {p}", key=f"add_unknown_{p}"):
                        st.session_state.prefill_new_teacher_name = p
                        st.session_state.return_to_page = "payment"
                        st.session_state.current_page = "config"
                        st.rerun()
            
            if missing_families:
                with st.expander(f"❌ {len(missing_families)} famille(s) sans lien", expanded=True):
                    for fam in missing_families:
                        st.write(f"• **{fam['parent_name']}** — {fam['billable_amount']} {fam['currency']}")
            
            # Bouton pour fermer le rapport
            if st.button("✖️ Fermer ce rapport", key="close_report"):
                st.session_state.show_payment_report = False
                st.rerun()
            
            st.markdown("---")
        
        # Info
        st.info(f"📊 **{len(data)}** familles dans l'extraction")
        
        # Bloquer si profs manquants
        if missing_teachers:
            st.error("⛔ Vous devez d'abord configurer tous les professeurs ci-dessus avant de générer les liens.")
            return
        
        # Options communes (On Behalf Of + Méthodes paiement)
        use_on_behalf, selected_teachers, payment_method_types, no_split_mode, secrets_no_prof = _render_payment_options(ctx, secrets, "tab1")
        
        # Option: inclure les impayés des mois précédents dans le montant
        include_unpaid_payment = st.checkbox(
            "📌 Inclure les montants impayés des mois précédents",
            value=False,
            key="include_unpaid_payment_links",
            help="Si coché, le lien de paiement couvrira aussi les cours non réglés des mois précédents (chargés via la page Factures)."
        )
        
        additional_amounts = None
        if include_unpaid_payment:
            prev_data = st.session_state.get("_previous_unpaid_data")
            if prev_data:
                additional_amounts = {}
                for fam_id, fam_data in prev_data.items():
                    lessons = fam_data.get("lessons", [])
                    billable = [L for L in lessons if L.get("attendance_status") != "AbsentNotice"]
                    fam_total = sum(float(L.get("amount") or 0) for L in billable)
                    if fam_total > 0:
                        additional_amounts[fam_id] = fam_total
                if additional_amounts:
                    st.info(f"📦 **{len(additional_amounts)}** famille(s) avec montant impayé ajouté au lien Stripe")
                else:
                    st.warning("⚠️ Aucun montant impayé trouvé dans les données chargées.")
            else:
                st.warning("⚠️ Les données impayées ne sont pas chargées. Allez d'abord dans **Générer Factures** → cochez **Inclure les impayés** → **Charger les données**.")
        
        # Bouton Relancer manquants (seulement si rapport affiché et mode normal)
        if not no_split_mode and st.session_state.get("show_payment_report") and os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            missing_families = report.get("missing_families", [])
            
            if missing_families:
                st.markdown("---")
                if st.button("🔁 Relancer uniquement les liens manquants", width="stretch", key="relaunch_missing"):
                    familles_euros = ctx["load_familles_euros"]()
                    tarifs_speciaux = ctx["load_tarifs_speciaux"]()

                    progress = st.progress(0)
                    status = st.empty()

                    def callback(p, m):
                        progress.progress(p)
                        status.info(m)

                    target_family_ids = [f["family_id"] for f in missing_families]

                    result = run_create_payment_links(
                        data, secrets, familles_euros, tarifs_speciaux,
                        use_on_behalf, selected_teachers, ctx["DATA_DIR"], callback,
                        payment_method_types=payment_method_types,
                        target_family_ids=target_family_ids,
                        skip_if_exists=True,
                    )

                    if result["success"]:
                        st.session_state.regenerated_families = target_family_ids
                        st.session_state.show_goto_invoices = True
                        st.session_state.show_payment_report = True
                        st.session_state.payment_links_notice = "✅ Relance terminée !"
                        st.rerun()
                    else:
                        st.error(f"❌ Erreur : {result['error']}")

        # Bouton principal
        if st.button("🚀 Générer les liens", type="primary", width="stretch", key="gen_all_links"):
            familles_euros = ctx["load_familles_euros"]()
            tarifs_speciaux = ctx["load_tarifs_speciaux"]()
            
            progress = st.progress(0)
            status = st.empty()
            
            def callback(p, m):
                progress.progress(p)
                status.info(m)
            
            # Mode sans transfert
            if no_split_mode:
                if not secrets_no_prof:
                    st.error("❌ secrets_no_prof.yaml manquant !")
                    result = None
                else:
                    result = run_create_payment_links_no_split(
                        data, secrets_no_prof, familles_euros,
                        ctx["DATA_DIR"], callback,
                        payment_method_types=payment_method_types,
                        additional_amounts=additional_amounts,
                    )
                    
                    if result["success"]:
                        st.session_state.payment_links_notice = f"✅ **{result['links_count']}** liens créés (mode sans transfert)"
                        st.success(st.session_state.payment_links_notice)
                    else:
                        st.error(f"❌ Erreur : {result['error']}")
            else:
                # Mode normal avec split
                result = run_create_payment_links(
                    data, secrets, familles_euros, tarifs_speciaux,
                    use_on_behalf, selected_teachers, ctx["DATA_DIR"], callback,
                    payment_method_types=payment_method_types,
                    additional_amounts=additional_amounts,
                )
            
            if result and result["success"]:
                st.session_state.show_payment_report = True
                st.session_state.no_split_mode_active = no_split_mode  # Mémoriser le mode
                if not no_split_mode:
                    st.session_state.payment_links_notice = f"✅ **{result['links_count']}** liens générés avec succès"
                st.rerun()
            elif result:
                st.error(f"❌ Erreur : {result['error']}")
        
        # Bouton vers génération factures (après régénération)
        if st.session_state.get("show_goto_invoices"):
            st.markdown("---")
            st.success("✅ Liens régénérés ! Vous pouvez maintenant régénérer les factures correspondantes.")
            if st.button("📄 Aller à Régénérer les factures →", type="primary", width="stretch", key="goto_invoices"):
                st.session_state.current_page = "invoices"
                st.session_state.invoices_tab = "regen"
                st.session_state.show_goto_invoices = False
                st.session_state.show_payment_report = False
                st.rerun()
    
    # ===========================
    # TAB 2: Régénérer pour certaines familles
    # ===========================
    with tab2:
        st.markdown("### 🔄 Régénérer liens pour certaines familles")
        
        st.info("""
        **Utilisez cette option pour :**
        - Corriger un lien de paiement incorrect
        - Régénérer un lien expiré
        - Modifier le montant d'une famille spécifique
        
        ⚠️ Les anciens liens seront remplacés.
        """)
        
        # Bloquer si profs manquants
        if missing_teachers:
            st.error("⛔ Vous devez d'abord configurer tous les professeurs avant de générer les liens.")
            return
        
        # Liste des familles
        family_list = [(fam_id, fam.get("parent_name", fam_id)) for fam_id, fam in data.items()]
        family_names = [f"{name} ({fam_id})" for fam_id, name in family_list]
        
        selected_families_display = st.multiselect(
            "📋 Sélectionnez les familles",
            family_names,
            key="select_families_regen"
        )
        
        # Extraire les IDs
        selected_family_ids = []
        for sel in selected_families_display:
            for fam_id, name in family_list:
                if f"{name} ({fam_id})" == sel:
                    selected_family_ids.append(fam_id)
        
        if selected_family_ids:
            st.info(f"📊 **{len(selected_family_ids)}** famille(s) sélectionnée(s)")
            
            # Options
            use_on_behalf_t2, selected_teachers_t2, payment_method_types_t2, no_split_t2, secrets_no_prof_t2 = _render_payment_options(ctx, secrets, "tab2")
            
            if st.button("🔄 Régénérer les liens sélectionnés", type="primary", width="stretch", key="regen_selected"):
                familles_euros = ctx["load_familles_euros"]()
                tarifs_speciaux = ctx["load_tarifs_speciaux"]()
                
                progress = st.progress(0)
                status = st.empty()
                
                def callback(p, m):
                    progress.progress(p)
                    status.info(m)
                
                if no_split_t2:
                    if not secrets_no_prof_t2:
                        st.error("❌ secrets_no_prof.yaml manquant !")
                    else:
                        result = run_create_payment_links_no_split(
                            data, secrets_no_prof_t2, familles_euros,
                            ctx["DATA_DIR"], callback,
                            payment_method_types=payment_method_types_t2,
                            target_family_ids=selected_family_ids,
                            skip_if_exists=False,
                        )
                else:
                    result = run_create_payment_links(
                        data, secrets, familles_euros, tarifs_speciaux,
                        use_on_behalf_t2, selected_teachers_t2, ctx["DATA_DIR"], callback,
                        payment_method_types=payment_method_types_t2,
                        target_family_ids=selected_family_ids,
                        skip_if_exists=False,  # Forcer la régénération
                    )
                
                if result["success"]:
                    st.session_state.regenerated_families = selected_family_ids
                    st.session_state.show_goto_invoices_tab2 = True
                    st.session_state.payment_links_notice = f"✅ **{result['links_count']}** liens régénérés !"
                    st.rerun()
                else:
                    st.error(f"❌ Erreur : {result['error']}")
            
            # Bouton vers génération factures — INLINE
            if st.session_state.get("show_goto_invoices_tab2"):
                st.markdown("---")
                st.success(st.session_state.get("payment_links_notice", "✅ Liens régénérés !"))
                st.markdown("### 📄 Étape suivante — Générer la facture")
                
                regen_fam_ids = st.session_state.get("regenerated_families", [])
                regen_names = [data[fid].get("parent_name", fid) for fid in regen_fam_ids if fid in data]
                st.info(f"Famille(s) : **{', '.join(regen_names)}**")
                
                # Choix du dossier
                mode_regen_t2, selected_folder_regen_t2 = _render_invoice_folder_selector(
                    "invoice_folder_mode_regen_t2", "invoice_folder_select_regen_t2", default_to_latest=False
                )
                
                candidates = [
                    os.path.join(ctx["BASE_DIR"], "Professor_logo_dernier.png"),
                    os.path.join(ctx["BASE_DIR"], "assets", "logo.png"),
                ]
                logo_path = next((p for p in candidates if os.path.exists(p)), None)
                
                if st.button("📄 Générer la facture maintenant", type="primary", width="stretch", key="gen_invoice_inline_t2"):
                    familles_euros = ctx["load_familles_euros"]()
                    
                    target_folder_path = None
                    force_new_folder = mode_regen_t2 == "Créer un nouveau dossier"
                    if mode_regen_t2 == "Utiliser un dossier existant" and selected_folder_regen_t2:
                        target_folder_path = _ensure_local_invoice_folder(selected_folder_regen_t2)
                        if not target_folder_path:
                            st.error("❌ Impossible de charger le dossier sélectionné depuis Google Drive.")
                            return
                    
                    progress = st.progress(0)
                    status = st.empty()
                    
                    def callback(p, m):
                        progress.progress(p)
                        status.info(m)
                    
                    filtered_data = {fid: fam for fid, fam in data.items() if fid in regen_fam_ids}
                    result = run_generate_invoices(
                        filtered_data, secrets, familles_euros, ctx["DATA_DIR"], ctx["BASE_DIR"], logo_path, callback,
                        target_folder_path=target_folder_path,
                        force_new_folder=force_new_folder,
                    )
                    if result["success"]:
                        folder_used = result.get("folder")
                        nb_invoices = result.get("invoices", 0)
                        drive_saved = result.get("drive_saved", False)
                        st.success(f"✅ **{nb_invoices}** facture(s) générée(s) dans **{os.path.basename(folder_used)}**")
                        if drive_saved:
                            st.caption("☁️ Uploadé sur Google Drive")
                        else:
                            st.warning(f"⚠️ PDF non uploadé sur Drive (invoices={nb_invoices}, drive_saved={drive_saved}, folder={folder_used})")
                        if result.get("links_missing"):
                            st.warning(f"⚠️ Liens manquants : {', '.join(result['links_missing'])}")
                        st.session_state.show_goto_invoices_tab2 = False
                        
                        # Proposer le téléchargement
                        generated_files = result.get("generated_files", [])
                        if generated_files:
                            # Nom du ZIP basé sur les familles
                            regen_label = "_".join(n.replace(" ", "_") for n in regen_names[:3])
                            if len(regen_names) > 3:
                                regen_label += f"_+{len(regen_names)-3}"
                            
                            import zipfile
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                                for fp in generated_files:
                                    if os.path.exists(fp):
                                        zf.write(fp, os.path.basename(fp))
                            zip_buffer.seek(0)
                            st.download_button(
                                "⬇️ Télécharger la/les facture(s)",
                                data=zip_buffer.getvalue(),
                                file_name=f"Factures_{regen_label}.zip",
                                mime="application/zip",
                                key="dl_regen_invoices_t2",
                            )
                    else:
                        st.error(f"❌ Erreur : {result['error']}")
                
                st.markdown("---")
                st.caption("Ou, si vous préférez passer par la page Factures :")
                if st.button("📄 Aller à la page Factures →", width="stretch", key="goto_invoices_t2"):
                    st.session_state.current_page = "invoices"
                    st.session_state.invoices_tab = "regen"
                    st.session_state.show_goto_invoices_tab2 = False
                    st.rerun()
        else:
            st.warning("⚠️ Sélectionnez au moins une famille.")

def _render_payment_options(ctx, secrets, prefix):
    """Rend les options de paiement (On Behalf Of + Méthodes) et retourne les valeurs.
    
    Returns:
        tuple: (use_on_behalf, selected_teachers, payment_method_types, no_split_mode, secrets_no_prof)
    """
    
    # ===========================
    # MODE SANS TRANSFERT
    # ===========================
    st.markdown("### 💰 Mode de paiement")
    
    no_split_mode = st.toggle(
        "🏦 Tout recevoir sur mon compte (sans transfert aux profs)",
        value=True,
        key=f"no_split_{prefix}",
        help="Active le mode sans split : tous les paiements vont directement sur votre compte Stripe principal"
    )
    
    # Méthodes de paiement (communes aux deux modes)
    st.markdown("### 💳 Méthodes de paiement")

    col1, col2 = st.columns(2)

    with col1:
        pm_card = st.checkbox("💳 Carte bancaire", value=True, key=f"pm_card_{prefix}")
        pm_link = st.checkbox("🔗 Link", value=True, key=f"pm_link_{prefix}")

    with col2:
        pm_apple = st.checkbox("🍎 Apple Pay", value=True, key=f"pm_apple_{prefix}")
        pm_google = st.checkbox("🤖 Google Pay", value=True, key=f"pm_google_{prefix}")

    payment_method_types = []

    if pm_card or pm_apple or pm_google:
        payment_method_types.append("card")
    if pm_link:
        payment_method_types.append("link")

    if not payment_method_types:
        payment_method_types = ["card"]
    
    st.warning("⚠️ Vérifiez dans les paramètres Stripe que ces méthodes sont bien actives !")
    
    if no_split_mode:
        st.warning("⚠️ **Mode sans transfert activé** — Aucun split ne sera créé. Tous les paiements iront sur le compte Stripe défini dans `secrets_no_prof.yaml`.")
        
        secrets_no_prof = ctx.get("load_secrets_no_prof", lambda: None)()
        if not secrets_no_prof:
            st.error("❌ `secrets_no_prof.yaml` non trouvé dans config/ ou à la racine du projet.")
            st.info("Créez ce fichier avec votre clé Stripe alternative (même structure que secrets.yaml mais sans teachers).")
            return None, None, payment_method_types, True, None
        
        return None, None, payment_method_types, True, secrets_no_prof
    
    # --- Mode normal avec split ---
    st.markdown("### 👨‍🏫 On Behalf Of")
    
    use_on_behalf = st.checkbox("🔄 Activer On Behalf Of", value=True, key=f"use_on_behalf_{prefix}")
    
    selected_teachers = []
    if use_on_behalf:
        teachers = secrets.get("teachers", {})
        teachers_with_connect = [n for n, i in teachers.items() if i.get("connect_account_id")]
        
        selected_teachers = st.multiselect(
            "Professeurs pour On Behalf Of",
            teachers_with_connect,
            default=teachers_with_connect,
            key=f"selected_teachers_{prefix}"
        )
    
    return use_on_behalf, selected_teachers, payment_method_types, False, None




def _parse_invoice_folder_dt(folder_name):
    date_part = folder_name.split(" - ")[-1]
    for fmt in ("%d-%m-%Y %Hh%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_part, fmt)
        except Exception:
            pass
    return datetime.min


def _folder_source_label(folder):
    source = (folder or {}).get("source", "local")
    if source == "both":
        return "Local + Drive"
    if source == "drive":
        return "Drive"
    return "Local"


def _invoice_folder_choices():
    folders = list_invoice_folders()
    choices = []
    for f in folders:
        label = f"{f['month']} · {_folder_source_label(f)}"
        choices.append((label, f))
    return choices


def _ensure_local_invoice_folder(folder):
    if not folder:
        return None

    folder_path = folder.get("path")
    source = str(folder.get("source", "")).lower()

    # 1) Si le dossier local existe ET contient déjà des PDFs, on l'utilise tel quel.
    if folder_path and os.path.exists(folder_path):
        for root, _, files in os.walk(folder_path):
            if any(f.lower().endswith(".pdf") for f in files):
                return folder_path

    # 2) Si le dossier existe aussi sur Drive (source=drive ou both), on le recharge depuis Drive.
    # Cela évite qu'après un reboot du runtime Streamlit, on garde un chemin local vide/stale.
    if source in {"drive", "both"}:
        result = load_invoice_folder(folder.get("year"), folder.get("month"))
        if result.get("success") and result.get("local_path"):
            return result.get("local_path")

    # 3) Dernier fallback : si le chemin local existe encore, on le renvoie quand même.
    if folder_path and os.path.exists(folder_path):
        return folder_path

    return None


def _render_invoice_folder_selector(mode_key, selection_key, default_to_latest=True):
    choices = _invoice_folder_choices()
    mode = st.radio(
        "📁 Dossier de travail",
        ["Créer un nouveau dossier", "Utiliser un dossier existant"],
        horizontal=True,
        key=mode_key,
        index=1 if (choices and not default_to_latest) else 0,
    )
    selected_folder = None
    if mode == "Utiliser un dossier existant":
        if not choices:
            st.warning("⚠️ Aucun dossier existant trouvé. Un nouveau dossier sera créé.")
            mode = "Créer un nouveau dossier"
        else:
            labels = [c[0] for c in choices]
            default_index = 0
            selected_label = st.selectbox("Choisir un dossier", labels, index=default_index, key=selection_key)
            selected_folder = dict(choices[labels.index(selected_label)][1])
            st.info(
                f"📂 Dossier sélectionné : **{selected_folder['month']}** "
                f"({_folder_source_label(selected_folder)})"
            )
    else:
        st.info("📁 Un nouveau dossier sera créé. Si un dossier existe déjà aujourd'hui, l'heure sera ajoutée automatiquement au nom du dossier.")
    return mode, selected_folder


def _zip_folder_bytes(folder_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(folder_path):
            for filename in files:
                full_path = os.path.join(root, filename)
                arcname = os.path.relpath(full_path, folder_path)
                zf.write(full_path, arcname)
    buf.seek(0)
    return buf.getvalue()


def page_invoices(ctx):

    st.markdown('<div class="section-title">📄 Générer les Factures</div>', unsafe_allow_html=True)

    data = _try_load_data(ctx)
    secrets = ctx["load_secrets"]()

    if not data:
        _render_no_data_warning("la génération de factures")
        return

    default_tab = 1 if st.session_state.get("invoices_tab") == "regen" else 0
    tab1, tab2 = st.tabs(["📄 Générer toutes les factures", "🔄 Régénérer et remplacer certaines factures"])

    with tab1:
        st.info(f"📊 **{len(data)}** familles à facturer")
        links_path = os.path.join(ctx["DATA_DIR"], "payment_links_output.json")
        if not os.path.exists(links_path):
            st.warning("⚠️ Les liens de paiement n'ont pas été générés.")

        mode, selected_folder = _render_invoice_folder_selector("invoice_folder_mode_all", "invoice_folder_select_all")

        save_local_copy = st.checkbox(
            "💾 Sauvegarder aussi une copie sur cet ordinateur",
            value=False,
            key="save_invoice_copy_local_pc",
            help="Depuis Streamlit Cloud, l'application ne peut pas écrire directement sur votre PC. Si vous cochez cette case, une copie téléchargeable du dossier sera proposée après génération."
        )
        if is_streamlit_cloud():
            st.caption("Depuis Streamlit Cloud, la sauvegarde sur l'ordinateur passe par un téléchargement manuel après génération.")
        else:
            st.caption("En exécution locale, les fichiers sont déjà créés sur votre ordinateur.")

        candidates = [
            os.path.join(ctx["BASE_DIR"], "Professor_logo_dernier.png"),
            os.path.join(ctx["BASE_DIR"], "assets", "logo.png"),
        ]
        logo_path = next((p for p in candidates if os.path.exists(p)), None)
        if not logo_path:
            st.warning("⚠️ Logo non trouvé")

        # ===========================
        # OPTION : INCLURE LES IMPAYÉS n-2 (depuis Notion)
        # ===========================
        include_unpaid = st.checkbox(
            "📌 ⚠️ Inclure les cours impayés des mois précédents",
            value=False,
            key="include_unpaid_previous_months",
            help="Si coché, l'app lit dans Notion les lignes impayées du mois n-2 et les ajoute comme section 'Rappel' dans la facture PDF. Le montant total (et le lien Stripe) couvriront l'ensemble."
        )
        
        previous_unpaid_data = None
        previous_month_label = None
        
        if include_unpaid:
            st.markdown("---")
            st.markdown("##### 📋 Détection des impayés n-2 (Notion)")
            st.caption("Sélectionnez le mois n-2 à vérifier. L'app interroge directement Notion « Paiements – Base Centrale » pour les lignes impayées de ce mois.")
            
            # Proposer les mois disponibles (n-2 par défaut = 2 mois en arrière)
            available_months = []
            try:
                today_dt = datetime.today()
                for months_back in range(1, 7):  # 6 mois en arrière max
                    m = today_dt.month - months_back
                    y = today_dt.year
                    while m <= 0:
                        m += 12
                        y -= 1
                    MONTHS_FR_LOCAL = ctx["MONTHS_FR"]
                    label = f"{MONTHS_FR_LOCAL[m - 1]} {y}"
                    available_months.append((label, y, m))
            except Exception:
                pass
            
            if available_months:
                month_labels = [m[0] for m in available_months]
                # Par défaut n-2 (index 1 = 2 mois en arrière)
                default_idx = min(1, len(month_labels) - 1)
                selected_unpaid_month = st.selectbox(
                    "Mois à vérifier (impayés n-2)",
                    month_labels,
                    index=default_idx,
                    key="select_unpaid_month_n2",
                )
                
                if selected_unpaid_month:
                    # Trouver le year/month correspondant
                    sel_year, sel_month = None, None
                    for label, y, m in available_months:
                        if label == selected_unpaid_month:
                            sel_year, sel_month = y, m
                            break
                    
                    if st.button("🔍 Détecter les impayés depuis Notion", key="load_unpaid_notion_n2"):
                        with st.spinner(f"Interrogation de Notion pour {selected_unpaid_month}..."):
                            n2_result = fetch_unpaid_n2(secrets, sel_year, sel_month)
                        
                        if n2_result["success"] and n2_result["families"]:
                            previous_month_label = n2_result["month_label"]
                            
                            # Convertir en format compatible avec generate_invoices (previous_unpaid_data)
                            # Le format attendu est {family_id: {"lessons": [...], "parent_name": ..., ...}}
                            # On utilise le nom normalisé comme family_id temporaire
                            from scripts.send_payment_reminders import normalize as _norm_n2
                            previous_unpaid_data = {}
                            
                            for norm_key, fam_info in n2_result["families"].items():
                                # Chercher le vrai family_id dans data
                                matched_fam_id = None
                                for fid, fam in data.items():
                                    parent = fam.get("parent_name") or fam.get("family_name") or ""
                                    if _norm_n2(parent) == norm_key:
                                        matched_fam_id = fid
                                        break
                                
                                if not matched_fam_id:
                                    # Utiliser un ID synthétique
                                    matched_fam_id = f"notion_unpaid_{norm_key.replace(' ', '_')}"
                                
                                # Construire les leçons depuis les lignes Notion
                                lessons = []
                                for row in fam_info["rows"]:
                                    # Reconstituer une leçon compatible
                                    heures_str = row.get("heures", "0")
                                    try:
                                        heures_val = float(heures_str.replace("h", "").replace(",", ".").strip())
                                    except (ValueError, AttributeError):
                                        heures_val = 0
                                    
                                    # Convert Notion date YYYY-MM-DD to DD.MM.YYYY
                                    raw_date = row.get("date_cours_start", "")
                                    converted_date = ""
                                    if raw_date and len(raw_date) == 10 and "-" in raw_date:
                                        try:
                                            parts = raw_date.split("-")
                                            converted_date = f"{parts[2]}.{parts[1]}.{parts[0]}"
                                        except (IndexError, ValueError):
                                            converted_date = ""
                                    
                                    lessons.append({
                                        "date": converted_date,
                                        "time": "00:00",
                                        "student": row.get("eleve", ""),
                                        "teacher": row.get("prof", ""),
                                        "duration_min": int(heures_val * 60) if heures_val else 0,
                                        "amount": row.get("montant", 0),
                                        "attendance_status": "Present",
                                    })
                                
                                previous_unpaid_data[matched_fam_id] = {
                                    "family_id": matched_fam_id,
                                    "parent_name": fam_info["parent_name"],
                                    "lessons": lessons,
                                    "total_courses": fam_info["total_amount"],
                                    "currency": fam_info.get("currency", "CHF").lower(),
                                }
                            
                            st.session_state["_previous_unpaid_data"] = previous_unpaid_data
                            st.session_state["_previous_month_label"] = previous_month_label
                            # Stocker aussi les familles n2 brutes pour la désactivation Stripe
                            st.session_state["_unpaid_n2_families"] = n2_result["families"]
                            
                            st.success(f"✅ **{len(previous_unpaid_data)}** famille(s) avec impayés détectés pour {previous_month_label}")
                            
                            # Afficher le détail
                            with st.expander(f"📋 Détail des impayés — {previous_month_label}", expanded=False):
                                for fam_id, fam_data in previous_unpaid_data.items():
                                    total = fam_data.get("total_courses", 0)
                                    st.write(f"**{fam_data['parent_name']}** — {total:.2f} {fam_data.get('currency', 'CHF').upper()}")
                                    for L in fam_data["lessons"]:
                                        st.caption(f"  • {L.get('teacher', '')} / {L.get('student', '')} — {L.get('amount', 0):.2f}")
                        
                        elif n2_result["success"] and not n2_result["families"]:
                            st.success(f"✅ Aucun impayé trouvé pour {n2_result.get('month_label', selected_unpaid_month)} — toutes les familles ont payé !")
                            st.session_state.pop("_previous_unpaid_data", None)
                            st.session_state.pop("_previous_month_label", None)
                            st.session_state.pop("_unpaid_n2_families", None)
                        else:
                            st.error(f"❌ Erreur Notion : {n2_result.get('error', 'Erreur inconnue')}")
            else:
                st.warning("⚠️ Impossible de déterminer les mois disponibles.")
        
        # Récupérer depuis session_state si déjà chargé
        if include_unpaid and "_previous_unpaid_data" in st.session_state:
            previous_unpaid_data = st.session_state.get("_previous_unpaid_data")
            previous_month_label = st.session_state.get("_previous_month_label")
            if previous_unpaid_data:
                st.info(f"📦 Impayés Notion chargés : **{len(previous_unpaid_data)}** famille(s) — {previous_month_label}")

        st.markdown("---")

        if st.button("📄 Générer les factures", type="primary", width="stretch", key="gen_all_invoices"):
            familles_euros = ctx["load_familles_euros"]()
            progress = st.progress(0)
            status = st.empty()

            def callback(p, m):
                progress.progress(p)
                status.info(m)

            target_folder_path = None
            force_new_folder = mode == "Créer un nouveau dossier"
            if mode == "Utiliser un dossier existant" and selected_folder:
                target_folder_path = _ensure_local_invoice_folder(selected_folder)
                if not target_folder_path:
                    st.error("❌ Impossible de charger le dossier sélectionné depuis Google Drive.")
                    return

            result = run_generate_invoices(
                data, secrets, familles_euros, ctx["DATA_DIR"], ctx["BASE_DIR"], logo_path, callback,
                target_folder_path=target_folder_path,
                force_new_folder=force_new_folder,
                previous_unpaid_data=previous_unpaid_data if include_unpaid else None,
                previous_month_label=previous_month_label if include_unpaid else None,
            )

            if result["success"]:
                folder_used = result.get("folder")
                generated_files = result.get("generated_files", [])
                source_for_state = "both" if result.get("drive_saved") else "local"
                st.session_state.invoice_work_folder = {
                    "path": folder_used,
                    "name": os.path.basename(folder_used) if folder_used else "",
                    "year": os.path.basename(os.path.dirname(folder_used)) if folder_used else "",
                    "month": os.path.basename(folder_used) if folder_used else "",
                    "source": source_for_state,
                }
                st.success(f"✅ **{result['invoices']}** factures créées")
                st.info(f"📁 Dossier utilisé : **{os.path.basename(folder_used)}**")
                drive_status = "Local + Drive" if result.get("drive_saved") else "Local"
                st.caption(f"Source confirmée : **{drive_status}**")
                if generated_files:
                    st.caption(f"{len(generated_files)} PDF(s) généré(s) dans ce dossier.")
                if save_local_copy and folder_used and os.path.exists(folder_used):
                    zip_bytes = _zip_folder_bytes(folder_used)
                    st.download_button(
                        "⬇️ Télécharger une copie locale du dossier",
                        data=zip_bytes,
                        file_name=f"{os.path.basename(folder_used)}.zip",
                        mime="application/zip",
                        key=f"download_invoice_folder_{os.path.basename(folder_used)}",
                        width="stretch",
                    )
            else:
                st.error(f"❌ Erreur : {result['error']}")

    with tab2:
        st.markdown("### 🔄 Remplacer factures pour certaines familles")
        mode_regen, selected_folder_regen = _render_invoice_folder_selector("invoice_folder_mode_regen", "invoice_folder_select_regen", default_to_latest=False)
        if mode_regen != "Utiliser un dossier existant":
            st.warning("⚠️ Pour remplacer des factures existantes, sélectionnez un dossier existant.")
            return
        if not selected_folder_regen:
            st.error("❌ Aucun dossier de factures existant. Générez d'abord toutes les factures.")
            return
        selected_folder_path = _ensure_local_invoice_folder(selected_folder_regen)
        if not selected_folder_path:
            st.error("❌ Impossible de charger le dossier sélectionné depuis Google Drive.")
            return

        st.info("""
        💡 **Pour générer une ou plusieurs factures**, rendez-vous d'abord dans l'onglet
        **Créer liens paiement** → **Régénérer pour certaines familles**.
        """)
        if st.button("💳 Aller à « Régénérer liens pour certaines familles »", key="goto_payment_regen"):
            st.session_state.current_page = "payment"
            st.rerun()

        st.markdown("---")
        st.warning(f"⚠️ **Attention** : Les nouvelles factures remplaceront celles existantes dans le dossier : **{selected_folder_regen['month']}**")
        st.info("""
        💡 **Note** : La mise à jour Notion n'est nécessaire que si le **prix** ou les **horaires** ont changé.
        Si vous corrigez uniquement une erreur de mise en page, pas besoin de mettre à jour Notion.
        
        📅 La colonne **Invoice Date modified** sera automatiquement remplie avec la date de régénération.
        """)

        preselected = st.session_state.get("regenerated_families", [])
        family_list = [(fam_id, fam.get("parent_name", fam_id)) for fam_id, fam in data.items()]
        family_names = [f"{name} ({fam_id})" for fam_id, name in family_list]
        default_selection = [f"{name} ({fid})" for fid, name in family_list if fid in preselected]
        selected_families_display = st.multiselect("📋 Sélectionnez les familles", family_names, default=default_selection, key="select_families_invoices_regen")
        selected_family_ids = []
        for sel in selected_families_display:
            for fam_id, name in family_list:
                if f"{name} ({fam_id})" == sel:
                    selected_family_ids.append(fam_id)

        if selected_family_ids:
            st.info(f"📊 **{len(selected_family_ids)}** famille(s) sélectionnée(s)")
            if st.button("🔄 Régénérer les factures sélectionnées", type="primary", width="stretch", key="regen_invoices"):
                familles_euros = ctx["load_familles_euros"]()
                candidates = [
                    os.path.join(ctx["BASE_DIR"], "Professor_logo_dernier.png"),
                    os.path.join(ctx["BASE_DIR"], "assets", "logo.png"),
                ]
                logo_path = next((p for p in candidates if os.path.exists(p)), None)
                progress = st.progress(0)
                status = st.empty()

                def callback(p, m):
                    progress.progress(p)
                    status.info(m)

                filtered_data = {fid: fam for fid, fam in data.items() if fid in selected_family_ids}
                result = run_generate_invoices(
                    filtered_data, secrets, familles_euros, ctx["DATA_DIR"], ctx["BASE_DIR"], logo_path, callback,
                    target_folder_path=selected_folder_path,
                )
                if result["success"]:
                    st.session_state.regenerated_invoices_families = selected_family_ids
                    st.session_state.regenerated_invoices_paths = result.get("generated_files", [])
                    st.session_state.show_download_invoices = True
                    st.success(f"✅ **{result['invoices']}** factures régénérées dans **{selected_folder_regen['month']}** !")
                    st.rerun()
                else:
                    st.error(f"❌ Erreur : {result['error']}")

            if st.session_state.get("show_download_invoices"):
                st.markdown("---")
                generated_files = st.session_state.get("regenerated_invoices_paths", [])
                if generated_files:
                    st.success(f"📄 **{len(generated_files)}** facture(s) régénérée(s)")
                    import zipfile, io
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for file_path in generated_files:
                            if os.path.exists(file_path):
                                zf.write(file_path, os.path.basename(file_path))
                    zip_buffer.seek(0)
                    st.download_button(label="📥 Télécharger les factures régénérées (ZIP)", data=zip_buffer.getvalue(), file_name="factures_regenerees.zip", mime="application/zip", width="stretch")
                    with st.expander("📋 Fichiers régénérés"):
                        for f in generated_files:
                            st.write(f"• {os.path.basename(f)}")
                st.markdown("---")
                st.info("💡 **Rappel** : Mettez à jour Notion uniquement si le prix ou les horaires ont changé.")
                if st.button("📤 Aller à Mettre à jour Notion →", width="stretch", key="goto_notion"):
                    st.session_state.current_page = "update"
                    st.session_state.update_tab = "selective"
                    st.session_state.show_download_invoices = False
                    st.rerun()
                if st.button("✅ Terminé (pas besoin de Notion)", width="stretch", key="done_no_notion"):
                    st.session_state.show_download_invoices = False
                    st.session_state.regenerated_invoices_families = []
                    st.session_state.regenerated_invoices_paths = []
                    st.rerun()
        else:
            st.warning("⚠️ Sélectionnez au moins une famille.")

def page_send(ctx):
    st.markdown('<div class="section-title">📧 Envoyer les Factures</div>', unsafe_allow_html=True)

    secrets = ctx["load_secrets"]()

    gmail_config = secrets.get("gmail", {}) if secrets else {}
    if not gmail_config.get("email") or not gmail_config.get("app_password"):
        st.error("❌ Configuration email manquante. Allez dans Paramètres > Email pour configurer.")
        if st.button("⚙️ Aller aux paramètres"):
            st.session_state.current_page = "config"
            st.rerun()
        return

    # ===========================
    # SÉLECTION DU DOSSIER DE FACTURES (fonctionne SANS extraction)
    # ===========================
    mode_send, selected_folder = _render_invoice_folder_selector("invoice_folder_mode_send", "invoice_folder_select_send", default_to_latest=False)
    if mode_send != "Utiliser un dossier existant":
        st.warning("⚠️ Sélectionnez un dossier existant pour envoyer des factures.")
        return
    if not selected_folder:
        st.warning("⚠️ Aucun dossier de factures trouvé")
        return

    folder_path = _ensure_local_invoice_folder(selected_folder)
    if not folder_path:
        st.error("❌ Impossible de charger le dossier sélectionné depuis Google Drive.")
        return

    st.info(f"📁 Dossier : **{selected_folder['month']}**")

    # ===========================
    # CHARGEMENT DES DONNÉES FAMILLES (emails) — optionnel
    # ===========================
    data = _try_load_data(ctx)

    if not data:
        st.warning("⚠️ **Données des familles non disponibles.** Les emails des parents sont nécessaires pour l'envoi.")
        if st.button("📥 Charger les données depuis TutorBird / Google Drive", key="load_tb_data_send"):
            with st.spinner("Chargement..."):
                data = _try_load_data(ctx)
                if data:
                    st.success(f"✅ {len(data)} famille(s) chargées")
                    st.rerun()
                else:
                    st.error("❌ Aucune donnée trouvée. Lancez d'abord une extraction TutorBird.")
        return

    # ===========================
    # DIAGNOSTICS ET ENVOI
    # ===========================
    month_name, year = ctx["get_month_year_from_folder"]({
        "name": selected_folder["month"],
        "date": _parse_invoice_folder_dt(selected_folder['month'])
    })
    template_fr = get_default_email_template(month_name, year, language="fr")
    template_en = get_default_email_template(month_name, year, language="en")

    diagnostics = collect_invoice_diagnostics(folder_path, data)
    st.info(
        f"📊 PDFs détectés : **{diagnostics['found_pdfs']}**  |  "
        f"Familles prêtes : **{len(diagnostics['ready_families'])}**"
    )
    if diagnostics["missing_email_families"]:
        with st.expander(f"⚠️ {len(diagnostics['missing_email_families'])} famille(s) avec PDF mais sans email"):
            for item in diagnostics["missing_email_families"]:
                st.write(f"• **{item['parent_name']}** — {item.get('invoice_count', 0)} PDF(s)")
    if diagnostics["missing_pdf_families"]:
        with st.expander(f"⚠️ {len(diagnostics['missing_pdf_families'])} famille(s) avec email mais sans PDF retrouvé"):
            for item in diagnostics["missing_pdf_families"]:
                st.write(f"• **{item['parent_name']}** — {item.get('parent_email','')}")
        
        # Bouton resync Drive pour récupérer les PDFs manquants
        source = str(selected_folder.get("source", "")).lower()
        if source in ("drive", "both"):
            if st.button("🔄 Resynchroniser les PDFs depuis Google Drive", key="resync_drive_pdfs"):
                with st.spinner("📥 Téléchargement des factures depuis Google Drive..."):
                    try:
                        resync_result = load_invoice_folder(
                            selected_folder.get("year"),
                            selected_folder.get("month"),
                        )
                        if resync_result.get("success"):
                            dl_count = resync_result.get("downloaded", 0)
                            dl_errors = resync_result.get("errors", [])
                            folder_path = resync_result.get("local_path", folder_path)
                            st.success(f"✅ {dl_count} fichier(s) téléchargé(s) depuis Drive")
                            if dl_errors:
                                with st.expander(f"⚠️ {len(dl_errors)} erreur(s) de téléchargement"):
                                    for err in dl_errors:
                                        st.write(f"• {err}")
                            st.rerun()
                        else:
                            st.error(f"❌ Erreur resync : {resync_result.get('error', 'Erreur inconnue')}")
                    except Exception as e:
                        st.error(f"❌ Erreur : {e}")

    # Récupérer les détails heures Notion pour le mail personnalisé Carole
    carole_details = ""
    if data:
        for fam in data.values():
            if fam.get("source") == "notion_hors_tb":
                for L in fam.get("lessons", []):
                    dh = L.get("notion_details_heures", "")
                    if dh:
                        carole_details = dh
                        break
                if carole_details:
                    break
    
    carole_template = {
        "subject": f"Facture - Soutien scolaire - {month_name} {year}",
        "body": f"""Bonjour,

J'espère que vous allez bien.

Veuillez trouver ci-joint la facture pour les cours de soutien scolaire du mois de {month_name} {year}.

Détails : {carole_details}

Vous pouvez régler directement en cliquant sur le bouton "Payer en ligne" dans la facture PDF.

Merci de procéder au paiement dans les plus brefs délais.

Cordialement,
Professor+
"""
    }
    
    # ===========================
    # IDENTIFIER LES FAMILLES MULTI-MOIS (avant les tabs pour l'aperçu)
    # ===========================
    _multimonth_ids = set()
    _prev_unpaid = st.session_state.get("_previous_unpaid_data")
    if _prev_unpaid:
        _multimonth_ids = set(_prev_unpaid.keys())
    if not _multimonth_ids:
        try:
            _plinks_path = os.path.join(ctx["DATA_DIR"], "payment_links_output.json")
            if os.path.exists(_plinks_path):
                with open(_plinks_path, "r", encoding="utf-8") as f:
                    _plinks_data = json.load(f)
                for _pl in _plinks_data:
                    if _pl.get("includes_previous_months") == "true" or str(_pl.get("metadata", {}).get("includes_previous_months", "")) == "true":
                        _fid = _pl.get("family_id", "")
                        if _fid:
                            _multimonth_ids.add(_fid)
        except Exception:
            pass
    
    # ===========================
    # PRÉ-CALCUL : répartition des familles par template
    # ===========================
    _fam_by_template = {"fr": [], "en": [], "carole": [], "multi": []}
    for _fam in diagnostics["ready_families"]:
        _fid = _fam.get("family_id", "")
        _fname = _fam["parent_name"]
        _fdata = data.get(_fid, {})
        _is_multi = bool(_multimonth_ids and _fid in _multimonth_ids)
        
        # Détection Carole : par nom uniquement (template OCTOPUS toujours custom)
        _is_carole_t = ("carole" in _fname.lower() and "tessier" in _fname.lower())
        
        # Détection anglais : depuis les données OU depuis ready_families
        _lang_t = str(_fdata.get("language") or _fam.get("language") or "fr").strip().lower()
        _is_en_t = _lang_t in {"anglais", "english", "en"}
        
        if _is_multi:
            _fam_by_template["multi"].append(_fname)
        elif _is_carole_t:
            _fam_by_template["carole"].append(_fname)
        elif _is_en_t:
            _fam_by_template["en"].append(_fname)
        else:
            _fam_by_template["fr"].append(_fname)
    
    tab_fr, tab_en, tab_carole, tab_multimonth = st.tabs([
        f"🇫🇷 Template français ({len(_fam_by_template['fr'])})",
        f"🇬🇧 Template anglais ({len(_fam_by_template['en'])})",
        f"👩 Carole Tessier ({len(_fam_by_template['carole'])})",
        f"📌 Multi-mois ({len(_fam_by_template['multi'])})",
    ])
    with tab_fr:
        if _fam_by_template["fr"]:
            st.caption(f"👥 **{len(_fam_by_template['fr'])}** famille(s) : " + ", ".join(_fam_by_template["fr"]))
        else:
            st.caption("👥 Aucune famille pour ce template")
        subject = st.text_input("📝 Sujet", value=template_fr["subject"], key="invoice_mail_subject_fr")
        body = st.text_area("✉️ Message", value=template_fr["body"], height=250, key="invoice_mail_body_fr")
    with tab_en:
        if _fam_by_template["en"]:
            st.caption(f"👥 **{len(_fam_by_template['en'])}** famille(s) : " + ", ".join(_fam_by_template["en"]))
        else:
            st.caption("👥 Aucune famille pour ce template")
        subject_en = st.text_input("📝 Subject", value=template_en["subject"], key="invoice_mail_subject_en")
        body_en = st.text_area("✉️ Message", value=template_en["body"], height=250, key="invoice_mail_body_en")
    with tab_carole:
        if _fam_by_template["carole"]:
            st.caption(f"👥 **{len(_fam_by_template['carole'])}** famille(s) : " + ", ".join(_fam_by_template["carole"]))
        else:
            st.caption("👥 Aucune famille pour ce template")
        if carole_details:
            st.caption(f"📋 Détails heures Notion : **{carole_details}**")
        subject_carole = st.text_input("📝 Sujet", value=carole_template["subject"], key="invoice_mail_subject_carole")
        body_carole = st.text_area("✉️ Message", value=carole_template["body"], height=250, key="invoice_mail_body_carole")
    with tab_multimonth:
        if _fam_by_template["multi"]:
            st.caption(f"👥 **{len(_fam_by_template['multi'])}** famille(s) : " + ", ".join(_fam_by_template["multi"]))
        else:
            st.caption("👥 Aucune famille pour ce template")
        unpaid_month_label = st.session_state.get("_previous_month_label", "mois précédent")
        multimonth_template = get_default_multimonth_template(month_name, year, unpaid_month_label)
        st.caption(f"📌 Ce template est utilisé automatiquement pour les familles ayant des impayés de mois précédents inclus dans leur facture.")
        subject_multi = st.text_input("📝 Sujet", value=multimonth_template["subject"], key="invoice_mail_subject_multi")
        body_multi = st.text_area("✉️ Message", value=multimonth_template["body"], height=250, key="invoice_mail_body_multi")

    st.markdown("---")
    st.markdown("### 📬 Options d'envoi")
    col1, col2 = st.columns(2)
    with col1:
        send_all = st.radio("Envoyer à :", ["Toutes les familles", "Sélection personnalisée"], key="send_mode")
    with col2:
        send_test = st.checkbox("📧 Envoyer d'abord à moi-même (test)", value=True)

    families = diagnostics["ready_families"]
    family_names = [f["parent_name"] for f in families]
    selected_invoice_names = family_names.copy()
    if send_all == "Sélection personnalisée":
        selected_invoice_names = st.multiselect(
            "Sélectionner les familles",
            family_names,
            default=family_names,
            key="invoice_selected_families"
        )

    excluded_invoice_names = st.multiselect(
        "Ne pas envoyer à ces familles",
        selected_invoice_names,
        key="invoice_excluded_families"
    )
    final_invoice_names = [name for name in selected_invoice_names if name not in excluded_invoice_names]
    selected_families = [f["family_id"] for f in families if f["parent_name"] in final_invoice_names]

    if send_test:
        if st.button("📧 Envoyer le test à moi-même", width="stretch"):
            if not final_invoice_names:
                st.warning("⚠️ Aucune famille sélectionnée pour l'envoi.")
            else:
                progress = st.progress(0)
                status = st.empty()

                def callback(p, m):
                    progress.progress(p)
                    status.info(m)

                result = run_send_invoices(
                    secrets, data, folder_path,
                    custom_subject=subject, custom_body=body,
                    custom_subject_en=subject_en, custom_body_en=body_en,
                    custom_subject_carole=subject_carole, custom_body_carole=body_carole,
                    custom_subject_multi=subject_multi, custom_body_multi=body_multi,
                    multimonth_family_ids=_multimonth_ids if _multimonth_ids else None,
                    selected_families=selected_families,
                    send_to_test=True, callback=callback
                )
                if result["success"]:
                    st.success(f"✅ Test envoyé à {gmail_config['email']}")
                    st.caption(
                        f"PDFs détectés : {result.get('found_pdfs', 0)} | "
                        f"Familles prêtes : {result.get('matched_families', result.get('total', 0))}"
                    )
                    if result.get("missing_email_families"):
                        st.warning("Familles ignorées car email manquant : " + ", ".join(x["parent_name"] for x in result["missing_email_families"]))
                    if result.get("missing_pdf_families"):
                        st.warning("Familles ignorées car PDF non retrouvé : " + ", ".join(x["parent_name"] for x in result["missing_pdf_families"]))
                else:
                    st.error(f"❌ Erreur : {result['error']}")
                    if result.get("found_pdfs") is not None:
                        st.caption(
                            f"PDFs détectés : {result.get('found_pdfs', 0)} | "
                            f"Familles prêtes : {result.get('matched_families', 0)}"
                        )
                    if result.get("missing_email_families"):
                        st.warning("Familles avec PDF mais sans email : " + ", ".join(x["parent_name"] for x in result["missing_email_families"]))
                    if result.get("missing_pdf_families"):
                        st.warning("Familles avec email mais sans PDF retrouvé : " + ", ".join(x["parent_name"] for x in result["missing_pdf_families"]))

    if st.button("📧 Envoyer les factures aux clients", type="primary", width="stretch"):
        if not final_invoice_names:
            st.warning("⚠️ Aucune famille sélectionnée pour l'envoi.")
        else:
            progress = st.progress(0)
            status = st.empty()

            def callback(p, m):
                progress.progress(p)
                status.info(m)

            result = run_send_invoices(
                secrets, data, folder_path,
                custom_subject=subject, custom_body=body,
                custom_subject_en=subject_en, custom_body_en=body_en,
                custom_subject_carole=subject_carole, custom_body_carole=body_carole,
                custom_subject_multi=subject_multi, custom_body_multi=body_multi,
                multimonth_family_ids=_multimonth_ids if _multimonth_ids else None,
                selected_families=selected_families,
                send_to_test=False, callback=callback
            )
            if result["success"]:
                st.success(f"✅ **{result['sent']}/{result['total']}** emails envoyés")
                # Mettre à jour System-Metadata (envoi réel uniquement)
                _update_metadata(secrets, "last_invoice_sent_date", date_value=datetime.today().strftime("%Y-%m-%d"))
                
                # ===========================
                # DÉSACTIVATION DES ANCIENS LIENS STRIPE (impayés n-2)
                # ===========================
                unpaid_n2_fams = st.session_state.get("_unpaid_n2_families")
                if unpaid_n2_fams:
                    st.info("🔒 Désactivation des anciens liens Stripe pour les familles avec impayés consolidés...")
                    try:
                        # Charger payment_links_output.json pour lookup des plink IDs
                        plinks_list = None
                        try:
                            plinks_path = os.path.join(ctx["DATA_DIR"], "payment_links_output.json")
                            if os.path.exists(plinks_path):
                                with open(plinks_path, "r", encoding="utf-8") as f:
                                    plinks_list = json.load(f)
                        except Exception:
                            pass
                        
                        deact_result = deactivate_old_payment_links(
                            secrets, unpaid_n2_fams,
                            payment_links_output=plinks_list,
                        )
                        if deact_result.get("deactivated", 0) > 0:
                            st.success(f"🔒 **{deact_result['deactivated']}** ancien(s) lien(s) Stripe désactivé(s)")
                        if deact_result.get("skipped", 0) > 0:
                            st.caption(f"⏭️ {deact_result['skipped']} lien(s) ignoré(s) (déjà inactifs ou non trouvés)")
                        if deact_result.get("errors"):
                            with st.expander(f"⚠️ {len(deact_result['errors'])} erreur(s) de désactivation"):
                                for err in deact_result["errors"]:
                                    st.write(f"• {err}")
                    except Exception as e:
                        st.warning(f"⚠️ Erreur lors de la désactivation des anciens liens : {e}")
                
                st.caption(
                    f"PDFs détectés : {result.get('found_pdfs', 0)} | "
                    f"Familles prêtes : {result.get('matched_families', result.get('total', 0))}"
                )
                if result.get("missing_email_families"):
                    with st.expander("⚠️ Familles ignorées car email manquant"):
                        for item in result["missing_email_families"]:
                            st.write(f"• **{item['parent_name']}**")
                if result.get("missing_pdf_families"):
                    with st.expander("⚠️ Familles ignorées car PDF non retrouvé"):
                        for item in result["missing_pdf_families"]:
                            st.write(f"• **{item['parent_name']}** — {item.get('parent_email','')}")
                if result.get("errors"):
                    with st.expander(f"⚠️ {len(result['errors'])} erreur(s) d'envoi"):
                        for err in result["errors"]:
                            st.write(f"• {err}")
            else:
                st.error(f"❌ Erreur : {result['error']}")
                st.caption(
                    f"PDFs détectés : {result.get('found_pdfs', 0)} | "
                    f"Familles prêtes : {result.get('matched_families', 0)}"
                )
                if result.get("missing_email_families"):
                    with st.expander("⚠️ Familles avec PDF mais sans email"):
                        for item in result["missing_email_families"]:
                            st.write(f"• **{item['parent_name']}**")
                if result.get("missing_pdf_families"):
                    with st.expander("⚠️ Familles avec email mais sans PDF retrouvé"):
                        for item in result["missing_pdf_families"]:
                            st.write(f"• **{item['parent_name']}** — {item.get('parent_email','')}")

def page_reminders(ctx):
    st.markdown('<div class="section-title">🔔 Rappels de Paiement</div>', unsafe_allow_html=True)
    
    secrets = ctx["load_secrets"]()
    
    if not secrets:
        st.error("❌ Fichier secrets.yaml non trouvé !")
        return
    
    gmail_config = secrets.get("gmail", {})
    if not gmail_config.get("email") or not gmail_config.get("app_password"):
        st.error("❌ Configuration email manquante. Allez dans Paramètres > Email pour configurer.")
        if st.button("⚙️ Aller aux paramètres", key="goto_config_reminder"):
            st.session_state.current_page = "config"
            st.rerun()
        return
    
    st.info("Envoie des rappels aux familles n'ayant pas encore payé (basé sur la base Notion Paiements).")
    
    # Alerte le 11
    if should_send_automatic_reminder():
        st.warning("🔔 **C'est le 11 du mois !** C'est le bon moment pour envoyer les rappels.")
    
    # ===========================
    # ÉTAPE 0 : RAPPEL TUTORBIRD
    # ===========================
    st.markdown("### 💡 Étape 0 — Vérification préalable")
    st.caption("Pensez à relancer une **extraction TutorBird** si vous avez ajouté/modifié des emails récemment, pour que les dernières informations soient prises en compte.")
    
    # ===========================
    # ÉTAPE 1 : DOSSIER DE FACTURES
    # ===========================
    st.markdown("### 📁 Étape 1 — Dossier de factures (pour joindre les PDFs)")
    
    mode_rem_preload, selected_folder_rem_preload = _render_invoice_folder_selector(
        "invoice_folder_mode_reminder_pre", "invoice_folder_select_reminder_pre", default_to_latest=False
    )
    
    st.markdown("---")
    
    # ===========================
    # ÉTAPE 2 : CHARGER LES IMPAYÉS DEPUIS NOTION
    # ===========================
    st.markdown("### 📋 Étape 2 — Familles non payées (Notion)")
    
    if st.button("🔍 Charger les familles non payées depuis Notion", width="stretch", key="load_unpaid_notion"):
        with st.spinner("Chargement depuis Notion..."):
            # Charger le dossier seulement au clic (évite la lenteur)
            folder_path_for_matching = None
            if mode_rem_preload == "Utiliser un dossier existant" and selected_folder_rem_preload:
                folder_path_for_matching = _ensure_local_invoice_folder(selected_folder_rem_preload)
            
            unpaid_data_for_matching = _try_load_data(ctx)
            if not unpaid_data_for_matching:
                try:
                    unpaid_data_for_matching = storage_load_json("full_output_tb_SIMPLE.json", folder="data")
                except Exception:
                    pass
            
            result = get_unpaid_families_from_notion(
                secrets,
                data=unpaid_data_for_matching,
                invoice_folder=folder_path_for_matching,
            )
            if result["success"]:
                st.session_state.unpaid_families = result["unpaid"]
                # Mémoriser le dossier sélectionné pour l'envoi
                st.session_state.reminder_folder_mode = mode_rem_preload
                st.session_state.reminder_folder_selected = selected_folder_rem_preload
                st.success(f"✅ {len(result['unpaid'])} famille(s) avec paiement en attente")
            else:
                st.error(f"❌ Erreur : {result['error']}")
    
    unpaid = st.session_state.get("unpaid_families", [])
    
    if not unpaid:
        st.info("Cliquez sur le bouton ci-dessus pour charger les impayés.")
        return
    
    # ===========================
    # VÉRIFICATION DES EMAILS
    # ===========================
    with_email = [f for f in unpaid if f.get("parent_email")]
    without_email = [f for f in unpaid if not f.get("parent_email")]
    
    st.info(f"📊 **{len(unpaid)}** famille(s) non payée(s) — **{len(with_email)}** avec email, **{len(without_email)}** sans email")
    
    if without_email:
        with st.expander(f"⚠️ {len(without_email)} famille(s) SANS email — ne recevront pas de rappel", expanded=True):
            for f in without_email:
                st.write(f"• **{f['parent_name']}** — {f.get('amount', 0):.2f} CHF — ❌ Email manquant")
    
    if with_email:
        with st.expander(f"✅ {len(with_email)} famille(s) avec email", expanded=False):
            for f in with_email:
                st.write(f"• **{f['parent_name']}** — {f.get('amount', 0):.2f} CHF — 📧 {f['parent_email']}")
    
    st.markdown("---")
    
    st.markdown("---")
    
    # ===========================
    # ÉTAPE 3 : TEMPLATE + OPTIONS
    # ===========================
    st.markdown("### ✉️ Étape 3 — Message de rappel")
    
    # Utiliser le dossier sélectionné à l'étape 1
    selected_folder_rem = st.session_state.get("reminder_folder_selected")
    mode_rem = st.session_state.get("reminder_folder_mode", "")
    
    # Déduire mois/année depuis le dossier ou la date courante
    if selected_folder_rem:
        month_name, year = ctx["get_month_year_from_folder"]({
            "name": selected_folder_rem["month"],
            "date": _parse_invoice_folder_dt(selected_folder_rem["month"])
        })
    else:
        month_name = ctx["MONTHS_FR"][datetime.now().month - 1]
        year = datetime.now().year
    
    template_fr = get_default_reminder_template(month_name, year)
    
    # Template anglais
    MONTHS_EN = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
    month_idx = ctx["MONTHS_FR"].index(month_name) if month_name in ctx["MONTHS_FR"] else datetime.now().month - 1
    month_en = MONTHS_EN[month_idx]
    
    template_en = {
        "subject": f"Reminder - Outstanding invoice(s) - Tutoring - {month_en} {year}",
        "body": f"""Hello,

I hope you are well.

This is a friendly reminder regarding the outstanding tutoring invoice(s) for {month_en} {year}.

Please find attached the corresponding invoice(s). You can pay directly by clicking the "Pay online" button in the PDF.

Please proceed with payment at your earliest convenience.

Do not hesitate to contact me if you have any questions or if you have already made the payment.

Best regards,
Professor+
"""
    }
    
    # Récupérer les détails heures Notion pour Carole
    carole_details_rem = ""
    data_rem = _try_load_data(ctx)
    if data_rem:
        for fam in data_rem.values():
            if fam.get("source") == "notion_hors_tb":
                for L in fam.get("lessons", []):
                    dh = L.get("notion_details_heures", "")
                    if dh:
                        carole_details_rem = dh
                        break
                if carole_details_rem:
                    break
    
    carole_reminder_template = {
        "subject": f"Rappel - Facture en attente - Soutien scolaire - {month_name} {year}",
        "body": f"""Bonjour,

J'espère que vous allez bien.

Je me permets de vous relancer concernant la facture de soutien scolaire du mois de {month_name} {year} qui reste en attente de règlement.

Détails : {carole_details_rem}

Vous trouverez ci-joint la facture correspondante. Vous pouvez régler directement en cliquant sur le bouton "Payer en ligne" dans le PDF.

Merci de procéder au paiement dès que possible.

N'hésitez pas à me contacter si vous avez des questions ou si vous avez déjà effectué le paiement.

Cordialement,
Professor+
"""
    }
    
    # Charger les données TutorBird pour classer les familles par template
    data_rem_classify = _try_load_data(ctx)
    
    # Pré-calcul : répartition des familles non payées par template
    _rem_by_template = {"fr": [], "en": [], "carole": []}
    for _fam_rem in with_email:
        _fname_rem = _fam_rem["parent_name"]
        _is_carole_r = ("carole" in _fname_rem.lower() and "tessier" in _fname_rem.lower())
        _is_en_r = False
        if data_rem_classify:
            for _fid_r, _fd in data_rem_classify.items():
                _fp = _fd.get("parent_name", "")
                if _fp and _fp.lower().strip() == _fname_rem.lower().strip():
                    _lr = str(_fd.get("language", "fr")).strip().lower()
                    if _lr in {"anglais", "english", "en"}:
                        _is_en_r = True
                    break
        if _is_carole_r:
            _rem_by_template["carole"].append(_fname_rem)
        elif _is_en_r:
            _rem_by_template["en"].append(_fname_rem)
        else:
            _rem_by_template["fr"].append(_fname_rem)
    
    tab_fr, tab_en, tab_carole = st.tabs([
        f"🇫🇷 Template français ({len(_rem_by_template['fr'])})",
        f"🇬🇧 Template anglais ({len(_rem_by_template['en'])})",
        f"👩 Carole Tessier ({len(_rem_by_template['carole'])})",
    ])
    with tab_fr:
        if _rem_by_template["fr"]:
            st.caption(f"👥 **{len(_rem_by_template['fr'])}** famille(s) : " + ", ".join(_rem_by_template["fr"]))
        else:
            st.caption("👥 Aucune famille pour ce template")
        subject = st.text_input("📝 Sujet", value=template_fr["subject"], key="reminder_subject_fr")
        body = st.text_area("✉️ Message", value=template_fr["body"], height=250, key="reminder_body_fr")
    with tab_en:
        if _rem_by_template["en"]:
            st.caption(f"👥 **{len(_rem_by_template['en'])}** famille(s) : " + ", ".join(_rem_by_template["en"]))
        else:
            st.caption("👥 Aucune famille pour ce template")
        subject_en = st.text_input("📝 Subject", value=template_en["subject"], key="reminder_subject_en")
        body_en = st.text_area("✉️ Message", value=template_en["body"], height=250, key="reminder_body_en")
    with tab_carole:
        if _rem_by_template["carole"]:
            st.caption(f"👥 **{len(_rem_by_template['carole'])}** famille(s) : " + ", ".join(_rem_by_template["carole"]))
        else:
            st.caption("👥 Aucune famille pour ce template")
        if carole_details_rem:
            st.caption(f"📋 Détails heures Notion : **{carole_details_rem}**")
        subject_carole = st.text_input("📝 Sujet", value=carole_reminder_template["subject"], key="reminder_subject_carole")
        body_carole = st.text_area("✉️ Message", value=carole_reminder_template["body"], height=250, key="reminder_body_carole")
    
    st.markdown("---")
    
    # Sélection des familles
    st.markdown("### 📬 Étape 4 — Envoi")
    
    col1, col2 = st.columns(2)
    with col1:
        send_mode = st.radio("Envoyer à :", ["Toutes les familles non payées", "Sélection personnalisée"], key="reminder_send_mode")
    with col2:
        send_test = st.checkbox("📧 Envoyer d'abord à moi-même (test)", value=True, key="reminder_test")
    
    selected_names = None
    if send_mode == "Sélection personnalisée":
        family_options = [f["parent_name"] for f in with_email]
        selected_names = st.multiselect("Sélectionner les familles", family_options, key="reminder_select_families")
    
    # Exclusion de familles
    available_for_exclusion = selected_names if selected_names else [f["parent_name"] for f in with_email]
    excluded_names = st.multiselect(
        "Ne pas envoyer à ces familles",
        available_for_exclusion,
        key="reminder_excluded_families"
    )
    final_names = [name for name in available_for_exclusion if name not in excluded_names]
    if excluded_names:
        selected_names = final_names
    
    # Charger les données TutorBird pour le matching des factures PDF
    data = data_rem_classify or _try_load_data(ctx)
    if not data:
        st.caption("💡 Les données TutorBird ne sont pas chargées. Les factures PDF ne seront pas jointes automatiquement.")
    
    # Résoudre le dossier de factures pour l'envoi (depuis l'étape 1)
    folder_path = None
    if mode_rem == "Utiliser un dossier existant" and selected_folder_rem:
        folder_path = _ensure_local_invoice_folder(selected_folder_rem)
    
    # ===========================
    # ENVOI TEST
    # ===========================
    if send_test:
        if st.button("📧 Envoyer le test à moi-même", width="stretch", key="send_reminder_test"):
            if not folder_path:
                st.warning("⚠️ Aucun dossier de factures sélectionné — le rappel sera envoyé sans pièce jointe.")
            
            progress = st.progress(0)
            status = st.empty()
            
            def callback(p, m):
                progress.progress(p)
                status.info(m)
            
            result = run_send_reminders(
                secrets, data or {}, folder_path or "", ctx["DATA_DIR"],
                custom_subject=subject, custom_body=body,
                custom_subject_en=subject_en, custom_body_en=body_en,
                selected_families=selected_names,
                send_to_test=True, callback=callback,
                custom_subject_carole=subject_carole, custom_body_carole=body_carole
            )
            
            if result["success"]:
                st.success(f"✅ Test envoyé à {gmail_config['email']} ({result.get('sent', 0)} rappel(s))")
            else:
                st.error(f"❌ Erreur : {result.get('error', 'Erreur inconnue')}")
    
    # ===========================
    # ENVOI RÉEL
    # ===========================
    if st.button("📧 Envoyer les rappels", type="primary", width="stretch", key="send_reminders_real"):
        if not folder_path:
            st.warning("⚠️ Aucun dossier de factures sélectionné — les rappels seront envoyés sans pièce jointe.")
        
        if not with_email:
            st.error("❌ Aucune famille avec email à relancer.")
            return
        
        progress = st.progress(0)
        status = st.empty()
        
        def callback(p, m):
            progress.progress(p)
            status.info(m)
        
        result = run_send_reminders(
            secrets, data or {}, folder_path or "", ctx["DATA_DIR"],
            custom_subject=subject, custom_body=body,
            custom_subject_en=subject_en, custom_body_en=body_en,
            selected_families=selected_names,
            send_to_test=False, callback=callback,
            custom_subject_carole=subject_carole, custom_body_carole=body_carole
        )
        
        if result["success"]:
            sent = result.get("sent", 0)
            total = result.get("total", 0)
            errors = result.get("errors", [])
            
            if errors:
                st.warning(f"⚠️ **{sent}/{total}** rappels envoyés — **{len(errors)}** erreur(s)")
            else:
                st.success(f"✅ **{sent}/{total}** rappels envoyés avec succès !")
            
            # Mettre à jour System-Metadata (envoi réel uniquement)
            if sent > 0:
                # Incrémenter le compteur de rappels
                current_count = 0
                try:
                    import requests as _req
                    metadata_db = secrets["notion"].get("metadata_database_id")
                    if metadata_db:
                        _r = _req.post(
                            f"https://api.notion.com/v1/databases/{metadata_db}/query",
                            headers={"Authorization": f"Bearer {secrets['notion']['token']}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"},
                            json={}, timeout=10
                        )
                        if _r.status_code == 200:
                            for row in _r.json().get("results", []):
                                cle = row.get("properties", {}).get("Clé", {}).get("title", [])
                                if cle and cle[0].get("plain_text", "").strip() == "last_reminder_sent_date":
                                    current_count = int(row.get("properties", {}).get("Valeur", {}).get("number", 0) or 0)
                                    break
                except Exception:
                    pass
                _update_metadata(secrets, "last_reminder_sent_date", value=current_count + 1, date_value=datetime.today().strftime("%Y-%m-%d"))
            
            # Rapport détaillé
            if sent > 0:
                families_sent = selected_names if selected_names else [f["parent_name"] for f in with_email]
                with st.expander(f"✅ {sent} email(s) envoyé(s)"):
                    for name in families_sent[:sent]:
                        st.write(f"• ✅ **{name}**")
            
            if errors:
                with st.expander(f"❌ {len(errors)} erreur(s) d'envoi"):
                    for err in errors:
                        st.write(f"• {err}")
            
            if without_email:
                with st.expander(f"⚠️ {len(without_email)} famille(s) sans email — non contactée(s)"):
                    for f in without_email:
                        st.write(f"• **{f['parent_name']}** — email manquant")
        else:
            st.error(f"❌ Erreur : {result.get('error', 'Erreur inconnue')}")

def page_sync(ctx):
    st.markdown('<div class="section-title">🔄 Sync Stripe → Notion</div>', unsafe_allow_html=True)
    
    secrets = ctx["load_secrets"]()
    latest = ctx["get_latest_invoice_folder"]()
    
    # Toggle no-split (persistant, ne dépend plus de session_state volatile)
    no_split_sync = st.toggle(
        "🏦 Mode no-split (tout sur mon compte, pas de split par prof)",
        value=True,
        key="sync_no_split_toggle",
        help="Activez si vous utilisez le compte Stripe no-split (sans transfert aux profs)"
    )
    
    if no_split_sync:
        st.info("""
        **Mode no-split** — Matching par **Famille + Montant** (id paiement le plus haut).
        Pas besoin de BeautifulSoup. Pas de pages profs.
        """)
    else:
        st.info("""
        **Mode normal** — Matching par **Prof + Élève + Montant** (via reçu Stripe).
        Met à jour les pages des professeurs.
        """)
    
    use_latest = st.checkbox("📅 Depuis le dernier dossier de factures", value=True)
    
    if use_latest and latest:
        since_date = latest["date"]
        st.info(f"📅 Depuis : {since_date.strftime('%d/%m/%Y')}")
    else:
        since_date = st.date_input("📅 Depuis la date")
        since_date = datetime.combine(since_date, time(0, 0))
    
    if st.button("🔄 Synchroniser", type="primary", width="stretch"):
        progress = st.progress(0)
        status = st.empty()
        
        if no_split_sync:
            # MODE NO-SPLIT
            def callback_ns(p, m):
                progress.progress(p)
                status.info(m)
            
            secrets_no_prof = ctx.get("load_secrets_no_prof", lambda: None)()
            if not secrets_no_prof:
                st.error("❌ Config no-split non trouvée ! Vérifiez la section stripe_no_split dans secrets.yaml.")
                return
            
            result1 = run_sync_stripe_notion_no_split(secrets_no_prof, secrets, since_date, callback_ns)
            
            progress.progress(100)
            status.empty()
            
            if result1["success"]:
                st.success(f"""
                ✅ **Synchronisation no-split terminée**
                
                - {result1['synced']} paiement(s) synchronisé(s)
                - {result1['already_paid']} déjà marqué(s) payé(s)
                - {result1['total_not_found']} non trouvé(s) dans Notion
                """)
                
                if result1.get("duplicates_warning"):
                    with st.expander(f"⚠️ {len(result1['duplicates_warning'])} doublon(s) détecté(s) dans Notion", expanded=True):
                        st.warning("Des lignes en double ont été trouvées. Vérifiez et supprimez les doublons manuellement.")
                        for dw in result1["duplicates_warning"]:
                            st.write(f"• {dw}")
                
                if result1.get("not_found"):
                    with st.expander("⚠️ Paiements non trouvés dans Notion"):
                        for nf in result1["not_found"]:
                            st.write(f"• {nf}")
            else:
                st.error(f"❌ Erreur : {result1['error']}")
        
        else:
            # MODE NORMAL avec split
            def callback1(p, m):
                progress.progress(int(p * 0.5))
                status.info(f"[1/2] {m}")
            
            from scripts.sync_stripe_notion import run_sync_stripe_notion
            result1 = run_sync_stripe_notion(secrets, since_date, callback1)
            
            if not result1["success"]:
                st.error(f"❌ Erreur sync Stripe : {result1['error']}")
                return
            
            def callback2(p, m):
                progress.progress(50 + int(p * 0.5))
                status.info(f"[2/2] {m}")
            
            from scripts.update_notion_prof_pages import run_update_notion_prof_pages
            result2 = run_update_notion_prof_pages(secrets, callback2, force=False, latest_only=False)
            
            progress.progress(100)
            status.empty()
            
            if result1["success"] and result2["success"]:
                st.success(f"""
                ✅ **Synchronisation terminée**
                
                **Stripe → Notion :**
                - {result1['synced']} paiement(s) synchronisé(s)
                - {result1['already_paid']} déjà marqué(s) payé(s)
                - {result1.get('student_unknown', 0)} élève(s) inconnu(s)
                - {result1['total_not_found']} non trouvé(s) dans Notion
                
                **Pages professeurs :**
                - {result2['updated']} page(s) mise(s) à jour
                - {result2['skipped']} page(s) déjà à jour
                - {result2['recaps_updated']} récap(s) mis à jour
                """)
                
                if result1.get("not_found"):
                    with st.expander("⚠️ Paiements non trouvés dans Notion"):
                        for nf in result1["not_found"]:
                            st.write(f"• {nf}")
            
            elif result2 and not result2["success"]:
                st.warning(f"""
                ⚠️ **Sync Stripe OK, mais erreur pages profs**
                - {result1['synced']} paiement(s) synchronisé(s)
                - Erreur pages profs : {result2['error']}
                """)


def page_update(ctx):
    st.markdown('<div class="section-title">📤 Ajouter lignes Notion</div>', unsafe_allow_html=True)
    
    secrets = ctx["load_secrets"]()
    if not secrets:
        st.error("❌ Fichier secrets.yaml non trouvé !")
        return
    
    # Chargement des données avec fallback Drive
    data = _try_load_data(ctx)
    latest = ctx["get_latest_invoice_folder"]()
    if not data:
        st.warning("⚠️ **Données des familles non disponibles.**")
        if st.button("📥 Charger depuis TutorBird / Drive", key="load_tb_update"):
            with st.spinner("Chargement..."):
                data = _try_load_data(ctx)
                if data:
                    st.success(f"✅ {len(data)} famille(s) chargées")
                    st.rerun()
                else:
                    st.error("❌ Lancez d'abord une extraction TutorBird.")
        return
    
    # Options no-split
    is_no_split = st.session_state.get("no_split_mode_active", False)
    if is_no_split:
        st.info("🏦 **Mode sans transfert actif**")
    
    skip_prof_subpages = st.checkbox(
        "🚫 Ne pas créer les sous-pages profs (Prof → Date → Élève)",
        value=True,
        key="skip_prof_subpages_update"
    )
    effective_no_split = is_no_split or skip_prof_subpages
    
    tab1, tab2, tab3 = st.tabs(["➕ Ajouter toutes les lignes", "🔄 Mettre à jour certaines lignes", "🔍 Ajouter ligne(s) manquante(s)"])
    
    with tab1:
        st.markdown("### 📁 Dossier de travail")
        mode_t1, selected_folder_t1 = _render_invoice_folder_selector("update_folder_mode_t1", "update_folder_select_t1", default_to_latest=False)
        
        folder_name_t1 = "N/A"
        if mode_t1 == "Utiliser un dossier existant" and selected_folder_t1:
            folder_name_t1 = selected_folder_t1.get("month", "N/A")
        elif mode_t1 != "Utiliser un dossier existant":
            st.warning("⚠️ Sélectionnez un dossier existant.")
        
        st.markdown("---")
        st.info(f"""
        **Cette action va :**
        1. Ajouter **{len(data)}** lignes dans la base de données Paiements
        2. Avec Professeur, Élève, Devise, Année, Date cours (range), Invoice date
        
        📁 Dossier : **{folder_name_t1}**
        """)
        
        if st.button("📤 Ajouter les lignes", type="primary", width="stretch", key="add_all_notion"):
            familles_euros = ctx["load_familles_euros"]()
            
            # Extraire la date de facture depuis le nom du dossier (ex: "Mars 2026 - 24-03-2026")
            invoice_date_from_folder = None
            if selected_folder_t1:
                folder_dt = _parse_invoice_folder_dt(selected_folder_t1.get("month", ""))
                if folder_dt:
                    invoice_date_from_folder = folder_dt.strftime("%Y-%m-%d")
            
            progress = st.progress(0)
            status = st.empty()
            def callback(p, m):
                progress.progress(p)
                status.info(m)
            
            # Calculer additional_amounts depuis les données impayées n-2
            # Inclut montant, heures, et dates pour les lignes Notion complètes
            _update_additional_amounts = None
            _prev_unpaid_for_notion = st.session_state.get("_previous_unpaid_data")
            if _prev_unpaid_for_notion:
                _update_additional_amounts = {}
                for _fid, _fdata in _prev_unpaid_for_notion.items():
                    _lessons = _fdata.get("lessons", [])
                    _billable = [L for L in _lessons if L.get("attendance_status") != "AbsentNotice"]
                    _fam_total = sum(float(L.get("amount") or 0) for L in _billable)
                    _fam_hours = sum((L.get("duration_min") or 0) / 60 for L in _billable)
                    _fam_dates = []
                    for L in _billable:
                        d = L.get("date", "")
                        if d:
                            try:
                                _fam_dates.append(datetime.strptime(d, "%d.%m.%Y"))
                            except Exception:
                                pass
                    if _fam_total > 0:
                        _update_additional_amounts[_fid] = {
                            "amount": _fam_total,
                            "hours": _fam_hours,
                            "dates": _fam_dates,
                        }
            
            result = run_update_notion(secrets, data, ctx["BASE_DIR"], callback, no_split=effective_no_split, familles_euros=familles_euros, invoice_date_override=invoice_date_from_folder, additional_amounts=_update_additional_amounts)
            
            if result["success"]:
                added = result.get('added', 0)
                api_failed = result.get('api_failed', 0)
                total_fam = result.get('total_families', 0)
                
                if added > 0:
                    st.success(f"""
                    ✅ **{added} ligne(s) ajoutée(s)** sur {total_fam} familles
                    - {result.get('pages_created', 0)} sous-page(s) prof créée(s)
                    """)
                    if api_failed > 0:
                        st.warning(f"⚠️ {api_failed} famille(s) n'ont pas pu être ajoutée(s) — voir les logs.")
                else:
                    st.warning(f"""
                    ⚠️ **Aucune ligne ajoutée** — Diagnostic :
                    - 📊 {total_fam} familles
                    - 📭 {result.get('no_lessons', 0)} sans leçon
                    - ❌ {api_failed} échec(s) API
                    """)
                    if api_failed > 0:
                        st.error("Vérifiez les logs Streamlit pour les détails d'erreur.")
            else:
                st.error(f"❌ Erreur : {result['error']}")
    
    with tab2:
        st.markdown("### 🔄 Mettre à jour certaines lignes Notion")
        
        st.info("""
        **Cette option permet de :**
        - Remplacer les valeurs des lignes existantes pour certaines familles
        - Mettre à jour les sous-pages des professeurs concernés
        
        ⚠️ Utilisez cette option après avoir régénéré des factures pour certains clients.
        """)
        
        if latest:
            st.warning(f"📁 Les modifications concerneront le dossier : **{latest['name']}**")
        else:
            st.error("❌ Aucun dossier de factures trouvé.")
            return
        
        # ===========================
        # CHOIX DU MODE DE SÉLECTION
        # ===========================
        mode = st.radio(
            "🔍 Mode de sélection :",
            ["👨‍👩‍👧 Par famille", "👨‍🏫 Par professeur"],
            horizontal=True,
            key="update_selection_mode"
        )
        
        st.markdown("---")
        
        selected_family_ids = []
        selected_teachers = []
        
        # ===========================
        # MODE PAR FAMILLE
        # ===========================
        if mode == "👨‍👩‍👧 Par famille":
            # Pré-sélection si venant de la page factures
            preselected = st.session_state.get("regenerated_invoices_families", [])
            
            # Liste des familles
            family_list = [(fam_id, fam.get("parent_name", fam_id)) for fam_id, fam in data.items()]
            family_names = [f"{name} ({fam_id})" for fam_id, name in family_list]
            
            # Pré-sélectionner
            default_selection = []
            for fam_id in preselected:
                for fid, name in family_list:
                    if fid == fam_id:
                        default_selection.append(f"{name} ({fid})")
            
            selected_families_display = st.multiselect(
                "📋 Sélectionnez les familles à mettre à jour",
                family_names,
                default=default_selection,
                key="select_families_notion_update_mode1"
            )
            
            # Extraire les IDs
            for sel in selected_families_display:
                for fam_id, name in family_list:
                    if f"{name} ({fam_id})" == sel:
                        selected_family_ids.append(fam_id)
            
            if selected_family_ids:
                # Récupérer TOUS les profs de ces familles automatiquement
                for fam_id in selected_family_ids:
                    fam = data.get(fam_id, {})
                    lessons = fam.get("lessons", [])
                    for L in lessons:
                        teacher = L.get("teacher", "")
                        if teacher and teacher not in selected_teachers:
                            selected_teachers.append(teacher)
                
                st.info(f"📊 **{len(selected_family_ids)}** famille(s) sélectionnée(s) → **{len(selected_teachers)}** professeur(s) concerné(s)")
        
        # ===========================
        # MODE PAR PROFESSEUR
        # ===========================
        else:
            # Récupérer tous les profs avec le nombre de familles
            all_teachers = {}
            for fam_id, fam in data.items():
                lessons = fam.get("lessons", [])
                for L in lessons:
                    teacher = L.get("teacher", "")
                    if teacher:
                        if teacher not in all_teachers:
                            all_teachers[teacher] = {"families": set(), "count": 0}
                        all_teachers[teacher]["families"].add(fam_id)
                        all_teachers[teacher]["count"] = len(all_teachers[teacher]["families"])
            
            # Liste des profs avec leur nombre de familles
            teacher_options = [f"{name} ({info['count']} famille(s))" for name, info in sorted(all_teachers.items())]
            
            selected_teachers_display = st.multiselect(
                "👨‍🏫 Sélectionnez les professeurs",
                teacher_options,
                key="select_teachers_notion_update_mode2"
            )
            
            # Extraire les noms et les familles concernées
            for sel in selected_teachers_display:
                teacher_name = sel.split(" (")[0]
                selected_teachers.append(teacher_name)
                
                # Ajouter toutes les familles de ce prof
                if teacher_name in all_teachers:
                    for fam_id in all_teachers[teacher_name]["families"]:
                        if fam_id not in selected_family_ids:
                            selected_family_ids.append(fam_id)
            
            if selected_teachers:
                st.info(f"👨‍🏫 **{len(selected_teachers)}** professeur(s) sélectionné(s) → **{len(selected_family_ids)}** famille(s) concernée(s)")
        
        # ===========================
        # BOUTON D'ACTION
        # ===========================
        if selected_family_ids and selected_teachers:
            st.markdown("---")
            
            st.warning(f"""
            ⚠️ **Cette action va :**
            1. Scanner les factures PDF du dossier **{latest['name']}**
            2. Mettre à jour **{len(selected_family_ids)}** ligne(s) Notion
            3. Professeurs concernés : {', '.join(selected_teachers)}
            """)
            
            if st.button("🔄 Mettre à jour les lignes sélectionnées", type="primary", width="stretch", key="update_selective_notion"):
                progress = st.progress(0)
                status = st.empty()
                
                def callback(p, m):
                    progress.progress(p)
                    status.info(m)
                
                # Appel de la fonction de mise à jour sélective
                result = run_update_notion_selective(
                    secrets, 
                    data, 
                    latest["path"],
                    selected_family_ids,
                    selected_teachers,
                    callback,
                    no_split=is_no_split
                )
                
                if result["success"]:
                    st.success(f"""
                    ✅ **Mise à jour terminée !**
                    - 📄 {result.get('invoices_found', 0)} facture(s) trouvée(s)
                    - ✏️ {result.get('rows_updated', 0)} ligne(s) Notion mise(s) à jour
                    - 📁 {result.get('subpages_updated', 0)} sous-page(s) prof mise(s) à jour
                    """)
                    
                    if result.get("details"):
                        with st.expander("📋 Détails des mises à jour"):
                            for detail in result["details"]:
                                st.write(f"• **{detail['family']}** / {detail['teacher']} : {detail['amount']} {detail['currency']}")
                    
                    if result.get("not_found"):
                        with st.expander("⚠️ Factures non trouvées"):
                            for nf in result["not_found"]:
                                st.write(f"• {nf}")
                    
                    # Clear les flags
                    st.session_state.regenerated_invoices_families = []
                    st.session_state.update_tab = None
                else:
                    st.error(f"❌ Erreur : {result['error']}")
        else:
            st.warning("⚠️ Sélectionnez au moins une famille ou un professeur.")
        
        # Clear le flag après affichage
        st.session_state.update_tab = None
    
    # ===========================
    # TAB 3: Ajouter ligne(s) manquante(s) (NOUVEAU)
    # ===========================
    with tab3:
        st.markdown("### 🔍 Ajouter ligne(s) manquante(s)")

        if not latest or latest is None:
            st.error("❌ Aucun dossier de factures trouvé. Veuillez d'abord générer des factures.")
        
        else:
            st.info("""
            **Cette option permet de :**
            1. Scanner toutes les factures du dossier actuel
            2. Comparer avec les lignes Notion existantes
            3. Identifier les lignes manquantes
            4. Ajouter automatiquement les lignes manquantes
            
            💡 Utile pour s'assurer que toutes les factures ont bien une ligne dans Notion.
            """)
            
            st.warning(f"📁 Dossier analysé : **{latest['name']}**")
            
            # ===========================
            # ÉTAPE 1: SCAN ET COMPARAISON
            # ===========================
            if st.button("🔍 Scanner et comparer", type="primary", width="stretch", key="scan_compare_notion"):
                progress = st.progress(0)
                status = st.empty()
                
                def callback(p, m):
                    progress.progress(p)
                    status.info(m)
                
                from scripts.update_notion import run_scan_and_compare
                result = run_scan_and_compare(secrets, data, latest["path"], callback)
                
                if result["success"]:
                    # Stocker le résultat dans session_state pour l'utiliser après
                    st.session_state.scan_compare_result = result
                    
                    missing = result.get("missing", [])
                    already_exists = result.get("already_exists", [])
                    
                    st.success(f"""
                    ✅ **Scan terminé !**
                    - 📄 **{result['invoices_scanned']}** facture(s) scannée(s)
                    - 📋 **{result['notion_rows']}** lignes Notion existantes
                    - ✅ **{len(already_exists)}** déjà dans Notion
                    - ⚠️ **{len(missing)}** manquante(s)
                    """)
                    
                    if missing:
                        st.warning(f"⚠️ **{len(missing)} ligne(s) manquante(s) dans Notion :**")
                        
                        # Afficher les détails dans un tableau
                        missing_data = []
                        for m in missing:
                            missing_data.append({
                                "Famille": m["family_name"],
                                "Professeur": m["teacher"],
                                "Montant": f"{m['amount']:.2f} {m.get('currency', 'CHF')}",
                                "Élèves": m.get("students_formatted", ""),
                            })
                        
                        st.dataframe(missing_data, width="stretch", hide_index=True)
                    else:
                        st.success("🎉 **Toutes les factures ont une ligne dans Notion !**")
                else:
                    st.error(f"❌ Erreur : {result['error']}")
            
            # ===========================
            # ÉTAPE 2: AJOUTER LES MANQUANTES
            # ===========================
            if "scan_compare_result" in st.session_state:
                result = st.session_state.scan_compare_result
                missing = result.get("missing", [])
                
                if missing:
                    st.markdown("---")
                    st.markdown("### ➕ Ajouter les lignes manquantes")
                    
                    if st.button(f"➕ Ajouter les {len(missing)} ligne(s) manquante(s)", type="primary", width="stretch", key="add_missing_notion"):
                        progress = st.progress(0)
                        status = st.empty()
                        
                        def callback(p, m):
                            progress.progress(p)
                            status.info(m)
                        
                        from scripts.update_notion import run_add_missing_rows
                        add_result = run_add_missing_rows(secrets, data, missing, callback)
                        
                        if add_result["success"]:
                            st.success(f"""
                            ✅ **Ligne(s) ajoutée(s) !**
                            - ➕ **{add_result['added']}** ligne(s) ajoutée(s) dans Notion
                            """)
                            
                            # Afficher les erreurs s'il y en a
                            if add_result.get("errors"):
                                with st.expander("⚠️ Erreurs rencontrées"):
                                    for err in add_result["errors"]:
                                        st.error(err)
                            
                            # Clear le résultat
                            del st.session_state.scan_compare_result
                            
                            # Proposer d'aller vers Sync Stripe
                            if add_result['added'] > 0:
                                st.markdown("---")
                                st.info("💡 **Prochaine étape :** Allez sur **Sync Stripe → Notion** pour synchroniser les paiements et mettre à jour les pages des professeurs.")
                                
                                if st.button("🔄 Aller vers Sync Stripe → Notion", width="stretch", key="go_to_sync"):
                                    st.session_state.current_page = "sync"
                                    st.rerun()
                        else:
                            st.error(f"❌ Erreur : {add_result['error']}")

def page_config(ctx):
    st.markdown('<div class="section-title">⚙️ Configuration</div>', unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["👨‍🏫 Professeurs", "💶 Familles EUR", "🏷️ Tarifs spéciaux", "📧 Email", "🔧 Drive"])
    
    # ===========================
    # TAB 5: Diagnostic Drive
    # ===========================
    with tab5:
        st.markdown("### 🔧 Diagnostic Google Drive")
        st.caption("Vérifie que la sauvegarde et la restauration des configs fonctionnent.")
        
        # Afficher le log de sync au boot
        _sync_log = st.session_state.get("drive_sync_log", [])
        if _sync_log:
            st.markdown("**Sync au démarrage :**")
            for _msg in _sync_log:
                st.write(_msg)
        else:
            st.info("Aucun log de sync disponible (premier chargement ou mode local)")
        
        st.markdown("---")
        
        # Test de connexion Drive
        if st.button("🔍 Tester la connexion Drive", key="test_drive_conn"):
            try:
                from scripts.config_loader import _get_drive_service, _get_root_folder_id, _download_yaml_from_drive, is_streamlit_cloud
                
                st.write(f"☁️ `is_streamlit_cloud()` = **{is_streamlit_cloud()}**")
                
                svc = _get_drive_service()
                if svc:
                    st.success("✅ Connexion Drive OK")
                    root_id = _get_root_folder_id()
                    st.write(f"📁 ROOT_FOLDER_ID = `{root_id}`")
                    
                    # Lister le contenu du dossier config/
                    query = f"name='config' and mimeType='application/vnd.google-apps.folder' and '{root_id}' in parents and trashed=false"
                    results = svc.files().list(q=query, fields="files(id, name)").execute()
                    config_folders = results.get('files', [])
                    
                    if config_folders:
                        cfg_id = config_folders[0]['id']
                        st.success(f"✅ Dossier config/ trouvé (ID: `{cfg_id}`)")
                        
                        # Lister les fichiers dans config/
                        query = f"'{cfg_id}' in parents and trashed=false"
                        results = svc.files().list(q=query, fields="files(id, name, modifiedTime, size)").execute()
                        files = results.get('files', [])
                        
                        if files:
                            st.write(f"📄 **{len(files)} fichier(s) dans config/ :**")
                            for f in files:
                                st.write(f"  • `{f['name']}` — modifié: {f.get('modifiedTime', '?')} — taille: {f.get('size', '?')}")
                        else:
                            st.warning("⚠️ Dossier config/ est vide")
                    else:
                        st.error("❌ Dossier config/ non trouvé dans Professor_Plus_Data")
                    
                    # Test lecture secrets.yaml
                    st.markdown("---")
                    st.write("**Test lecture secrets.yaml :**")
                    content = _download_yaml_from_drive(svc, root_id, "secrets.yaml")
                    if content:
                        st.success(f"✅ secrets.yaml lu ({len(content)} caractères)")
                    else:
                        st.error("❌ secrets.yaml non lisible")
                    
                    # Test lecture tarifs_speciaux.yaml
                    st.write("**Test lecture tarifs_speciaux.yaml :**")
                    content = _download_yaml_from_drive(svc, root_id, "tarifs_speciaux.yaml")
                    if content:
                        st.success(f"✅ tarifs_speciaux.yaml lu ({len(content)} caractères)")
                        st.code(content[:500], language="yaml")
                    else:
                        st.error("❌ tarifs_speciaux.yaml non lisible")
                    
                else:
                    st.error("❌ Impossible de se connecter à Google Drive")
                    st.write("Vérifiez que `google_service_account` est configuré dans les secrets Streamlit.")
            except Exception as e:
                st.error(f"❌ Erreur : {e}")
                import traceback
                st.code(traceback.format_exc())
        
        st.markdown("---")
        
        # Test d'écriture
        if st.button("📝 Tester l'écriture sur Drive", key="test_drive_write"):
            try:
                from scripts.config_loader import save_yaml_to_drive
                test_data = {"test": True, "timestamp": datetime.now().isoformat()}
                result = save_yaml_to_drive("_test_write.yaml", test_data)
                if result:
                    st.success("✅ Écriture Drive OK — fichier `_test_write.yaml` créé dans config/")
                else:
                    st.error("❌ Échec écriture Drive")
            except Exception as e:
                st.error(f"❌ Erreur écriture : {e}")
                import traceback
                st.code(traceback.format_exc())
    
    # ===========================
    # TAB 1: Professeurs
    # ===========================
    with tab1:
        secrets = ctx["load_secrets"]()
        if not secrets:
            st.error("❌ secrets.yaml non trouvé")
            return

        if "teachers" not in secrets:
            secrets["teachers"] = {}

        teachers = secrets.get("teachers", {})

        cols = st.columns([3, 1])
        with cols[0]:
            st.markdown("### 👨‍🏫 Gestion des professeurs")
        with cols[1]:
            if st.session_state.get("return_to_page"):
                if st.button("↩ Retour", width="stretch"):
                    st.session_state.current_page = st.session_state.return_to_page
                    st.session_state.return_to_page = ""
                    st.rerun()

        t_add, t_edit = st.tabs(["➕ Ajouter", "✏️ Modifier"])

        with t_add:

            # Message important sur Render
            st.warning("""
            ⚠️ **Important** : Après avoir ajouté un nouveau professeur ici, pensez à **l'ajouter également dans Render** 
            (variables d'environnement du webhook) pour que l'automatisation Stripe → Notion fonctionne correctement !
            """)
            prefill = st.session_state.get("prefill_new_teacher_name", "")

            new_name = st.text_input(
                "Nom du professeur (doit matcher TutorBird)",
                value=prefill,
                key="ui_new_teacher_name",
            )

            col1, col2 = st.columns(2)
            with col1:
                new_chf = st.number_input("💰 Tarif CHF/h", value=0.0, step=0.1, key="ui_new_teacher_chf")
            with col2:
                new_eur = st.number_input("💶 Tarif EUR/h", value=0.0, step=0.1, key="ui_new_teacher_eur")

            new_connect = st.text_input("🔗 Stripe Connect ID (optionnel)", value="", key="ui_new_teacher_connect")

            if st.button("✅ Créer le professeur", type="primary", width="stretch"):
                name = (new_name or "").strip()
                if not name:
                    st.error("❌ Nom vide")
                elif name in teachers:
                    st.warning("⚠️ Ce professeur existe déjà.")
                else:
                    teachers[name] = {
                        "connect_account_id": (new_connect or "").strip(),
                        "pay_rate": {
                            "chf": float(new_chf),
                            "eur": float(new_eur)
                        }
                    }
                    secrets["teachers"] = teachers
                    ctx["save_secrets"](secrets)

                    st.success("✅ Professeur ajouté !")
                    st.session_state.prefill_new_teacher_name = ""

                    report_path = os.path.join(ctx["DATA_DIR"], "payment_links_report.json")
                    if os.path.exists(report_path):
                        os.remove(report_path)

                    return_to = st.session_state.get("return_to_page", "")
                    if return_to:
                        st.session_state.current_page = return_to
                        st.session_state.return_to_page = ""

                    st.rerun()

        with t_edit:
            if not teachers:
                st.info("Aucun professeur configuré.")
            else:
                # Récupérer le taux FX pour l'auto CHF
                from scripts.recap_profs import fetch_chf_eur_rate
                fx_rate, fx_source = fetch_chf_eur_rate()
                
                st.info(f"💱 Taux CHF→EUR actuel : **{fx_rate}** ({fx_source})")
                
                # Créer les données pour le tableau
                teacher_names = list(teachers.keys())
                
                # Préparer les données pour st.data_editor
                table_data = []
                for name in teacher_names:
                    t_data = teachers[name]
                    auto_chf = t_data.get("auto_chf", False)
                    table_data.append({
                        "Professeur": name,
                        "CHF/h": float(t_data.get("pay_rate", {}).get("chf", 0)),
                        "EUR/h": float(t_data.get("pay_rate", {}).get("eur", 0)),
                        "Auto CHF": auto_chf,
                        "Stripe Connect ID": t_data.get("connect_account_id") or "",
                        "Supprimer": False
                    })
                
                # Afficher le tableau éditable
                edited_df = st.data_editor(
                    table_data,
                    column_config={
                        "Professeur": st.column_config.TextColumn(
                            "👨‍🏫 Professeur",
                            disabled=True,
                            width="medium"
                        ),
                        "CHF/h": st.column_config.NumberColumn(
                            "💰 CHF/h",
                            min_value=0,
                            max_value=500,
                            step=0.01,
                            format="%.2f",
                            width="small"
                        ),
                        "EUR/h": st.column_config.NumberColumn(
                            "💶 EUR/h",
                            min_value=0,
                            max_value=500,
                            step=0.01,
                            format="%.2f",
                            width="small"
                        ),
                        "Auto CHF": st.column_config.CheckboxColumn(
                            "🔄 Auto",
                            help="Si coché, le taux CHF est calculé automatiquement pour que la conversion CHF→EUR donne exactement le taux EUR indiqué",
                            width="small",
                            default=False
                        ),
                        "Stripe Connect ID": st.column_config.TextColumn(
                            "🔗 Stripe Connect ID",
                            width="large"
                        ),
                        "Supprimer": st.column_config.CheckboxColumn(
                            "🗑️",
                            width="small",
                            default=False
                        )
                    },
                    hide_index=True,
                    width="stretch",
                    key="teachers_table"
                )
                
                # Aperçu des taux auto-calculés
                auto_preview = []
                for row in edited_df:
                    if row.get("Auto CHF") and row["EUR/h"] > 0 and fx_rate > 0:
                        computed_chf = round(row["EUR/h"] / fx_rate, 2)
                        if abs(computed_chf - row["CHF/h"]) > 0.01:
                            auto_preview.append(f"**{row['Professeur']}** : CHF/h {row['CHF/h']:.2f} → **{computed_chf:.2f}** (pour obtenir {row['EUR/h']:.2f} €)")
                
                if auto_preview:
                    st.warning("🔄 **Auto CHF — Modifications à appliquer :**\n" + "\n".join(f"- {p}" for p in auto_preview))
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("💾 Sauvegarder les modifications", type="primary", width="stretch"):
                        for row in edited_df:
                            name = row["Professeur"]
                            if name in teachers:
                                eur_rate = float(row["EUR/h"])
                                chf_rate = float(row["CHF/h"])
                                is_auto = row.get("Auto CHF", False)
                                
                                # Si Auto CHF activé, recalculer CHF depuis EUR
                                if is_auto and eur_rate > 0 and fx_rate > 0:
                                    chf_rate = round(eur_rate / fx_rate, 2)
                                
                                teachers[name]["pay_rate"]["chf"] = chf_rate
                                teachers[name]["pay_rate"]["eur"] = eur_rate
                                teachers[name]["auto_chf"] = is_auto
                                teachers[name]["connect_account_id"] = (row["Stripe Connect ID"] or "").strip()
                        
                        secrets["teachers"] = teachers
                        ctx["save_secrets"](secrets)
                        st.success("✅ Modifications sauvegardées !")
                        st.rerun()
                
                with col2:
                    # Compter les suppressions cochées
                    to_delete = [row["Professeur"] for row in edited_df if row.get("Supprimer")]
                    
                    if to_delete:
                        if st.button(f"🗑️ Supprimer ({len(to_delete)})", width="stretch"):
                            for name in to_delete:
                                if name in teachers:
                                    del teachers[name]
                            secrets["teachers"] = teachers
                            ctx["save_secrets"](secrets)
                            st.success(f"✅ {len(to_delete)} professeur(s) supprimé(s)")
                            st.rerun()
                    else:
                        st.button("🗑️ Supprimer", width="stretch", disabled=True)
    
    # ===========================
    # TAB 2: Familles EUR (AMÉLIORÉ)
    # ===========================
    with tab2:
        st.markdown("### 💶 Familles facturées en EUR")
        
        familles_eur = ctx["load_familles_euros"]()
        data = ctx["load_extracted_data"]()
        
        # Récupérer toutes les familles depuis TutorBird
        all_families = []
        if data:
            for fam_id, fam_data in data.items():
                parent_name = fam_data.get("parent_name") or fam_data.get("family_name") or ""
                if parent_name and parent_name not in all_families:
                    all_families.append(parent_name)
        all_families.sort()
        
        st.info(f"📋 **{len(familles_eur)}** famille(s) configurée(s) en EUR")
        
        # Afficher les familles existantes dans un tableau
        if familles_eur:
            table_data = []
            for fam in familles_eur:
                table_data.append({
                    "Famille": fam,
                    "Supprimer": False
                })
            
            edited_fam_df = st.data_editor(
                table_data,
                column_config={
                    "Famille": st.column_config.TextColumn(
                        "👨‍👩‍👧 Famille",
                        disabled=True,
                        width="large"
                    ),
                    "Supprimer": st.column_config.CheckboxColumn(
                        "🗑️",
                        width="small",
                        default=False
                    )
                },
                hide_index=True,
                width="stretch",
                key="familles_eur_table"
            )
            
            # Bouton supprimer
            to_delete_fam = [row["Famille"] for row in edited_fam_df if row.get("Supprimer")]
            if to_delete_fam:
                if st.button(f"🗑️ Supprimer {len(to_delete_fam)} famille(s)", width="stretch"):
                    for fam in to_delete_fam:
                        if fam in familles_eur:
                            familles_eur.remove(fam)
                    ctx["save_familles_euros"](familles_eur)
                    st.success(f"✅ {len(to_delete_fam)} famille(s) supprimée(s)")
                    st.rerun()
        
        st.markdown("---")
        st.markdown("#### ➕ Ajouter une famille en EUR")
        
        # Filtrer les familles qui ne sont pas encore en EUR
        available_families = [f for f in all_families if f not in familles_eur]
        
        if available_families:
            col1, col2 = st.columns([3, 1])
            with col1:
                selected_family = st.selectbox(
                    "Sélectionner une famille",
                    options=[""] + available_families,
                    format_func=lambda x: "-- Choisir une famille --" if x == "" else x,
                    key="select_famille_eur"
                )
            with col2:
                st.write("")  # Spacer
                st.write("")  # Spacer
                add_disabled = selected_family == ""
                if st.button("➕ Ajouter", type="primary", width="stretch", disabled=add_disabled, key="btn_add_fam_eur"):
                    if selected_family:
                        familles_eur.append(selected_family)
                        ctx["save_familles_euros"](familles_eur)
                        st.success(f"✅ **{selected_family}** ajoutée aux familles EUR")
                        st.rerun()
        else:
            if all_families:
                st.success("✅ Toutes les familles sont déjà configurées en EUR !")
            else:
                st.warning("⚠️ Aucune famille disponible. Lancez d'abord une extraction TutorBird.")
        
        # Option pour ajouter manuellement
        with st.expander("📝 Ajouter manuellement (si non présent dans TutorBird)"):
            manual_fam = st.text_input("Nom de la famille", key="manual_famille_eur")
            if st.button("➕ Ajouter manuellement", key="btn_add_manual_eur"):
                if manual_fam and manual_fam.strip():
                    if manual_fam.strip() not in familles_eur:
                        familles_eur.append(manual_fam.strip())
                        ctx["save_familles_euros"](familles_eur)
                        st.success(f"✅ **{manual_fam.strip()}** ajoutée")
                        st.rerun()
                    else:
                        st.warning("⚠️ Cette famille est déjà dans la liste")
    
    # ===========================
    # TAB 3: Tarifs spéciaux (AMÉLIORÉ)
    # ===========================
    with tab3:
        st.markdown("### 🏷️ Tarifs spéciaux")
        st.caption("Définissez des tarifs personnalisés pour certaines combinaisons professeur/famille")
        
        tarifs = ctx["load_tarifs_speciaux"]()
        secrets = ctx["load_secrets"]()
        data = ctx["load_extracted_data"]()
        
        # Récupérer les profs et familles
        teacher_names = list(secrets.get("teachers", {}).keys()) if secrets else []
        
        all_families = []
        if data:
            for fam_id, fam_data in data.items():
                parent_name = fam_data.get("parent_name") or fam_data.get("family_name") or ""
                if parent_name and parent_name not in all_families:
                    all_families.append(parent_name)
        all_families.sort()
        
        st.info(f"📋 **{len(tarifs)}** tarif(s) spécial(aux) configuré(s)")
        
        # Afficher les tarifs existants dans un tableau
        if tarifs:
            table_data = []
            for t in tarifs:
                devise = t.get("currency", "EUR")
                if devise == "EUR" or "eur" in str(t.get("pay_rate", "")).lower():
                    devise = "EUR"
                    montant = t.get("pay_rate", 0)
                else:
                    devise = "CHF"
                    montant = t.get("pay_rate_chf", t.get("pay_rate", 0))
                
                table_data.append({
                    "Professeur": t.get("teacher", ""),
                    "Famille": t.get("parent", ""),
                    "Tarif": f"{montant}",
                    "Devise": devise,
                    "Supprimer": False
                })
            
            edited_tarifs_df = st.data_editor(
                table_data,
                column_config={
                    "Professeur": st.column_config.TextColumn(
                        "👨‍🏫 Professeur",
                        disabled=True,
                        width="medium"
                    ),
                    "Famille": st.column_config.TextColumn(
                        "👨‍👩‍👧 Famille",
                        disabled=True,
                        width="medium"
                    ),
                    "Tarif": st.column_config.TextColumn(
                        "💰 Tarif/h",
                        disabled=True,
                        width="small"
                    ),
                    "Devise": st.column_config.TextColumn(
                        "💱 Devise",
                        disabled=True,
                        width="small"
                    ),
                    "Supprimer": st.column_config.CheckboxColumn(
                        "🗑️",
                        width="small",
                        default=False
                    )
                },
                hide_index=True,
                width="stretch",
                key="tarifs_speciaux_table"
            )
            
            # Bouton supprimer
            to_delete_idx = [i for i, row in enumerate(edited_tarifs_df) if row.get("Supprimer")]
            if to_delete_idx:
                if st.button(f"🗑️ Supprimer {len(to_delete_idx)} tarif(s)", width="stretch"):
                    # Supprimer en ordre inverse pour éviter les problèmes d'index
                    for idx in sorted(to_delete_idx, reverse=True):
                        if idx < len(tarifs):
                            tarifs.pop(idx)
                    ctx["save_tarifs_speciaux"](tarifs)
                    st.success(f"✅ {len(to_delete_idx)} tarif(s) supprimé(s)")
                    st.rerun()
        
        st.markdown("---")
        st.markdown("#### ➕ Ajouter un tarif spécial")
        
        if not teacher_names:
            st.warning("⚠️ Aucun professeur configuré. Ajoutez d'abord des professeurs.")
        elif not all_families:
            st.warning("⚠️ Aucune famille disponible. Lancez d'abord une extraction TutorBird.")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                selected_teacher = st.selectbox(
                    "👨‍🏫 Professeur",
                    options=[""] + teacher_names,
                    format_func=lambda x: "-- Choisir un professeur --" if x == "" else x,
                    key="tarif_select_teacher"
                )
            
            with col2:
                selected_parent = st.selectbox(
                    "👨‍👩‍👧 Famille",
                    options=[""] + all_families,
                    format_func=lambda x: "-- Choisir une famille --" if x == "" else x,
                    key="tarif_select_parent"
                )
            
            col3, col4 = st.columns(2)
            
            with col3:
                tarif_amount = st.number_input(
                    "💰 Tarif horaire",
                    min_value=0.0,
                    max_value=500.0,
                    value=25.0,
                    step=0.1,
                    key="tarif_amount"
                )
            
            with col4:
                tarif_devise = st.selectbox(
                    "💱 Devise",
                    options=["EUR", "CHF"],
                    key="tarif_devise"
                )
            
            # Vérifier si ce tarif existe déjà
            already_exists = False
            if selected_teacher and selected_parent:
                for t in tarifs:
                    if t.get("teacher") == selected_teacher and t.get("parent") == selected_parent:
                        already_exists = True
                        break
            
            if already_exists:
                st.warning(f"⚠️ Un tarif spécial existe déjà pour **{selected_teacher}** / **{selected_parent}**")
            
            add_disabled = not selected_teacher or not selected_parent or already_exists
            
            if st.button("➕ Ajouter le tarif spécial", type="primary", width="stretch", disabled=add_disabled):
                new_tarif = {
                    "teacher": selected_teacher,
                    "parent": selected_parent,
                    "pay_rate": float(tarif_amount),
                    "currency": tarif_devise
                }
                tarifs.append(new_tarif)
                ctx["save_tarifs_speciaux"](tarifs)
                st.success(f"✅ Tarif spécial ajouté : **{selected_teacher}** / **{selected_parent}** → **{tarif_amount} {tarif_devise}/h**")
                st.rerun()
    
    # ===========================
    # TAB 4: Email
    # ===========================
    with tab4:
        secrets = ctx["load_secrets"]()
        if not secrets:
            secrets = {}
        
        gmail_config = secrets.get("gmail", {})
        
        st.markdown("### 📧 Configuration Email")
        st.info("Configurez votre email Gmail pour envoyer les factures et rappels.")
        
        email = st.text_input("📧 Email Gmail", value=gmail_config.get("email", ""), key="cfg_email")
        app_password = st.text_input("🔑 Mot de passe d'application", value=gmail_config.get("app_password", ""), type="password", key="cfg_app_pwd")
        
        st.markdown("""
        **Comment obtenir un mot de passe d'application :**
        1. Allez sur [myaccount.google.com](https://myaccount.google.com)
        2. Sécurité → Validation en 2 étapes (activez si besoin)
        3. Mots de passe des applications → Générer
        """)
        
        if st.button("💾 Sauvegarder la configuration email", type="primary", width="stretch"):
            if "gmail" not in secrets:
                secrets["gmail"] = {}
            secrets["gmail"]["email"] = email
            secrets["gmail"]["app_password"] = app_password
            ctx["save_secrets"](secrets)
            st.success("✅ Configuration email sauvegardée !")

def _send_prof_pdf(secrets, teacher_name, recipient_email, pdf_bytes, filename, mois_label, silent=False):
    """Envoie un PDF de fiche de paie à un professeur par email.
    
    Args:
        secrets: config avec gmail.email et gmail.app_password
        teacher_name: nom du prof
        recipient_email: email du destinataire
        pdf_bytes: contenu du PDF en bytes
        filename: nom du fichier PDF
        mois_label: ex "Mars 2026"
        silent: si True, ne pas afficher de messages Streamlit (mode batch)
    
    Returns:
        bool: True si envoyé avec succès
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    
    try:
        gmail_config = secrets.get("gmail", {})
        sender_email = gmail_config.get("email")
        app_password = gmail_config.get("app_password")
        
        if not sender_email or not app_password:
            if not silent:
                st.error("❌ Configuration email manquante dans secrets.yaml")
            return False
        
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg["Subject"] = f"Fiche de paie — {mois_label}"
        
        body = f"""Bonjour {teacher_name.split()[-1] if " " in teacher_name else teacher_name},

Veuillez trouver ci-joint votre fiche de paie pour {mois_label}.

N'hésitez pas à me contacter si vous avez des questions.

Cordialement,
Professor+
"""
        msg.attach(MIMEText(body, "plain"))
        
        # Attacher le PDF
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(part)
        
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        
        if not silent:
            st.success(f"✅ Fiche envoyée à {teacher_name} ({recipient_email})")
        return True
    except Exception as e:
        if not silent:
            st.error(f"❌ Erreur envoi à {teacher_name}: {e}")
        return False


def page_profs(ctx):
    import streamlit as st
    import os
    from datetime import datetime

    st.markdown('<div class="section-title">👨‍🏫 Récapitulatif Professeurs</div>', unsafe_allow_html=True)

    data = ctx["load_extracted_data"]()
    secrets = ctx["load_secrets"]()

    if not data:
        st.warning("⚠️ Aucune donnée extraite. Lancez d'abord une extraction TutorBird.")
        return

    if not secrets:
        st.error("❌ Fichier secrets.yaml non trouvé !")
        return

    familles_euros = ctx["load_familles_euros"]()
    tarifs_speciaux = ctx["load_tarifs_speciaux"]()

    # Import local
    from scripts.recap_profs import compute_teacher_recap
    from scripts.generate_prof_pdfs import generate_all_pdfs_to_bytes, generate_single_pdf_to_bytes, generate_all_pdfs_as_zip

    # Calculer le récap
        # Calculer le récap (FX automatique basé sur le mois de la date de fin d'extraction)
    extraction_end = None
    try:
        extraction_end = st.session_state.get('extract_dates', {}).get('end')
    except Exception:
        extraction_end = None

    try:
        recap = compute_teacher_recap(data, secrets, familles_euros, tarifs_speciaux, extraction_end_date=extraction_end)
    except RuntimeError as e:
        st.error(str(e))
        return

    teachers = recap["teachers"]
    grand_total = recap["grand_total"]

    # Déterminer le mois depuis les données
    MONTHS_FR = ctx["MONTHS_FR"]
    all_dates = []
    for fam in data.values():
        for l in fam.get("lessons", []):
            d = l.get("date", "")
            if d:
                all_dates.append(d)

    if all_dates:
        try:
            first_date = datetime.strptime(all_dates[0], "%d.%m.%Y")
            mois_label = f"{MONTHS_FR[first_date.month - 1]} {first_date.year}"
        except Exception:
            mois_label = "Période en cours"
    else:
        mois_label = "Période en cours"

    # ===========================
    # HEADER
    # ===========================
    fx = recap.get("fx")
    fx_rate = fx.get("factor", "?") if fx else "?"
    fx_source = fx.get("source", "") if fx else ""
    fx_display = f"1 CHF = {fx_rate} EUR" if isinstance(fx_rate, float) else "N/A"
    
    st.markdown(f"""
    <div class="header-card">
        <h1>💰 Paie des professeurs — {mois_label}</h1>
        <p>Taux de conversion : {fx_display} ({fx_source})  •  Total : {grand_total:.2f} €</p>
    </div>
    """, unsafe_allow_html=True)

    # Stats globales
    col1, col2, col3 = st.columns(3)
    nb_profs = len([t for t in teachers.values() if t["nb_lessons"] > 0])

    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">👨‍🏫 Professeurs actifs</div>
            <div class="stat-value">{nb_profs}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">📚 Leçons payables</div>
            <div class="stat-value">{recap['total_lessons']}</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">💰 Grand total</div>
            <div class="stat-value">{grand_total:,.2f} €</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ===========================
    # TABLEAU RÉCAP PAR PROF
    # ===========================
    st.markdown('<div class="section-title">📊 Détail par professeur</div>', unsafe_allow_html=True)

    # Logo (cherché une seule fois)
    candidates = [
        os.path.join(ctx["BASE_DIR"], "Professor_logo_dernier.png"),
        os.path.join(ctx["BASE_DIR"], "assets", "logo.png"),
    ]
    logo_path = next((p for p in candidates if os.path.exists(p)), None)

    # ===========================
    # CHARGEMENT DES EMAILS PROFS
    # ===========================
    teacher_emails_map = {}  # teacher_name -> email
    
    # 1) Depuis TutorBird (fichier teacher_emails.json sauvé à l'extraction)
    try:
        tb_emails_path = os.path.join(ctx["DATA_DIR"], "teacher_emails.json")
        if os.path.exists(tb_emails_path):
            with open(tb_emails_path, "r", encoding="utf-8") as f:
                tb_emails = json.load(f)
                teacher_emails_map.update(tb_emails)
        elif is_streamlit_cloud():
            tb_emails = storage_load_json("teacher_emails.json", folder="data")
            if tb_emails:
                teacher_emails_map.update(tb_emails)
    except Exception as _e:
        print(f"⚠️ Erreur chargement emails TutorBird: {_e}")
    
    # 2) Depuis Notion (profs hors TutorBird — colonne "email prof")
    try:
        notion_result = fetch_notion_profs(secrets)
        if notion_result.get("success"):
            for entry in notion_result["entries"]:
                prof_name = entry.get("professeur", "")
                prof_email = entry.get("email_prof", "")
                if prof_name and prof_email and prof_name not in teacher_emails_map:
                    teacher_emails_map[prof_name] = prof_email
    except Exception as _e:
        print(f"⚠️ Erreur chargement emails Notion profs: {_e}")
    
    # 3) Matching normalisé (les noms TutorBird / secrets.yaml ne sont pas toujours identiques)
    from scripts.recap_profs import norm as _norm_prof
    teacher_emails_normalized = {}
    for name, email in teacher_emails_map.items():
        teacher_emails_normalized[_norm_prof(name)] = email
    
    def _get_teacher_email(teacher_name):
        """Retourne l'email du prof, avec matching normalisé."""
        if teacher_name in teacher_emails_map:
            return teacher_emails_map[teacher_name]
        normed = _norm_prof(teacher_name)
        return teacher_emails_normalized.get(normed, "")

    for tname in sorted(teachers.keys()):
        tdata = teachers[tname]
        if tdata["nb_lessons"] == 0:
            continue

        total = tdata["eur"] + tdata["chf_as_eur"]
        teacher_email = _get_teacher_email(tname)
        email_badge = f" — 📧 {teacher_email}" if teacher_email else " — ❌ Pas d'email"

        with st.expander(f"🧑‍🏫 **{tname}** — {tdata['nb_lessons']} leçons — **{total:.2f} €**{email_badge}", expanded=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Familles EUR", f"{tdata['eur']:.2f} €")
            with c2:
                st.metric("Familles CHF→EUR", f"{tdata['chf_as_eur']:.2f} €")
            with c3:
                st.metric("TOTAL", f"{total:.2f} €")

            # Tableau des leçons
            sorted_details = sorted(tdata["details"], key=lambda x: x["date"])
            table_rows = []
            for d in sorted_details:
                table_rows.append({
                    "Date": d["date"],
                    "Élève": d["student"],
                    "Durée": f"{d['duration_min']} min",
                    "Taux": d["rate"],
                    "Devise": d["currency"],
                    "Montant €": f"{d['amount_eur']:.2f}",
                })

            st.dataframe(table_rows, hide_index=True, use_container_width=True)

            # Bouton téléchargement individuel
            safe_name = tname.replace(" ", "_")
            filename = f"Paie_{safe_name}_{mois_label.replace(' ', '_')}.pdf"

            pdf_bytes = generate_single_pdf_to_bytes(tname, tdata, mois_label, logo_path, extraction_end_date=extraction_end)
            col_dl, col_send = st.columns(2)
            with col_dl:
                st.download_button(
                    label=f"📥 Télécharger le PDF",
                    data=pdf_bytes,
                    file_name=filename,
                    mime="application/pdf",
                    key=f"dl_pdf_{safe_name}",
                )
            with col_send:
                if teacher_email:
                    if st.button(f"📧 Envoyer à {teacher_email}", key=f"send_prof_{safe_name}"):
                        _send_prof_pdf(secrets, tname, teacher_email, pdf_bytes, filename, mois_label)
                else:
                    st.caption("❌ Email non disponible")

    # ===========================
    # ENVOI GLOBAL
    # ===========================
    st.markdown("---")
    st.markdown('<div class="section-title">📧 Envoyer les fiches de paie par email</div>', unsafe_allow_html=True)

    # Lister les profs avec email
    profs_with_email = []
    profs_without_email = []
    for tname in sorted(teachers.keys()):
        tdata = teachers[tname]
        if tdata["nb_lessons"] == 0:
            continue
        if tname == "Parisi Lucas":
            continue
        email = _get_teacher_email(tname)
        if email:
            profs_with_email.append({"name": tname, "email": email, "data": tdata})
        else:
            profs_without_email.append(tname)

    if profs_with_email:
        st.info(f"📧 **{len(profs_with_email)}** professeur(s) avec email — prêts à recevoir leur fiche")
        for p in profs_with_email:
            st.caption(f"• {p['name']} → {p['email']}")
    if profs_without_email:
        st.warning(f"⚠️ **{len(profs_without_email)}** professeur(s) sans email : {', '.join(profs_without_email)}")

    col_test, col_real = st.columns(2)
    with col_test:
        if st.button("📧 Envoyer un test à moi-même", width="stretch", key="send_all_profs_test"):
            gmail_config = secrets.get("gmail", {})
            test_email = gmail_config.get("email")
            if not test_email:
                st.error("❌ Email Gmail non configuré dans secrets.yaml")
            else:
                sent = 0
                for p in profs_with_email:
                    pdf_b = generate_single_pdf_to_bytes(p["name"], p["data"], mois_label, logo_path, extraction_end_date=extraction_end)
                    fname = f"Paie_{p['name'].replace(' ', '_')}_{mois_label.replace(' ', '_')}.pdf"
                    ok = _send_prof_pdf(secrets, p["name"], test_email, pdf_b, fname, mois_label, silent=True)
                    if ok:
                        sent += 1
                st.success(f"✅ Test envoyé à {test_email} — {sent}/{len(profs_with_email)} fiche(s)")

    with col_real:
        if st.button("📧 Envoyer à tous les profs", type="primary", width="stretch", key="send_all_profs_real"):
            sent = 0
            errors = []
            for p in profs_with_email:
                pdf_b = generate_single_pdf_to_bytes(p["name"], p["data"], mois_label, logo_path, extraction_end_date=extraction_end)
                fname = f"Paie_{p['name'].replace(' ', '_')}_{mois_label.replace(' ', '_')}.pdf"
                ok = _send_prof_pdf(secrets, p["name"], p["email"], pdf_b, fname, mois_label, silent=True)
                if ok:
                    sent += 1
                else:
                    errors.append(p["name"])
            if errors:
                st.warning(f"⚠️ {sent}/{len(profs_with_email)} envoyé(s) — Erreurs : {', '.join(errors)}")
            else:
                st.success(f"✅ {sent}/{len(profs_with_email)} fiche(s) de paie envoyée(s) !")

    # ===========================
    # TÉLÉCHARGEMENTS GLOBAUX
    # ===========================
    st.markdown("---")
    st.markdown('<div class="section-title">📥 Télécharger toutes les fiches</div>', unsafe_allow_html=True)

    col_zip, col_combined = st.columns(2)

    with col_zip:
        if st.button("📦 Générer le ZIP (1 PDF par prof)", type="primary", width="stretch", key="gen_zip"):
            with st.spinner("Génération du ZIP..."):
                zip_bytes = generate_all_pdfs_as_zip(
                    teachers, mois_label,
                    logo_path=logo_path,
                    exclude_owner="Parisi Lucas",
                    extraction_end_date=extraction_end,
                )
                if zip_bytes:
                    st.session_state.prof_zip_bytes = zip_bytes
                    st.session_state.prof_zip_filename = f"Paie_Profs_{mois_label.replace(' ', '_')}.zip"
                    st.success("✅ ZIP généré !")
                    st.rerun()

    with col_combined:
        if st.button("📄 Générer le PDF combiné (tout en un)", width="stretch", key="gen_combined"):
            with st.spinner("Génération du PDF..."):
                pdf_bytes = generate_all_pdfs_to_bytes(
                    teachers, mois_label,
                    logo_path=logo_path,
                    exclude_owner="Parisi Lucas",
                    extraction_end_date=extraction_end,
                )
                if pdf_bytes:
                    st.session_state.prof_pdf_bytes = pdf_bytes
                    st.session_state.prof_pdf_filename = f"Paie_Profs_{mois_label.replace(' ', '_')}.pdf"
                    st.success("✅ PDF généré !")
                    st.rerun()

    # Boutons de téléchargement
    dl1, dl2 = st.columns(2)

    with dl1:
        if st.session_state.get("prof_zip_bytes"):
            st.download_button(
                label="📥 Télécharger le ZIP",
                data=st.session_state.prof_zip_bytes,
                file_name=st.session_state.get("prof_zip_filename", "paie_profs.zip"),
                mime="application/zip",
                type="primary",
                key="dl_zip_final",
            )

    with dl2:
        if st.session_state.get("prof_pdf_bytes"):
            st.download_button(
                label="📥 Télécharger le PDF combiné",
                data=st.session_state.prof_pdf_bytes,
                file_name=st.session_state.get("prof_pdf_filename", "paie_profs.pdf"),
                mime="application/pdf",
                key="dl_pdf_final",
            )