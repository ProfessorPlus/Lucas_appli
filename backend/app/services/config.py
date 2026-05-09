"""Thin wrapper over the legacy `scripts/config_loader` module."""
from __future__ import annotations

from typing import Any

from app.services.paths import ensure_scripts_on_path

ensure_scripts_on_path()


def load_secrets(force_reload: bool = False) -> dict[str, Any]:
    from scripts.config_loader import load_secrets as _ls
    return _ls(force_reload=force_reload) or {}


def load_secrets_no_prof(force_reload: bool = False) -> dict[str, Any]:
    from scripts.config_loader import load_secrets_no_prof as _ls
    return _ls(force_reload=force_reload) or {}


def load_familles_euros() -> list[str]:
    """Read familles_euros.yaml — same logic as Streamlit's app.py."""
    import os
    import yaml
    from app.services.paths import PROJECT_ROOT

    candidates = [
        PROJECT_ROOT / "config" / "familles_euros.yaml",
        PROJECT_ROOT / "familles_euros.yaml",
    ]
    for path in candidates:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return list(data.get("euros", []))
    return []


def load_tarifs_speciaux() -> list[dict[str, Any]]:
    import yaml
    from app.services.paths import PROJECT_ROOT

    candidates = [
        PROJECT_ROOT / "config" / "tarifs_speciaux.yaml",
        PROJECT_ROOT / "tarifs_speciaux.yaml",
    ]
    for path in candidates:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return list(data.get("tarifs_speciaux", []))
    return []
