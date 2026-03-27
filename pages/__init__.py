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
from scripts.send_invoices_email import run_send_invoices, get_default_email_template, get_families_from_folder, collect_invoice_diagnostics
from scripts.sync_stripe_notion import run_sync_stripe_notion
from scripts.activate_twint import get_twint_status, activate_twint_for_accounts
from scripts.cleanup_notion import run_cleanup_duplicates, run_scan_notion_dates, run_delete_old_rows
from scripts.send_payment_reminders import run_send_reminders, get_default_reminder_template, get_unpaid_families_from_notion, should_send_automatic_reminder
from scripts.recap_profs import compute_teacher_recap
from scripts.generate_prof_pdfs import generate_all_pdfs_to_bytes, generate_single_pdf_to_bytes, generate_all_pdfs_as_zip
from scripts.create_payment_links_no_split import run_create_payment_links_no_split
from scripts.no_prof_sync_stripe_notion import run_sync_stripe_notion_no_split
from scripts.fetch_notion_profs import fetch_notion_profs, convert_notion_profs_to_families
from scripts.storage_manager import list_invoice_folders, load_invoice_folder, load_json as storage_load_json
from scripts.config_loader import is_streamlit_cloud


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


def page_accueil(ctx):
    st.markdown("""
    <div class="header-card">
        <h1>🎓 Professor+ Admin</h1>
        <p>Gestion complète de votre activité de soutien scolaire</p>
    </div>
    """, unsafe_allow_html=True)
    
    secrets = ctx["load_secrets"]()
    data = ctx["load_extracted_data"]()
    latest = ctx["get_latest_invoice_folder"]()
    
    nb_profs = len(secrets.get("teachers", {})) if secrets else 0
    nb_families = len(data) if data else 0
    total_amount = sum(f.get("total_courses", 0) for f in data.values()) if data else 0
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">👨‍🏫 Professeurs</div>
            <div class="stat-value">{nb_profs}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">👨‍👩‍👧 Familles</div>
            <div class="stat-value">{nb_families}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">💰 À facturer</div>
            <div class="stat-value">{total_amount:,.0f} CHF</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        folder_date = latest["date"].strftime("%d/%m/%Y") if latest else "—"
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">📁 Dernier dossier</div>
            <div class="stat-value" style="font-size: 1.2rem;">{folder_date}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Alerte rappel automatique le 11
    if should_send_automatic_reminder():
        st.warning("🔔 **C'est le 11 du mois !** Pensez à envoyer les rappels de paiement aux familles qui n'ont pas encore payé.")
    
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
            
            st.success(f"""
            ✅ **Extraction terminée !**
            - 📁 **{result['families']}** familles
            - 📚 **{result['lessons']}** leçons
            - 💰 **{result['amount']:,.2f} CHF** total{notion_msg}
            """)
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
    # Récupérer tous les profs de TutorBird
    tutorbird_teachers = set()
    for fam_id, fam in data.items():
        for L in fam.get("lessons", []):
            teacher = L.get("teacher", "")
            if teacher:
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
    
    for tb_teacher in tutorbird_teachers:
        tb_norm = normalize_for_compare(tb_teacher)
        
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
        st.success(f"✅ **{len(matched_teachers)} professeur(s)** - Tous les profs TutorBird sont configurés")
    
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
            
            # Bouton vers génération factures
            if st.session_state.get("show_goto_invoices_tab2"):
                st.markdown("---")
                st.warning("⚠️ **Étape suivante** : Régénérez les factures pour ces familles.")
                if st.button("📄 Aller à Régénérer les factures →", type="primary", width="stretch", key="goto_invoices_t2"):
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
        value=False,
        key=f"no_split_{prefix}",
        help="Active le mode sans split : tous les paiements vont directement sur votre compte Stripe principal (utilise secrets_no_prof.yaml)"
    )
    
    # Méthodes de paiement (communes aux deux modes)
    st.markdown("### 💳 Méthodes de paiement")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        pm_card = st.checkbox("💳 Carte bancaire", value=True, key=f"pm_card_{prefix}")
        pm_link = st.checkbox("🔗 Link", value=True, key=f"pm_link_{prefix}")

    with col2:
        pm_apple = st.checkbox("🍎 Apple Pay", value=True, key=f"pm_apple_{prefix}")
        pm_google = st.checkbox("🤖 Google Pay", value=True, key=f"pm_google_{prefix}")

    with col3:
        col_rev, col_help = st.columns([4, 1])
        with col_rev:
            pm_revolut = st.checkbox("🔄 Revolut Pay", value=True, key=f"pm_revolut_{prefix}")
        with col_help:
            st.markdown("""
            <span title="Revolut Pay est géré via les réglages Stripe" style="cursor: help; color: #666;">❓</span>
            """, unsafe_allow_html=True)
        pm_klarna = st.checkbox("🟢 Klarna", value=True, key=f"pm_klarna_{prefix}")

    with col4:
        pm_twint = st.checkbox("🇨🇭 Twint", value=True, key=f"pm_twint_{prefix}")

    payment_method_types = []

    if pm_card or pm_apple or pm_google:
        payment_method_types.append("card")
    if pm_link:
        payment_method_types.append("link")
    if pm_klarna:
        payment_method_types.append("klarna")
    if pm_twint:
        payment_method_types.append("twint")

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

    tab_fr, tab_en = st.tabs(["🇫🇷 Template français", "🇬🇧 Template anglais"])
    with tab_fr:
        subject = st.text_input("📝 Sujet", value=template_fr["subject"], key="invoice_mail_subject_fr")
        body = st.text_area("✉️ Message", value=template_fr["body"], height=250, key="invoice_mail_body_fr")
    with tab_en:
        subject_en = st.text_input("📝 Subject", value=template_en["subject"], key="invoice_mail_subject_en")
        body_en = st.text_area("✉️ Message", value=template_en["body"], height=250, key="invoice_mail_body_en")

    st.markdown("---")
    st.markdown("### 📬 Options d'envoi")
    col1, col2 = st.columns(2)
    with col1:
        send_all = st.radio("Envoyer à :", ["Toutes les familles", "Sélection personnalisée"], key="send_mode")
    with col2:
        send_test = st.checkbox("📧 Envoyer d'abord à moi-même (test)", value=True)

    families = diagnostics["ready_families"]
    selected_families = None
    if send_all == "Sélection personnalisée":
        family_names = [f["parent_name"] for f in families]
        selected_names = st.multiselect("Sélectionner les familles", family_names)
        selected_families = [f["family_id"] for f in families if f["parent_name"] in selected_names]

    if send_test:
        if st.button("📧 Envoyer le test à moi-même", width="stretch"):
            progress = st.progress(0)
            status = st.empty()

            def callback(p, m):
                progress.progress(p)
                status.info(m)

            result = run_send_invoices(
                secrets, data, folder_path,
                custom_subject=subject, custom_body=body,
                custom_subject_en=subject_en, custom_body_en=body_en,
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
        progress = st.progress(0)
        status = st.empty()

        def callback(p, m):
            progress.progress(p)
            status.info(m)

        result = run_send_invoices(
            secrets, data, folder_path,
            custom_subject=subject, custom_body=body,
            custom_subject_en=subject_en, custom_body_en=body_en,
            selected_families=selected_families,
            send_to_test=False, callback=callback
        )
        if result["success"]:
            st.success(f"✅ **{result['sent']}/{result['total']}** emails envoyés")
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
    # ÉTAPE 1 : CHARGER LES IMPAYÉS DEPUIS NOTION
    # ===========================
    st.markdown("### 📋 Étape 1 — Familles non payées (Notion)")
    
    if st.button("🔍 Charger les familles non payées depuis Notion", width="stretch", key="load_unpaid_notion"):
        with st.spinner("Chargement depuis Notion..."):
            result = get_unpaid_families_from_notion(secrets)
            if result["success"]:
                st.session_state.unpaid_families = result["unpaid"]
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
    
    # ===========================
    # ÉTAPE 2 : SÉLECTION DU DOSSIER DE FACTURES (depuis Drive)
    # ===========================
    st.markdown("### 📁 Étape 2 — Dossier de factures (pour joindre les PDFs)")
    
    mode_rem, selected_folder_rem = _render_invoice_folder_selector(
        "invoice_folder_mode_reminder", "invoice_folder_select_reminder", default_to_latest=False
    )
    
    folder_path = None
    if mode_rem == "Utiliser un dossier existant" and selected_folder_rem:
        folder_path = _ensure_local_invoice_folder(selected_folder_rem)
        if not folder_path:
            st.error("❌ Impossible de charger le dossier sélectionné depuis Google Drive.")
    elif mode_rem != "Utiliser un dossier existant":
        st.warning("⚠️ Sélectionnez un dossier existant pour joindre les factures aux rappels.")
    
    st.markdown("---")
    
    # ===========================
    # ÉTAPE 3 : TEMPLATE + OPTIONS
    # ===========================
    st.markdown("### ✉️ Étape 3 — Message de rappel")
    
    # Déduire mois/année depuis le dossier ou la date courante
    if selected_folder_rem:
        month_name, year = ctx["get_month_year_from_folder"]({
            "name": selected_folder_rem["month"],
            "date": _parse_invoice_folder_dt(selected_folder_rem["month"])
        })
    else:
        month_name = ctx["MONTHS_FR"][datetime.now().month - 1]
        year = datetime.now().year
    
    template = get_default_reminder_template(month_name, year)
    
    subject = st.text_input("📝 Sujet", value=template["subject"], key="reminder_subject")
    body = st.text_area("✉️ Message", value=template["body"], height=250, key="reminder_body")
    
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
    
    # Charger les données TutorBird pour le matching des factures PDF
    data = _try_load_data(ctx)
    if not data:
        st.caption("💡 Les données TutorBird ne sont pas chargées. Les factures PDF ne seront pas jointes automatiquement.")
    
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
                selected_families=selected_names,
                send_to_test=True, callback=callback
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
            selected_families=selected_names,
            send_to_test=False, callback=callback
        )
        
        if result["success"]:
            sent = result.get("sent", 0)
            total = result.get("total", 0)
            errors = result.get("errors", [])
            
            if errors:
                st.warning(f"⚠️ **{sent}/{total}** rappels envoyés — **{len(errors)}** erreur(s)")
            else:
                st.success(f"✅ **{sent}/{total}** rappels envoyés avec succès !")
            
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
    
    st.info("""
    **À quoi sert cette synchronisation ?**
    
    Cette fonction récupère les paiements effectués sur Stripe et :
    1. Marque automatiquement les lignes comme "Payé" dans Notion
    2. Met à jour les tableaux dans les pages des professeurs
    3. Met à jour les récapitulatifs de paiements
    4. Met à jour le dashboard global
    
    **Matching par :** Prof + Élève + Montant (via extraction du reçu Stripe)
    """)
    
    secrets = ctx["load_secrets"]()
    latest = ctx["get_latest_invoice_folder"]()
    
    # Détecter le mode no-split
    is_no_split = st.session_state.get("no_split_mode_active", False)
    
    if is_no_split:
        st.info("🏦 **Mode sans transfert détecté** — Sync simplifiée (famille + montant, pas de pages profs)")
    
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
        
        if is_no_split:
            # ===========================
            # MODE NO-SPLIT : sync simplifiée
            # ===========================
            def callback_ns(p, m):
                progress.progress(p)
                status.info(m)
            
            secrets_no_prof = ctx.get("load_secrets_no_prof", lambda: None)()
            if not secrets_no_prof:
                st.error("❌ secrets_no_prof.yaml non trouvé !")
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
                
                if result1.get("not_found"):
                    with st.expander("⚠️ Paiements non trouvés dans Notion"):
                        for nf in result1["not_found"]:
                            st.write(f"• {nf}")
            else:
                st.error(f"❌ Erreur : {result1['error']}")
        
        else:
            # ===========================
            # MODE NORMAL : sync avec pages profs
            # ===========================
            def callback1(p, m):
                progress.progress(int(p * 0.5))
                status.info(f"[1/2] {m}")
            
            from scripts.sync_stripe_notion import run_sync_stripe_notion
            result1 = run_sync_stripe_notion(secrets, since_date, callback1)
            
            if not result1["success"]:
                st.error(f"❌ Erreur sync Stripe : {result1['error']}")
                return
            
            # ===========================
            # ÉTAPE 2: Mise à jour des pages profs
            # ===========================
            def callback2(p, m):
                progress.progress(50 + int(p * 0.5))
                status.info(f"[2/2] {m}")
            
            from scripts.update_notion_prof_pages import run_update_notion_prof_pages
            result2 = run_update_notion_prof_pages(secrets, callback2, force=False, latest_only=False)
            
            progress.progress(100)
            status.empty()
            
            # ===========================
            # Affichage des résultats
            # ===========================
            if result1["success"] and result2["success"]:
                st.success(f"""
                ✅ **Synchronisation terminée**
                
                **Stripe → Notion :**
                - {result1['synced']} paiement(s) synchronisé(s)
                - {result1['already_paid']} déjà marqué(s) payé(s)
                - {result1.get('student_unknown', 0)} élève(s) inconnu(s) (reçu vide)
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
            
            **Stripe → Notion :**
            - {result1['synced']} paiement(s) synchronisé(s)
            
            **Erreur pages profs :**
            {result2['error']}
            """)

