"""
📁 Google Drive Integration for Professor+
Version OAuth-first:
- privilégie un vrai compte Google via OAuth refresh token
- fallback vers service account si aucun OAuth n'est configuré
- compatible My Drive + Shared Drives (supportsAllDrives)

Pourquoi :
Les service accounts n'ont pas de quota de stockage propre pour posséder/uploader des
fichiers dans My Drive. Pour un compte Gmail classique, l'approche la plus simple et
robuste est d'utiliser OAuth avec ton vrai compte Google.
"""

import os
import json
import io
from datetime import datetime

# Optional streamlit — same shim as scripts/config_loader.py so this module
# also loads in non-Streamlit contexts (the FastAPI backend).
try:
    import streamlit as st  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    class _StSecretsShim:
        def get(self, key, default=None):
            return default

        def __contains__(self, key):
            return False

        def __getitem__(self, key):
            raise KeyError(key)

    class _StSessionShim(dict):
        def __setattr__(self, k, v):
            self[k] = v

        def __getattr__(self, k):
            try:
                return self[k]
            except KeyError:
                raise AttributeError(k)

    class _StShim:
        secrets = _StSecretsShim()
        session_state = _StSessionShim()

    st = _StShim()  # type: ignore[assignment]

# Google Drive API
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload


# ===========================
# CONFIGURATION
# ===========================
SCOPES = ['https://www.googleapis.com/auth/drive']
DEFAULT_ROOT_FOLDER_ID = "19Kco_Tu_gZxVgzWuQb5gvB7-7Z3LS-8E"  # Professor_Plus_Data


def get_root_folder_id():
    """Récupère l'ID racine depuis st.secrets si présent, sinon fallback."""
    try:
        if hasattr(st, "secrets") and "google_drive" in st.secrets:
            gd = dict(st.secrets["google_drive"])
            if gd.get("root_folder_id"):
                return gd["root_folder_id"]
    except Exception:
        pass
    return DEFAULT_ROOT_FOLDER_ID


ROOT_FOLDER_ID = get_root_folder_id()


# ===========================
# CREDENTIALS
# ===========================
def _get_oauth_credentials_from_secrets():
    """
    OAuth utilisateur réel (préféré).
    Attendu dans Streamlit secrets:

    [google_oauth]
    client_id = "..."
    client_secret = "..."
    refresh_token = "..."
    token_uri = "https://oauth2.googleapis.com/token"
    """
    try:
        if not hasattr(st, "secrets") or "google_oauth" not in st.secrets:
            return None

        cfg = dict(st.secrets["google_oauth"])
        client_id = cfg.get("client_id")
        client_secret = cfg.get("client_secret")
        refresh_token = cfg.get("refresh_token")
        token_uri = cfg.get("token_uri", "https://oauth2.googleapis.com/token")

        if not (client_id and client_secret and refresh_token):
            return None

        creds = UserCredentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

        # Force un refresh pour s'assurer que les credentials sont utilisables
        creds.refresh(Request())
        return creds

    except Exception as e:
        print(f"⚠️ OAuth Google indisponible: {e}")
        return None


def _get_service_account_credentials():
    """
    Fallback service account:
    - Streamlit Cloud: st.secrets["google_service_account"]
    - Local: fichier JSON
    """
    # 1) Streamlit secrets
    try:
        if hasattr(st, 'secrets') and 'google_service_account' in st.secrets:
            service_account_info = dict(st.secrets['google_service_account'])
            return service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
    except Exception as e:
        print(f"⚠️ Service account depuis st.secrets indisponible: {e}")

    # 2) Fichier local
    local_paths = [
        os.path.join(os.path.dirname(__file__), "..", "config", "google_service_account.json"),
        os.path.join(os.path.dirname(__file__), "..", "google_service_account.json"),
    ]

    for path in local_paths:
        if os.path.exists(path):
            try:
                return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
            except Exception as e:
                print(f"⚠️ Service account local invalide ({path}): {e}")

    return None


