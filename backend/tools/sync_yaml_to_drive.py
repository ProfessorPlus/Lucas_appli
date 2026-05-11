"""One-off utility — sync a local config YAML to Google Drive.

Diagnoses and fixes the Drive/local desync issue (see MEMORY).
Usage:
    python backend/tools/sync_yaml_to_drive.py familles_euros.yaml
    python backend/tools/sync_yaml_to_drive.py tarifs_speciaux.yaml
    python backend/tools/sync_yaml_to_drive.py --diff-only familles_euros.yaml

The script:
1. Authenticates with Drive via the service account JSON at project root.
2. Locates the file by name within Professor_Plus_Data/config/.
3. Downloads the current Drive content.
4. Diffs against the local config/<name>.yaml.
5. Uploads the local version unless --diff-only.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import yaml
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ACCOUNT_FILE = PROJECT_ROOT / "google_service_account.json.json"
ROOT_FOLDER_NAME = "Professor_Plus_Data"
CONFIG_FOLDER_NAME = "config"

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive():
    creds = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def find_folder_id(drive, name: str, parent_id: str | None = None) -> str | None:
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    res = drive.files().list(q=q, fields="files(id, name)").execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def find_file(drive, name: str, parent_id: str) -> dict | None:
    q = f"name='{name}' and '{parent_id}' in parents and trashed=false"
    res = drive.files().list(q=q, fields="files(id, name, modifiedTime)").execute()
    files = res.get("files", [])
    return files[0] if files else None


def download(drive, file_id: str) -> bytes:
    buf = io.BytesIO()
    request = drive.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    return buf.read()


def upload(drive, file_id: str, content: bytes) -> dict:
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/x-yaml", resumable=False)
    return drive.files().update(fileId=file_id, media_body=media, fields="id, name, modifiedTime").execute()


def _mask(value):
    """Mask any non-trivial value so we never echo a secret to stdout."""
    if value is None or value == "":
        return value
    s = str(value)
    if len(s) <= 6:
        return "***"
    return f"{s[:3]}...{s[-2:]} ({len(s)} chars)"


def _safe_dict_diff(local: dict, drive_data: dict, path: str = "") -> dict:
    """Generic structural diff that masks values — safe to use on secrets.yaml."""
    result: dict = {}
    all_keys = sorted(set(local) | set(drive_data))
    for k in all_keys:
        full_path = f"{path}.{k}" if path else k
        lv, dv = local.get(k), drive_data.get(k)
        if isinstance(lv, dict) and isinstance(dv, dict):
            sub = _safe_dict_diff(lv, dv, full_path)
            if sub:
                result[k] = sub
        elif lv != dv:
            result[k] = {"local": _mask(lv), "drive": _mask(dv)}
    return result


def diff_yaml(name: str, local: dict, drive_data: dict) -> dict:
    """Return a structural diff for these specific YAML shapes."""
    if name == "familles_euros.yaml":
        local_set = set(local.get("euros", []) or [])
        drive_set = set(drive_data.get("euros", []) or [])
        return {
            "added_locally_missing_on_drive": sorted(local_set - drive_set),
            "removed_locally_present_on_drive": sorted(drive_set - local_set),
            "local_count": len(local_set),
            "drive_count": len(drive_set),
        }
    if name == "tarifs_speciaux.yaml":
        def key(t):
            return (t.get("parent_name", ""), t.get("student_name", ""))
        local_idx = {key(t): t for t in (local.get("tarifs_speciaux", []) or [])}
        drive_idx = {key(t): t for t in (drive_data.get("tarifs_speciaux", []) or [])}
        only_local = sorted(local_idx.keys() - drive_idx.keys())
        only_drive = sorted(drive_idx.keys() - local_idx.keys())
        changed = sorted(k for k in (local_idx.keys() & drive_idx.keys()) if local_idx[k] != drive_idx[k])
        return {
            "added_locally": only_local,
            "removed_locally": only_drive,
            "changed": changed,
            "local_count": len(local_idx),
            "drive_count": len(drive_idx),
        }
    # Default — masked diff (safe for secrets.yaml).
    return _safe_dict_diff(local, drive_data)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser()
    p.add_argument("filename", help="ex: familles_euros.yaml")
    p.add_argument("--diff-only", action="store_true", help="show diff without uploading")
    p.add_argument(
        "--from-drive",
        action="store_true",
        help="Reverse direction: overwrite the LOCAL file with the Drive version. "
             "Backs up the previous local content to <name>.local-backup.yaml first.",
    )
    args = p.parse_args()

    local_path = PROJECT_ROOT / "config" / args.filename
    if not local_path.exists():
        sys.exit(f"❌ Local file missing: {local_path}")
    local_bytes = local_path.read_bytes()
    local_data = yaml.safe_load(local_bytes) or {}

    print(f"📁 Local:  {local_path}  ({len(local_bytes)} bytes)")

    drive = get_drive()
    root_id = find_folder_id(drive, ROOT_FOLDER_NAME)
    if not root_id:
        sys.exit(f"❌ Drive folder {ROOT_FOLDER_NAME!r} not found")
    print(f"📁 Drive root: {ROOT_FOLDER_NAME} ({root_id})")

    config_id = find_folder_id(drive, CONFIG_FOLDER_NAME, root_id) or root_id
    print(f"📁 Drive config folder: {config_id}")

    drive_file = find_file(drive, args.filename, config_id)
    if not drive_file:
        sys.exit(f"❌ {args.filename} not found on Drive under {ROOT_FOLDER_NAME}/{CONFIG_FOLDER_NAME}/")

    print(f"📄 Drive file id: {drive_file['id']} (modified {drive_file.get('modifiedTime')})")
    drive_bytes = download(drive, drive_file["id"])
    drive_data = yaml.safe_load(drive_bytes.decode("utf-8")) or {}

    print()
    print("=== DIFF (local vs Drive) ===")
    d = diff_yaml(args.filename, local_data, drive_data)
    print(json.dumps(d, indent=2, ensure_ascii=False))

    if args.diff_only:
        return

    if local_bytes == drive_bytes:
        print("\n✅ Already in sync — nothing to upload.")
        return

    if args.from_drive:
        backup_path = local_path.with_name(local_path.stem + ".local-backup" + local_path.suffix)
        backup_path.write_bytes(local_bytes)
        print(f"\n📋 Backed up previous local to {backup_path.name}")
        local_path.write_bytes(drive_bytes)
        print(f"✅ Overwrote LOCAL with Drive content ({len(drive_bytes)} bytes)")
        # sanity re-read
        again = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
        print(f"✅ Verified: local now parses cleanly ({type(again).__name__})")
        return

    print()
    print("=== UPLOADING local → Drive ===")
    res = upload(drive, drive_file["id"], local_bytes)
    print(f"✅ Uploaded. New modifiedTime: {res.get('modifiedTime')}")

    # Verify by re-downloading
    verify = download(drive, drive_file["id"])
    if verify == local_bytes:
        print("✅ Verified: Drive content matches local.")
    else:
        sys.exit("❌ Verification FAILED — Drive content differs from what was uploaded.")


if __name__ == "__main__":
    main()
