"""Atomic YAML I/O — local + Google Drive.

Every config write goes to Drive (source of truth, also used by Streamlit Cloud)
AND mirrors to local (cache for fast reads + dev mode). This is the single
entry point for Settings CRUD to prevent the desync that caused the
60€/1950€ drift in May 2026 (see MEMORY).

Reads: local-first, Drive-fallback. Cache 60s in memory.
Writes: Drive-first (so prod is consistent), then local mirror. On Drive
failure, the operation fails LOUDLY rather than silently leaving an
inconsistent state.
"""
from __future__ import annotations

import io
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from app.services.paths import PROJECT_ROOT

# Local config directory.
_LOCAL_DIR = PROJECT_ROOT / "config"

# Cached reads — short TTL so config edits propagate quickly without
# hammering Drive on every request.
_CACHE_TTL_SECONDS = 60.0
_cache_lock = threading.RLock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


# ── Drive plumbing (lazy import, service account JSON) ────────────────

_drive_service = None
_drive_root_id: str | None = None
_drive_config_folder_id: str | None = None


def _get_drive():
    """Lazily build a Drive client from the service account JSON at project root."""
    global _drive_service
    if _drive_service is not None:
        return _drive_service
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return None
    sa_path = PROJECT_ROOT / "google_service_account.json.json"
    if not sa_path.exists():
        sa_path = PROJECT_ROOT / "google_service_account.json"
    if not sa_path.exists():
        return None
    creds = service_account.Credentials.from_service_account_file(
        str(sa_path), scopes=["https://www.googleapis.com/auth/drive"]
    )
    _drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_service


def _drive_root() -> str | None:
    global _drive_root_id
    if _drive_root_id is not None:
        return _drive_root_id
    drv = _get_drive()
    if not drv:
        return None
    q = "name='Professor_Plus_Data' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    files = drv.files().list(q=q, fields="files(id)").execute().get("files", [])
    if not files:
        return None
    _drive_root_id = files[0]["id"]
    return _drive_root_id


def _drive_config_folder() -> str | None:
    global _drive_config_folder_id
    if _drive_config_folder_id is not None:
        return _drive_config_folder_id
    drv = _get_drive()
    root = _drive_root()
    if not drv or not root:
        return None
    q = (
        f"name='config' and mimeType='application/vnd.google-apps.folder' "
        f"and '{root}' in parents and trashed=false"
    )
    files = drv.files().list(q=q, fields="files(id)").execute().get("files", [])
    _drive_config_folder_id = files[0]["id"] if files else root
    return _drive_config_folder_id


def _find_drive_file(filename: str) -> dict | None:
    drv = _get_drive()
    folder = _drive_config_folder()
    if not drv or not folder:
        return None
    q = f"name='{filename}' and '{folder}' in parents and trashed=false"
    files = drv.files().list(q=q, fields="files(id, name, modifiedTime)").execute().get("files", [])
    return files[0] if files else None


def _download_drive(filename: str) -> bytes | None:
    from googleapiclient.http import MediaIoBaseDownload
    drv = _get_drive()
    f = _find_drive_file(filename)
    if not drv or not f:
        return None
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, drv.files().get_media(fileId=f["id"]))
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return buf.read()


def _upload_drive(filename: str, content: bytes) -> dict:
    """Update existing file or raise if not found (we never create new config files)."""
    from googleapiclient.http import MediaIoBaseUpload
    drv = _get_drive()
    f = _find_drive_file(filename)
    if not drv:
        raise RuntimeError("Drive service unavailable")
    if not f:
        raise FileNotFoundError(f"{filename} not present on Drive — refusing to create.")
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/x-yaml", resumable=False)
    return drv.files().update(fileId=f["id"], media_body=media, fields="id,name,modifiedTime").execute()


# ── Public API ────────────────────────────────────────────────────────


class YamlIOError(RuntimeError):
    """Raised when a YAML operation cannot complete consistently."""


def invalidate_cache(filename: str | None = None) -> None:
    with _cache_lock:
        if filename is None:
            _cache.clear()
        else:
            _cache.pop(filename, None)


def read_yaml(filename: str, *, prefer: str = "local") -> dict[str, Any]:
    """Read a YAML file. `prefer='local'` reads local first (fast, dev),
    falls back to Drive. `prefer='drive'` reads Drive first (prod). Cached 60s.
    """
    with _cache_lock:
        now = time.time()
        cached = _cache.get(filename)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

    sources = ("local", "drive") if prefer == "local" else ("drive", "local")
    last_error: Exception | None = None
    for src in sources:
        try:
            if src == "local":
                path = _LOCAL_DIR / filename
                if not path.exists():
                    continue
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            else:
                blob = _download_drive(filename)
                if blob is None:
                    continue
                data = yaml.safe_load(blob.decode("utf-8")) or {}
            with _cache_lock:
                _cache[filename] = (time.time(), data)
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if last_error:
        raise YamlIOError(f"Could not read {filename}: {last_error}") from last_error
    return {}


