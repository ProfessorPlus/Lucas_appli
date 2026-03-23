"""
🔧 Config Loader - Version Hybride
==================================
- Google Service Account: depuis st.secrets (TOML) pour pouvoir se connecter à Drive
- Reste de la config (notion, stripe, teachers...): depuis secrets.yaml sur Google Drive
- Config sans transfert: depuis secrets_no_prof.yaml

Usage:
    from scripts.config_loader import load_secrets, load_secrets_no_prof, is_streamlit_cloud
    
    secrets = load_secrets()
    if secrets:
        notion_token = secrets["notion"]["token"]
    
    secrets_no_prof = load_secrets_no_prof()
    if secrets_no_prof:
        stripe_key = secrets_no_prof["stripe"]["platform_secret_key"]
"""

import os
import io
import streamlit as st

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# ===========================
# DÉTECTION ENVIRONNEMENT
# ===========================

def is_streamlit_cloud():
    """Détecte si on est sur Streamlit Cloud."""
    return (
        os.environ.get("STREAMLIT_SHARING_MODE") == "true" or
        os.environ.get("STREAMLIT_SERVER_HEADLESS") == "true" or
        not os.path.exists("secrets.yaml") and not os.path.exists("config/secrets.yaml")
    )


def get_data_dir():
    """Retourne le dossier data approprié."""
    if is_streamlit_cloud():
        data_dir = "/tmp/data"
    else:
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.abspath(data_dir)


def get_invoices_dir():
    """Retourne le dossier factures approprié."""
    if is_streamlit_cloud():
        invoices_dir = "/tmp/Factures"
    else:
        invoices_dir = os.path.join(os.path.dirname(__file__), "..", "Factures")
    os.makedirs(invoices_dir, exist_ok=True)
    return os.path.abspath(invoices_dir)


# ===========================
# GOOGLE DRIVE CONNECTION
# ===========================

