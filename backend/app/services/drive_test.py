"""Drive connectivity & write tests (Settings → Drive tab)."""
from __future__ import annotations

import io
import time
from typing import Any

from app.services.paths import PROJECT_ROOT


def drive_test() -> dict[str, Any]:
    """List files in Professor_Plus_Data/config to verify read access."""
    try:
        from app.services.yaml_io import _get_drive, _drive_root, _drive_config_folder
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    drv = _get_drive()
    if not drv:
        return {"ok": False, "error": "Drive service unavailable (service account missing?)"}
    root = _drive_root()
    folder = _drive_config_folder()
    files = []
    if folder:
        res = drv.files().list(
            q=f"'{folder}' in parents and trashed=false",
            fields="files(id, name, size, modifiedTime)",
        ).execute()
        files = res.get("files", [])
    return {
        "ok": bool(folder),
        "root_id": root,
        "config_folder_id": folder,
        "files": files,
    }


def drive_write_test() -> dict[str, Any]:
    """Verify Drive write access by touching an existing config file's
    modifiedTime (re-uploading identical content). Service accounts can't
    create new files in user-owned Drive folders, but they CAN update
    existing ones shared with them — which is what we need."""
    try:
        from googleapiclient.http import MediaIoBaseUpload
        from app.services.yaml_io import _get_drive, _find_drive_file, _download_drive
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    drv = _get_drive()
    if not drv:
        return {"ok": False, "error": "Drive service unavailable"}
    # Use a safe target — an existing YAML config.
    target = "familles_euros.yaml"
    f = _find_drive_file(target)
    if not f:
        return {"ok": False, "error": f"Test target {target!r} not found on Drive"}
    blob = _download_drive(target)
    if blob is None:
        return {"ok": False, "error": "Could not download test target"}
    try:
        media = MediaIoBaseUpload(io.BytesIO(blob), mimetype="application/x-yaml")
        updated = drv.files().update(
            fileId=f["id"], media_body=media, fields="id, name, modifiedTime"
        ).execute()
        return {
            "ok": True,
            "test_target": target,
            "drive_id": updated["id"],
            "new_modified_time": updated["modifiedTime"],
            "note": "Tested by re-uploading identical content (no data change).",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "test_target": target}