def get_credentials():
    """
    Ordre de priorité:
    1) OAuth utilisateur réel (recommandé)
    2) Service account (fallback)
    
    Les credentials sont cachées dans st.session_state.
    """
    # Cache via st.session_state (survit aux reruns Streamlit)
    if hasattr(st, 'session_state') and '_drive_credentials' in st.session_state:
        return st.session_state._drive_credentials
    
    creds = _get_oauth_credentials_from_secrets()
    if creds:
        print("✅ Google Drive via OAuth utilisateur")
        if hasattr(st, 'session_state'):
            st.session_state._drive_credentials = creds
        return creds

    creds = _get_service_account_credentials()
    if creds:
        print("✅ Google Drive via service account (fallback)")
        if hasattr(st, 'session_state'):
            st.session_state._drive_credentials = creds
        return creds

    return None


# Cache du service Drive (au niveau module, pour la durée du script run)
_drive_service_cache = None

def get_drive_service():
    """Crée le service Google Drive (avec cache module-level)."""
    global _drive_service_cache
    if _drive_service_cache is not None:
        return _drive_service_cache
    
    creds = get_credentials()
    if not creds:
        return None
    service = build('drive', 'v3', credentials=creds, cache_discovery=False)
    _drive_service_cache = service
    return service


# ===========================
# HELPERS ALL-DRIVES
# ===========================
def _list_kwargs():
    return {
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }


def _file_kwargs():
    return {
        "supportsAllDrives": True,
    }


# ===========================
# FONCTIONS UTILITAIRES
# ===========================
def find_or_create_folder(service, folder_name, parent_id=None):
    """Trouve ou crée un dossier dans Google Drive."""
    parent_id = parent_id or ROOT_FOLDER_ID

    query = (
        f"name='{folder_name}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"'{parent_id}' in parents and trashed=false"
    )
    results = service.files().list(
        q=query,
        fields="files(id, name)",
        **_list_kwargs(),
    ).execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(
        body=file_metadata,
        fields='id',
        **_file_kwargs(),
    ).execute()
    return folder.get('id')


def find_file(service, filename, folder_id=None):
    """Trouve un fichier par son nom dans un dossier."""
    folder_id = folder_id or ROOT_FOLDER_ID
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name, modifiedTime, size)",
        **_list_kwargs(),
    ).execute()
    files = results.get('files', [])
    return files[0] if files else None


def list_files_in_folder(service, folder_id=None):
    """Liste tous les fichiers dans un dossier."""
    folder_id = folder_id or ROOT_FOLDER_ID
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType, modifiedTime)",
        **_list_kwargs(),
    ).execute()
    return results.get('files', [])


# ===========================
# UPLOAD FUNCTIONS
# ===========================
def upload_file(local_path, drive_filename=None, folder_id=None):
    """
    Upload un fichier local vers Google Drive.

    Returns:
        dict: {"success": bool, "file_id": str, "error": str}
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        folder_id = folder_id or ROOT_FOLDER_ID
        drive_filename = drive_filename or os.path.basename(local_path)

        existing = find_file(service, drive_filename, folder_id)

        mime_type = 'application/octet-stream'
        if local_path.endswith('.json'):
            mime_type = 'application/json'
        elif local_path.endswith('.yaml') or local_path.endswith('.yml'):
            mime_type = 'text/yaml'
        elif local_path.endswith('.pdf'):
            mime_type = 'application/pdf'

        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)

        if existing:
            file = service.files().update(
                fileId=existing['id'],
                media_body=media,
                **_file_kwargs(),
            ).execute()
        else:
            file_metadata = {
                'name': drive_filename,
                'parents': [folder_id]
            }
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                **_file_kwargs(),
            ).execute()

        return {"success": True, "file_id": file.get('id')}

    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_bytes(content, drive_filename, folder_id=None, mime_type='application/octet-stream'):
    """
    Upload des bytes directement vers Google Drive.

    Returns:
        dict: {"success": bool, "file_id": str, "error": str}
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        folder_id = folder_id or ROOT_FOLDER_ID

        if isinstance(content, str):
            content = content.encode('utf-8')

        existing = find_file(service, drive_filename, folder_id)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=True)

        if existing:
            file = service.files().update(
                fileId=existing['id'],
                media_body=media,
                **_file_kwargs(),
            ).execute()
        else:
            file_metadata = {
                'name': drive_filename,
                'parents': [folder_id]
            }
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                **_file_kwargs(),
            ).execute()

        return {"success": True, "file_id": file.get('id')}

    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_json(data, drive_filename, folder_id=None):
    """Upload un dict Python en tant que fichier JSON."""
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return upload_bytes(content, drive_filename, folder_id, 'application/json')