"""
Nouvelle version de page_update avec 3 onglets :
1. Ajouter toutes les lignes
2. Mettre à jour certaines lignes  
3. Vérifier & Compléter (NOUVEAU)
"""

def page_update(ctx):
    st.markdown('<div class="section-title">📤 Ajouter lignes Notion</div>', unsafe_allow_html=True)
    
    secrets = ctx["load_secrets"]()
    
    if not secrets:
        st.error("❌ Fichier secrets.yaml non trouvé !")
        return
    
    # Chargement des données avec fallback Drive
    data = _try_load_data(ctx)
    
    if not data:
        st.warning("⚠️ **Données des familles non disponibles.** Elles sont nécessaires pour ajouter les lignes Notion.")
        if st.button("📥 Charger les données depuis TutorBird / Google Drive", key="load_tb_data_update"):
            with st.spinner("Chargement..."):
                data = _try_load_data(ctx)
                if data:
                    st.success(f"✅ {len(data)} famille(s) chargées")
                    st.rerun()
                else:
                    st.error("❌ Aucune donnée trouvée. Lancez d'abord une extraction TutorBird.")
        return
    
    # Options no-split
    is_no_split = st.session_state.get("no_split_mode_active", False)

    if is_no_split:
        st.info("🏦 **Mode sans transfert actif** — Les lignes seront ajoutées sans colonne prof et sans sous-pages profs.")
        skip_prof_subpages = True
        st.checkbox("🚫 Ne pas créer les sous-pages dans les pages des professeurs (Prof → Date → Élève)", value=True, disabled=True, key="skip_prof_subpages_update_locked")
    else:
        skip_prof_subpages = st.checkbox("🚫 Ne pas créer les sous-pages dans les pages des professeurs (Prof → Date → Élève)", value=True, key="skip_prof_subpages_update")

    effective_no_split = is_no_split or skip_prof_subpages
    
    default_tab = 1 if st.session_state.get("update_tab") == "selective" else 0
    tab1, tab2, tab3 = st.tabs(["➕ Ajouter toutes les lignes", "🔄 Mettre à jour certaines lignes", "🔍 Ajouter ligne(s) manquante(s)"])
    
    with tab1:
        st.markdown("### 📁 Dossier de travail")
        mode_t1, selected_folder_t1 = _render_invoice_folder_selector("update_folder_mode_t1", "update_folder_select_t1", default_to_latest=False)
        
        folder_name_t1 = "N/A"
        if mode_t1 == "Utiliser un dossier existant" and selected_folder_t1:
            folder_name_t1 = selected_folder_t1.get("month", "N/A")
        elif mode_t1 != "Utiliser un dossier existant":
            st.warning("⚠️ Sélectionnez un dossier existant pour ajouter les lignes Notion.")
        
        st.markdown("---")
        
        if effective_no_split:
            reason = "(mode sans transfert)" if is_no_split else "(option cochée)"
            st.info(f"""
            **Cette action va :**
            1. Ajouter **{len(data)}** lignes dans la base de données Paiements
            2. **Ne pas créer les sous-pages profs** {reason}
            
            📁 Dossier : **{folder_name_t1}**
            
            ⚠️ Les lignes déjà existantes (même famille + même montant) seront ignorées.
            """)
        else:
            st.info(f"""
            **Cette action va :**
            1. Ajouter **{len(data)}** lignes dans la base de données Paiements
            2. Créer les sous-pages dans les pages des professeurs (Prof → Date → Élève)
            
            📁 Dossier : **{folder_name_t1}**
            
            ⚠️ Les lignes déjà existantes (même famille + même montant) seront ignorées.
            """)
        
        if st.button("📤 Ajouter les lignes", type="primary", width="stretch", key="add_all_notion"):
            progress = st.progress(0)
            status = st.empty()
            def callback(p, m):
                progress.progress(p)
                status.info(m)
            result = run_update_notion(secrets, data, ctx["BASE_DIR"], callback, no_split=effective_no_split)
            if result["success"]:
                added = result.get('added', 0)
                skipped_dup = result.get('skipped', 0)
                no_lessons = result.get('no_lessons', 0)
                api_failed = result.get('api_failed', 0)
                total_fam = result.get('total_families', 0)
                
                if added > 0:
                    st.success(f"""
                    ✅ **Ajout terminé**
                    - {added} ligne(s) ajoutée(s)
                    - {skipped_dup} ignorée(s) (doublons)
                    - {result.get('pages_created', 0)} sous-page(s) prof créée(s)
                    """)
                else:
                    st.warning(f"""
                    ⚠️ **Aucune ligne ajoutée** — Diagnostic détaillé :
                    - 📊 **{total_fam}** familles dans les données
                    - ⏭️ **{skipped_dup}** ignorée(s) car doublon (déjà dans Notion)
                    - 📭 **{no_lessons}** famille(s) sans leçon après filtrage des absences
                    - ❌ **{api_failed}** échec(s) API Notion
                    - 🔢 Reste non comptabilisé : **{total_fam - skipped_dup - no_lessons - api_failed - added}**
                    """)
                    if api_failed > 0:
                        st.error("💡 Des appels API Notion ont échoué. Vérifiez les logs Streamlit pour voir les détails d'erreur.")
                    if no_lessons > 0:
                        st.info("💡 Certaines familles n'ont aucune leçon (ou toutes marquées AbsentNotice). C'est normal si ce sont des familles sans cours ce mois-ci.")
                    if skipped_dup == total_fam:
                        st.info("💡 Toutes les familles sont déjà dans Notion ! Si vous voulez re-créer les lignes, supprimez d'abord les anciennes via **Nettoyage Notion**.")
            else:
                st.error(f"❌ Erreur : {result['error']}")
    
    with tab2:
        st.markdown("### 🔄 Mettre à jour certaines lignes Notion")
        st.info("Remplacez les valeurs des lignes existantes pour certaines familles après avoir régénéré des factures.")
        
        st.markdown("### 📁 Dossier de travail")
        mode_t2, selected_folder_t2 = _render_invoice_folder_selector("update_folder_mode_t2", "update_folder_select_t2", default_to_latest=False)
        
        folder_path_t2 = None
        if mode_t2 == "Utiliser un dossier existant" and selected_folder_t2:
            folder_path_t2 = _ensure_local_invoice_folder(selected_folder_t2)
            if not folder_path_t2:
                st.error("❌ Impossible de charger le dossier depuis Google Drive.")
        elif mode_t2 != "Utiliser un dossier existant":
            st.warning("⚠️ Sélectionnez un dossier existant.")
        
        if not folder_path_t2:
            st.warning("⚠️ Veuillez sélectionner un dossier de factures pour continuer.")
        else:
            st.markdown("---")
            mode = st.radio("🔍 Mode de sélection :", ["👨‍👩‍👧 Par famille", "👨‍🏫 Par professeur"], horizontal=True, key="update_selection_mode")
            st.markdown("---")
            selected_family_ids = []
            selected_teachers = []
            
            if mode == "👨‍👩‍👧 Par famille":
                preselected = st.session_state.get("regenerated_invoices_families", [])
                family_list = [(fam_id, fam.get("parent_name", fam_id)) for fam_id, fam in data.items()]
                family_names = [f"{name} ({fam_id})" for fam_id, name in family_list]
                default_selection = [f"{name} ({fid})" for fid, name in family_list if fid in preselected]
                selected_families_display = st.multiselect("📋 Sélectionnez les familles à mettre à jour", family_names, default=default_selection, key="select_families_notion_update_mode1")
                for sel in selected_families_display:
                    for fam_id, name in family_list:
                        if f"{name} ({fam_id})" == sel:
                            selected_family_ids.append(fam_id)
                if selected_family_ids:
                    for fam_id in selected_family_ids:
                        for L in data.get(fam_id, {}).get("lessons", []):
                            teacher = L.get("teacher", "")
                            if teacher and teacher not in selected_teachers:
                                selected_teachers.append(teacher)
                    st.info(f"📊 **{len(selected_family_ids)}** famille(s) → **{len(selected_teachers)}** professeur(s)")
            else:
                all_teachers = {}
                for fam_id, fam in data.items():
                    for L in fam.get("lessons", []):
                        teacher = L.get("teacher", "")
                        if teacher:
                            all_teachers.setdefault(teacher, {"families": set()})["families"].add(fam_id)
                teacher_options = [f"{name} ({len(info['families'])} famille(s))" for name, info in sorted(all_teachers.items())]
                selected_teachers_display = st.multiselect("👨‍🏫 Sélectionnez les professeurs", teacher_options, key="select_teachers_notion_update_mode2")
                for sel in selected_teachers_display:
                    teacher_name = sel.split(" (")[0]
                    selected_teachers.append(teacher_name)
                    if teacher_name in all_teachers:
                        for fam_id in all_teachers[teacher_name]["families"]:
                            if fam_id not in selected_family_ids:
                                selected_family_ids.append(fam_id)
                if selected_teachers:
                    st.info(f"👨‍🏫 **{len(selected_teachers)}** professeur(s) → **{len(selected_family_ids)}** famille(s)")
            
            if selected_family_ids and selected_teachers:
                st.markdown("---")
                st.warning(f"⚠️ Scanner **{selected_folder_t2['month']}** et mettre à jour **{len(selected_family_ids)}** ligne(s) Notion")
                if st.button("🔄 Mettre à jour les lignes sélectionnées", type="primary", width="stretch", key="update_selective_notion"):
                    progress = st.progress(0)
                    status = st.empty()
                    def callback(p, m):
                        progress.progress(p)
                        status.info(m)
                    result = run_update_notion_selective(secrets, data, folder_path_t2, selected_family_ids, selected_teachers, callback, no_split=effective_no_split)
                    if result["success"]:
                        st.success(f"✅ {result.get('rows_updated', 0)} ligne(s) mise(s) à jour, {result.get('subpages_updated', 0)} sous-page(s)")
                        if result.get("details"):
                            with st.expander("📋 Détails"):
                                for detail in result["details"]:
                                    st.write(f"• **{detail['family']}** / {detail['teacher']} : {detail['amount']} {detail['currency']}")
                        st.session_state.regenerated_invoices_families = []
                        st.session_state.update_tab = None
                    else:
                        st.error(f"❌ Erreur : {result['error']}")
            else:
                st.warning("⚠️ Sélectionnez au moins une famille ou un professeur.")
            st.session_state.update_tab = None
    
    with tab3:
        st.markdown("### 🔍 Ajouter ligne(s) manquante(s)")
        st.markdown("### 📁 Dossier à analyser")
        mode_t3, selected_folder_t3 = _render_invoice_folder_selector("update_folder_mode_t3", "update_folder_select_t3", default_to_latest=False)
        
        folder_path_t3 = None
        if mode_t3 == "Utiliser un dossier existant" and selected_folder_t3:
            folder_path_t3 = _ensure_local_invoice_folder(selected_folder_t3)
            if not folder_path_t3:
                st.error("❌ Impossible de charger le dossier depuis Google Drive.")
        elif mode_t3 != "Utiliser un dossier existant":
            st.warning("⚠️ Sélectionnez un dossier existant.")
        
        if not folder_path_t3:
            st.info("Sélectionnez un dossier de factures ci-dessus pour scanner les lignes manquantes.")
        else:
            st.info("Scanner le dossier sélectionné, comparer avec Notion et ajouter les lignes manquantes.")
            if st.button("🔍 Scanner et comparer", type="primary", width="stretch", key="scan_compare_notion"):
                progress = st.progress(0)
                status = st.empty()
                def callback(p, m):
                    progress.progress(p)
                    status.info(m)
                result = run_scan_and_compare(secrets, data, folder_path_t3, callback)
                if result["success"]:
                    st.session_state.scan_compare_result = result
                    missing = result.get("missing", [])
                    already_exists = result.get("already_exists", [])
                    st.success(f"✅ {result['invoices_scanned']} facture(s) scannée(s), {result['notion_rows']} lignes Notion, {len(already_exists)} déjà OK, {len(missing)} manquante(s)")
                    if missing:
                        st.warning(f"⚠️ **{len(missing)} ligne(s) manquante(s) :**")
                        missing_data = [{"Famille": m["family_name"], "Professeur": m["teacher"], "Montant": f"{m['amount']:.2f} {m.get('currency', 'CHF')}", "Élèves": m.get("students_formatted", "")} for m in missing]
                        st.dataframe(missing_data, width="stretch", hide_index=True)
                    else:
                        st.success("🎉 Toutes les factures ont une ligne dans Notion !")
                else:
                    st.error(f"❌ Erreur : {result['error']}")
            
            if "scan_compare_result" in st.session_state:
                missing = st.session_state.scan_compare_result.get("missing", [])
                if missing:
                    st.markdown("---")
                    if st.button(f"➕ Ajouter les {len(missing)} ligne(s) manquante(s)", type="primary", width="stretch", key="add_missing_notion"):
                        progress = st.progress(0)
                        status = st.empty()
                        def callback(p, m):
                            progress.progress(p)
                            status.info(m)
                        add_result = run_add_missing_rows(secrets, data, missing, callback)
                        if add_result["success"]:
                            st.success(f"✅ **{add_result['added']}** ligne(s) ajoutée(s)")
                            if add_result.get("errors"):
                                with st.expander("⚠️ Erreurs"):
                                    for err in add_result["errors"]:
                                        st.error(err)
                            del st.session_state.scan_compare_result
                            if add_result["added"] > 0:
                                st.info("💡 **Prochaine étape :** Sync Stripe → Notion")
                                if st.button("🔄 Aller vers Sync Stripe → Notion", width="stretch", key="go_to_sync"):
                                    st.session_state.current_page = "sync"
                                    st.rerun()
                        else:
                            st.error(f"❌ Erreur : {add_result['error']}")


def page_config(ctx):
    st.markdown('<div class="section-title">⚙️ Configuration</div>', unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs(["👨‍🏫 Professeurs", "💶 Familles EUR", "🏷️ Tarifs spéciaux", "📧 Email"])
    
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
    st.markdown(f"""
    <div class="header-card">
        <h1>💰 Paie des professeurs — {mois_label}</h1>
        <p>Taux de conversion : 1 CHF = 1.0896 EUR  •  Total : {grand_total:.2f} €</p>
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

    for tname in sorted(teachers.keys()):
        tdata = teachers[tname]
        if tdata["nb_lessons"] == 0:
            continue

        total = tdata["eur"] + tdata["chf_as_eur"]

        with st.expander(f"🧑‍🏫 **{tname}** — {tdata['nb_lessons']} leçons — **{total:.2f} €**", expanded=False):
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

            pdf_bytes = generate_single_pdf_to_bytes(tname, tdata, mois_label, logo_path)
            st.download_button(
                label=f"📥 Télécharger le PDF de {tname}",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                key=f"dl_pdf_{safe_name}",
            )

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