def _get_drive_service():
    """
    Crée le service Google Drive en utilisant st.secrets.
    Le google_service_account DOIT être dans st.secrets (TOML).
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        if hasattr(st, 'secrets') and 'google_service_account' in st.secrets:
            creds_info = dict(st.secrets['google_service_account'])
            creds = service_account.Credentials.from_service_account_info(
                creds_info,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"⚠️ Erreur connexion Drive: {e}")
    
    return None


def _download_yaml_from_drive(drive_service, folder_id, filename):
    """
    Télécharge un fichier YAML depuis Google Drive.
    Cherche dans le dossier config/ puis à la racine.
    
    Args:
        drive_service: service Google Drive
        folder_id: ID du dossier racine (Professor_Plus_Data)
        filename: nom du fichier (ex: "secrets.yaml", "secrets_no_prof.yaml")
    
    Returns:
        str: contenu YAML ou None
    """
    try:
        from googleapiclient.http import MediaIoBaseDownload
        
        # D'abord trouver le dossier config
        query = f"name='config' and mimeType='application/vnd.google-apps.folder' and '{folder_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        config_files = results.get('files', [])
        
        config_folder_id = config_files[0]['id'] if config_files else folder_id
        
        # Chercher le fichier dans config/
        query = f"name='{filename}' and '{config_folder_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        files = results.get('files', [])
        
        if not files:
            # Essayer à la racine du dossier Professor_Plus_Data
            query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
            results = drive_service.files().list(q=query, fields="files(id)").execute()
            files = results.get('files', [])
        
        if not files:
            print(f"⚠️ {filename} non trouvé sur Google Drive")
            return None
        
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        buffer.seek(0)
        return buffer.read().decode('utf-8')
        
    except Exception as e:
        print(f"⚠️ Erreur téléchargement {filename}: {e}")
        return None


# Compatibilité avec l'ancien nom
def _download_secrets_from_drive(drive_service, folder_id):
    """Télécharge secrets.yaml depuis Google Drive (compatibilité)."""
    return _download_yaml_from_drive(drive_service, folder_id, "secrets.yaml")


# ===========================
# CHARGEMENT GÉNÉRIQUE YAML
# ===========================

def _get_root_folder_id():
    """Récupère le ROOT_FOLDER_ID depuis st.secrets ou valeur par défaut."""
    root_folder_id = None
    if hasattr(st, 'secrets'):
        root_folder_id = st.secrets.get("google_drive", {}).get("root_folder_id")
    if not root_folder_id:
        root_folder_id = "19Kco_Tu_gZxVgzWuQb5gvB7-7Z3LS-8E"
    return root_folder_id


def _load_yaml_file(filename, local_names=None, cache_dict=None, cache_key=None, force_reload=False):
    """
    Charge un fichier YAML depuis local ou Google Drive.
    
    Args:
        filename: nom du fichier sur Drive (ex: "secrets.yaml")
        local_names: liste de chemins locaux à essayer
        cache_dict: dict de cache (mutable)
        cache_key: clé dans le cache
        force_reload: forcer le rechargement
    
    Returns:
        dict ou None
    """
    # Check cache
    if cache_dict is not None and cache_key and not force_reload:
        cached = cache_dict.get(cache_key)
        if cached is not None:
            return cached
    
    if not YAML_AVAILABLE:
        print("❌ Module yaml non installé")
        return None
    
    result = None
    
    # 1. Mode Streamlit Cloud
    if is_streamlit_cloud():
        drive_service = _get_drive_service()
        if drive_service:
            yaml_content = _download_yaml_from_drive(drive_service, _get_root_folder_id(), filename)
            if yaml_content:
                try:
                    result = yaml.safe_load(yaml_content)
                    print(f"✅ {filename} chargé depuis Google Drive")
                except Exception as e:
                    print(f"❌ Erreur parsing {filename}: {e}")
        else:
            print("❌ Impossible de se connecter à Google Drive")
    
    # 2. Mode local
    else:
        if local_names:
            for path in local_names:
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            result = yaml.safe_load(f)
                        print(f"✅ {filename} chargé depuis {path}")
                        break
                    except Exception as e:
                        print(f"⚠️ Erreur lecture {path}: {e}")
    
    # Update cache (only if we got a result)
    if cache_dict is not None and cache_key and result is not None:
        cache_dict[cache_key] = result
    
    return result


# ===========================
# CHARGEMENT DES SECRETS
# ===========================

_cache = {}

def load_secrets(force_reload=False):
    """
    Charge les secrets depuis:
    1. Streamlit Cloud: secrets.yaml sur Google Drive
    2. Local: fichier secrets.yaml dans config/ ou racine
    """
    return _load_yaml_file(
        filename="secrets.yaml",
        local_names=[
            os.path.join(os.path.dirname(__file__), "..", "config", "secrets.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "secrets.yaml"),
            "config/secrets.yaml",
            "secrets.yaml",
        ],
        cache_dict=_cache,
        cache_key="secrets",
        force_reload=force_reload,
    )


def load_secrets_no_prof(force_reload=False):
    print("🔍 DEBUG: load_secrets_no_prof() appelé")
    """
    Charge secrets_no_prof.yaml (config sans transfert) depuis:
    1. Streamlit Cloud: secrets_no_prof.yaml sur Google Drive (dossier config/)
    2. Local: fichier secrets_no_prof.yaml dans config/ ou racine
    """
    return _load_yaml_file(
        filename="secrets_no_prof.yaml",
        local_names=[
            os.path.join(os.path.dirname(__file__), "..", "config", "secrets_no_prof.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "secrets_no_prof.yaml"),
            "config/secrets_no_prof.yaml",
            "secrets_no_prof.yaml",
        ],
        cache_dict=_cache,
        cache_key="secrets_no_prof",
        force_reload=force_reload,
    )


def clear_secrets_cache():
    """Vide le cache des secrets (utile pour recharger après modification)."""
    _cache.clear()


# ===========================
# HELPERS
# ===========================

def get_secret(key_path, default=None):
    """
    Accède à une valeur de secret par chemin.
    
    Args:
        key_path: Chemin séparé par des points (ex: "notion.token")
        default: Valeur par défaut si non trouvée
    
    Example:
        token = get_secret("notion.token")
        pay_rate = get_secret("teachers.Bruno Lamaison.pay_rate.chf", 55)
    """
    secrets = load_secrets()
    if not secrets:
        return default
    
    keys = key_path.split(".")
    value = secrets
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value