# ===========================
# DOWNLOAD FUNCTIONS
# ===========================
def download_file(file_id, local_path):
    """
    Télécharge un fichier depuis Google Drive.
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        request = service.files().get_media(fileId=file_id, **_file_kwargs())

        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        with open(local_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}


def download_file_by_name(filename, local_path, folder_id=None):
    """
    Télécharge un fichier par son nom.
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        file = find_file(service, filename, folder_id)
        if not file:
            return {"success": False, "error": f"Fichier '{filename}' non trouvé"}

        return download_file(file['id'], local_path)

    except Exception as e:
        return {"success": False, "error": str(e)}


def download_bytes(file_id):
    """
    Télécharge un fichier et retourne son contenu en bytes.
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        request = service.files().get_media(fileId=file_id, **_file_kwargs())
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        return {"success": True, "content": buffer.getvalue()}

    except Exception as e:
        return {"success": False, "error": str(e)}


def download_json(filename, folder_id=None):
    """
    Télécharge un fichier JSON et retourne le dict.
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        file = find_file(service, filename, folder_id)
        if not file:
            return {"success": False, "error": f"Fichier '{filename}' non trouvé"}

        result = download_bytes(file['id'])
        if not result['success']:
            return result

        data = json.loads(result['content'].decode('utf-8'))
        return {"success": True, "data": data}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ===========================
