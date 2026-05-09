"""Path helpers — locate the project root and the legacy `scripts/` directory.

Backend is at <root>/backend/app, scripts at <root>/scripts. We add <root> to
sys.path so we can `from scripts.extract_tutorbird import ...` without copying.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_INVOICES_DIR = PROJECT_ROOT / "Factures"


def ensure_scripts_on_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def get_data_dir() -> Path:
    raw = os.getenv("PROFPLUS_DATA_DIR")
    path = Path(raw) if raw else DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_invoices_dir() -> Path:
    raw = os.getenv("PROFPLUS_INVOICES_DIR")
    path = Path(raw) if raw else DEFAULT_INVOICES_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path