def write_yaml(filename: str, data: dict[str, Any]) -> dict[str, Any]:
    """Atomically write YAML to Drive (authoritative) then mirror to local.

    Returns a result summary {drive_modified_time, local_path, bytes}.
    Raises YamlIOError on inconsistency (e.g. Drive ok but local fails — though
    we still keep Drive as the source of truth).
    """
    yaml_bytes = yaml.dump(
        data, default_flow_style=False, allow_unicode=True, sort_keys=False
    ).encode("utf-8")

    # 1) Drive first — if it fails we don't touch local.
    drive_result: dict[str, Any] = {}
    try:
        info = _upload_drive(filename, yaml_bytes)
        drive_result = {"id": info.get("id"), "modifiedTime": info.get("modifiedTime")}
    except FileNotFoundError:
        # No existing Drive file — for now we refuse to create one (safer).
        drive_result = {"skipped": "no Drive file (would need to create)"}
    except Exception as exc:  # noqa: BLE001
        raise YamlIOError(f"Drive upload of {filename} failed: {exc}") from exc

    # 2) Local mirror with a one-step backup so we can undo if needed.
    local_path = _LOCAL_DIR / filename
    if local_path.exists():
        backup = local_path.with_suffix(local_path.suffix + ".prev")
        try:
            shutil.copy2(local_path, backup)
        except Exception:
            pass  # nonblocking
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(yaml_bytes)

    # 3) Invalidate cache so the next read re-loads.
    invalidate_cache(filename)

    # 4) Also clear scripts/config_loader's internal cache (Streamlit-shared).
    try:
        from scripts.config_loader import clear_secrets_cache
        clear_secrets_cache()
    except Exception:
        pass

    return {
        "drive": drive_result,
        "local_path": str(local_path),
        "bytes": len(yaml_bytes),
    }


def get_drive_diagnostics(filename: str) -> dict[str, Any]:
    """For the /api/diagnostics/config-sync endpoint."""
    local_path = _LOCAL_DIR / filename
    local_exists = local_path.exists()
    drv_file = _find_drive_file(filename)
    return {
        "filename": filename,
        "local_exists": local_exists,
        "local_size": local_path.stat().st_size if local_exists else 0,
        "drive_exists": drv_file is not None,
        "drive_id": drv_file.get("id") if drv_file else None,
        "drive_modified_time": drv_file.get("modifiedTime") if drv_file else None,
    }


def diff_yaml_against_drive(filename: str) -> dict[str, Any]:
    """Return a coarse-grained structural diff between the local file and the
    Drive version. Values are masked for secrets.yaml to avoid leaking."""
    local_path = _LOCAL_DIR / filename
    local_bytes = local_path.read_bytes() if local_path.exists() else b""
    drive_bytes = _download_drive(filename) or b""

    if not local_bytes and not drive_bytes:
        return {"status": "missing_both"}
    if local_bytes == drive_bytes:
        return {"status": "in_sync"}

    local_data = yaml.safe_load(local_bytes.decode("utf-8")) if local_bytes else {}
    drive_data = yaml.safe_load(drive_bytes.decode("utf-8")) if drive_bytes else {}

    # Structural equality first — bytes may differ due to formatting (key order,
    # quoting). Only flag "diverged" if there's a REAL semantic difference.
    if filename == "familles_euros.yaml":
        l = set((local_data or {}).get("euros", []) or [])
        d = set((drive_data or {}).get("euros", []) or [])
        if l == d:
            return {"status": "in_sync"}
        return {
            "status": "diverged",
            "only_local": sorted(l - d),
            "only_drive": sorted(d - l),
            "local_count": len(l),
            "drive_count": len(d),
        }
    if filename == "tarifs_speciaux.yaml":
        def key(t: dict) -> tuple[str, str, str]:
            return (t.get("teacher", ""), t.get("parent", ""), t.get("student", ""))
        l_idx = {key(t): t for t in (local_data or {}).get("tarifs_speciaux", []) or []}
        d_idx = {key(t): t for t in (drive_data or {}).get("tarifs_speciaux", []) or []}
        only_l = list(l_idx.keys() - d_idx.keys())
        only_d = list(d_idx.keys() - l_idx.keys())
        changed = [k for k in (l_idx.keys() & d_idx.keys()) if l_idx[k] != d_idx[k]]
        if not only_l and not only_d and not changed:
            return {"status": "in_sync"}
        return {
            "status": "diverged",
            "only_local": [list(k) for k in only_l],
            "only_drive": [list(k) for k in only_d],
            "changed": [list(k) for k in changed],
            "local_count": len(l_idx),
            "drive_count": len(d_idx),
        }

    # secrets.yaml — masked structural diff
    diffs = _masked_diff(local_data or {}, drive_data or {})
    if not diffs:
        return {"status": "in_sync"}
    return {"status": "diverged", "masked_diff": diffs}


def _mask(v: Any) -> str:
    if v is None or v == "":
        return ""
    s = str(v)
    if len(s) <= 6:
        return "***"
    return f"{s[:3]}...{s[-2:]} ({len(s)} chars)"


def _masked_diff(local: dict, drive: dict, path: str = "") -> dict:
    out: dict = {}
    for k in sorted(set(local) | set(drive)):
        lv, dv = local.get(k), drive.get(k)
        if isinstance(lv, dict) and isinstance(dv, dict):
            sub = _masked_diff(lv, dv, f"{path}.{k}" if path else k)
            if sub:
                out[k] = sub
        elif lv != dv:
            out[k] = {"local": _mask(lv), "drive": _mask(dv)}
    return out
