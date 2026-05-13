"""CRUD on tarifs_speciaux.yaml — list of {teacher, parent, pay_rate, currency}."""
from __future__ import annotations

import hashlib
from typing import Any

from app.services.yaml_io import read_yaml, write_yaml

_FILENAME = "tarifs_speciaux.yaml"


def _make_id(teacher: str, parent: str, student: str = "") -> str:
    h = hashlib.sha1(f"{teacher.lower()}|{parent.lower()}|{student.lower()}".encode()).hexdigest()[:10]
    return h


def list_rates() -> list[dict[str, Any]]:
    data = read_yaml(_FILENAME)
    items = data.get("tarifs_speciaux") or []
    out = []
    for it in items:
        teacher = it.get("teacher", "")
        parent = it.get("parent", "")
        student = it.get("student", "")
        out.append(
            {
                "id": _make_id(teacher, parent, student),
                "teacher": teacher,
                "parent": parent,
                "student": student,
                "pay_rate": float(it.get("pay_rate", 0) or 0),
                "currency": (it.get("currency") or "EUR").upper(),
            }
        )
    return out


def add_rate(*, teacher: str, parent: str, pay_rate: float,
             currency: str = "EUR", student: str = "") -> dict[str, Any]:
    teacher = (teacher or "").strip()
    parent = (parent or "").strip()
    if not teacher or not parent:
        raise ValueError("Teacher and parent are required")
    data = read_yaml(_FILENAME)
    items = list(data.get("tarifs_speciaux") or [])
    new_entry = {
        "teacher": teacher,
        "parent": parent,
        "pay_rate": float(pay_rate),
        "currency": currency.upper(),
    }
    if student:
        new_entry["student"] = student.strip()
    new_id = _make_id(teacher, parent, student)
    # Check duplicate
    for it in items:
        if _make_id(it.get("teacher", ""), it.get("parent", ""), it.get("student", "")) == new_id:
            raise ValueError("This (teacher, parent, student) combo already has a special rate")
    items.append(new_entry)
    data["tarifs_speciaux"] = items
    write_yaml(_FILENAME, data)
    return {"id": new_id, **new_entry}


def remove_rate(rate_id: str) -> int:
    data = read_yaml(_FILENAME)
    items = list(data.get("tarifs_speciaux") or [])
    before = len(items)
    items = [
        it for it in items
        if _make_id(it.get("teacher", ""), it.get("parent", ""), it.get("student", "")) != rate_id
    ]
    if len(items) == before:
        raise KeyError(f"Rate '{rate_id}' not found")
    data["tarifs_speciaux"] = items
    write_yaml(_FILENAME, data)
    return before - len(items)