# FOLDER SYNC FUNCTIONS
# ===========================
def sync_folder_to_drive(local_folder, drive_folder_name=None, parent_id=None):
    """
    Synchronise un dossier local vers Google Drive.
    Utilise directement le service Drive (pas de sous-appels à get_drive_service).
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        drive_folder_name = drive_folder_name or os.path.basename(local_folder)
        print(f"📁 sync_folder_to_drive: {local_folder} → Drive/{drive_folder_name} (parent={parent_id})")
        
        folder_id = find_or_create_folder(service, drive_folder_name, parent_id)
        print(f"   📁 Dossier racine Drive ID: {folder_id}")

        uploaded = 0
        errors = []

        for root, dirs, files in os.walk(local_folder):
            rel_path = os.path.relpath(root, local_folder)

            current_folder_id = folder_id
            if rel_path != '.':
                for part in rel_path.split(os.sep):
                    current_folder_id = find_or_create_folder(service, part, current_folder_id)
                    print(f"   📁 Sous-dossier '{part}' → Drive ID: {current_folder_id}")

            for filename in files:
                local_path = os.path.join(root, filename)
                file_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
                print(f"   📤 Upload: {filename} ({file_size} bytes) → folder_id={current_folder_id}")
                
                try:
                    # Upload directement avec le service (pas via upload_file)
                    drive_filename = filename
                    existing = find_file(service, drive_filename, current_folder_id)
                    
                    # Si le fichier n'existe pas par nom exact ET c'est un PDF,
                    # chercher un ancien PDF dans le même dossier pour le remplacer
                    # (cas régénération : date dans le nom change)
                    old_pdf_to_replace = None
                    if not existing and local_path.endswith('.pdf'):
                        try:
                            existing_files = list_files_in_folder(service, current_folder_id)
                            old_pdfs = [f for f in existing_files if f['name'].endswith('.pdf') and f['name'] != drive_filename]
                            if old_pdfs:
                                old_pdf_to_replace = old_pdfs[0]
                                print(f"   🔄 Ancien PDF trouvé: {old_pdf_to_replace['name']} → sera remplacé par {drive_filename}")
                        except Exception:
                            pass
                    
                    mime_type = 'application/octet-stream'
                    if local_path.endswith('.pdf'):
                        mime_type = 'application/pdf'
                    elif local_path.endswith('.json'):
                        mime_type = 'application/json'
                    
                    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
                    
                    if existing:
                        # Même nom → mise à jour du contenu
                        file = service.files().update(
                            fileId=existing['id'],
                            media_body=media,
                            **_file_kwargs(),
                        ).execute()
                        old_size = existing.get('size', '?')
                        new_size = os.path.getsize(local_path)
                        print(f"   ✅ Mis à jour: {filename} (file_id={file.get('id')}, old_size={old_size}, new_size={new_size})")
                    elif old_pdf_to_replace:
                        # Nom différent mais même dossier famille → remplacer contenu + renommer
                        file = service.files().update(
                            fileId=old_pdf_to_replace['id'],
                            body={'name': drive_filename},
                            media_body=media,
                            **_file_kwargs(),
                        ).execute()
                        print(f"   ✅ Remplacé: {old_pdf_to_replace['name']} → {filename} (file_id={file.get('id')})")
                    else:
                        file_metadata = {
                            'name': drive_filename,
                            'parents': [current_folder_id]
                        }
                        file = service.files().create(
                            body=file_metadata,
                            media_body=media,
                            fields='id',
                            **_file_kwargs(),
                        ).execute()
                        print(f"   ✅ Créé: {filename} (file_id={file.get('id')})")
                    
                    uploaded += 1
                    
                except Exception as upload_err:
                    err_msg = f"{filename}: {upload_err}"
                    errors.append(err_msg)
                    print(f"   ❌ ERREUR UPLOAD: {err_msg}")
                    import traceback
                    traceback.print_exc()

        print(f"📊 Sync terminé: {uploaded} uploadé(s), {len(errors)} erreur(s)")
        return {"success": True, "uploaded": uploaded, "errors": errors, "folder_id": folder_id}

    except Exception as e:
        print(f"❌ ERREUR sync_folder_to_drive: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def sync_folder_from_drive(drive_folder_id, local_folder):
    """
    Télécharge un dossier depuis Google Drive.
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        os.makedirs(local_folder, exist_ok=True)

        downloaded = 0
        errors = []

        def download_recursive(folder_id, local_path):
            nonlocal downloaded, errors

            files = list_files_in_folder(service, folder_id)

            for file in files:
                file_path = os.path.join(local_path, file['name'])

                if file['mimeType'] == 'application/vnd.google-apps.folder':
                    os.makedirs(file_path, exist_ok=True)
                    download_recursive(file['id'], file_path)
                else:
                    result = download_file(file['id'], file_path)
                    if result['success']:
                        downloaded += 1
                    else:
                        errors.append(f"{file['name']}: {result['error']}")

        download_recursive(drive_folder_id, local_folder)

        return {"success": True, "downloaded": downloaded, "errors": errors}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ===========================
# HELPER FUNCTIONS
# ===========================
def ensure_drive_structure():
    """
    Crée la structure de dossiers sur Google Drive si nécessaire.

    Structure:
    - Professor_Plus_Data/
      - data/
      - Factures/
      - config/
    """
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Google Drive non configuré"}

    try:
        folders = {}
        root_id = get_root_folder_id()
        for folder_name in ['data', 'Factures', 'config']:
            folder_id = find_or_create_folder(service, folder_name, root_id)
            folders[folder_name] = folder_id

        return {"success": True, "folders": folders}

    except Exception as e:
        return {"success": False, "error": str(e)}


def test_connection():
    """Teste la connexion à Google Drive."""
    service = get_drive_service()
    if not service:
        return {"success": False, "error": "Credentials non trouvées"}

    try:
        root_id = get_root_folder_id()
        service.files().list(
            q=f"'{root_id}' in parents",
            pageSize=1,
            fields="files(id, name)",
            **_list_kwargs(),
        ).execute()

        auth_mode = "oauth_user" if _get_oauth_credentials_from_secrets() else "service_account"
        return {
            "success": True,
            "message": "Connexion Google Drive OK",
            "auth_mode": auth_mode,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}