"""CRUD on familles_euros.yaml — a flat list of parent names."""
from __future__ import annotations

from app.services.yaml_io import read_yaml, write_yaml


_FILENAME = "familles_euros.yaml"


def list_families() -> list[str]:
    data = read_yaml(_FILENAME)
    return sorted((data.get("euros") or []), key=str.lower)


def add_family(name: str) -> list[str]:
    name = name.strip()
    if not name:
        raise ValueError("Family name is required")
    data = read_yaml(_FILENAME)
    euros = list(data.get("euros") or [])
    if name in euros:
        raise ValueError(f"'{name}' already in the EUR families list")
    euros.append(name)
    data["euros"] = euros
    write_yaml(_FILENAME, data)
    return sorted(euros, key=str.lower)


def remove_family(name: str) -> list[str]:
    data = read_yaml(_FILENAME)
    euros = list(data.get("euros") or [])
    if name not in euros:
        raise KeyError(f"'{name}' not found")
    euros = [e for e in euros if e != name]
    data["euros"] = euros
    write_yaml(_FILENAME, data)
    return sorted(euros, key=str.lower)
