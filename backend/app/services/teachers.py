"""CRUD on the `teachers` section of secrets.yaml + Stripe Connect status."""
from __future__ import annotations

from typing import Any
from app.services.yaml_io import read_yaml, write_yaml


def _load_secrets() -> dict[str, Any]:
    return read_yaml("secrets.yaml")


def _save_secrets(secrets: dict[str, Any]) -> dict[str, Any]:
    return write_yaml("secrets.yaml", secrets)


def list_teachers() -> list[dict[str, Any]]:
    secrets = _load_secrets()
    teachers = secrets.get("teachers", {}) or {}
    out = []
    for name, cfg in teachers.items():
        cfg = cfg or {}
        pr = cfg.get("pay_rate", {}) or {}
        out.append(
            {
                "name": name,
                "connect_account_id": cfg.get("connect_account_id", ""),
                "pay_rate_chf": float(pr.get("chf", 0) or 0),
                "pay_rate_eur": float(pr.get("eur", 0) or 0),
                "auto_chf": bool(cfg.get("auto_chf", False)),
            }
        )
    return sorted(out, key=lambda t: t["name"].lower())


def create_teacher(name: str, *, connect_account_id: str = "", pay_rate_chf: float = 0,
                   pay_rate_eur: float = 0, auto_chf: bool = False) -> dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("Teacher name is required")
    name = name.strip()
    secrets = _load_secrets()
    teachers = secrets.setdefault("teachers", {})
    if name in teachers:
        raise ValueError(f"Teacher '{name}' already exists")
    teachers[name] = {
        "connect_account_id": connect_account_id,
        "pay_rate": {"chf": float(pay_rate_chf), "eur": float(pay_rate_eur)},
        "auto_chf": bool(auto_chf),
    }
    _save_secrets(secrets)
    return {"name": name, **teachers[name]}


def update_teacher(name: str, **fields) -> dict[str, Any]:
    secrets = _load_secrets()
    teachers = secrets.setdefault("teachers", {})
    if name not in teachers:
        raise KeyError(f"Teacher '{name}' not found")
    entry = teachers[name] or {}
    pr = entry.setdefault("pay_rate", {})
    if "connect_account_id" in fields:
        entry["connect_account_id"] = fields["connect_account_id"]
    if "pay_rate_chf" in fields:
        pr["chf"] = float(fields["pay_rate_chf"])
    if "pay_rate_eur" in fields:
        pr["eur"] = float(fields["pay_rate_eur"])
    if "auto_chf" in fields:
        entry["auto_chf"] = bool(fields["auto_chf"])
    teachers[name] = entry
    _save_secrets(secrets)
    return {"name": name, **entry}


def delete_teacher(name: str) -> None:
    secrets = _load_secrets()
    teachers = secrets.get("teachers", {})
    if name not in teachers:
        raise KeyError(f"Teacher '{name}' not found")
    teachers.pop(name)
    secrets["teachers"] = teachers
    _save_secrets(secrets)


def stripe_connect_status(name: str) -> dict[str, Any]:
    """Probe Stripe Connect for the teacher's account status."""
    secrets = _load_secrets()
    teacher = (secrets.get("teachers") or {}).get(name)
    if not teacher:
        raise KeyError(f"Teacher '{name}' not found")
    account_id = teacher.get("connect_account_id", "")
    if not account_id:
        return {"name": name, "account_id": "", "status": "unconfigured"}

    try:
        import stripe
    except ImportError:
        return {"name": name, "account_id": account_id, "status": "stripe_not_installed"}

    stripe_key = (secrets.get("stripe") or {}).get("platform_secret_key", "")
    if not stripe_key:
        return {"name": name, "account_id": account_id, "status": "no_stripe_key"}
    stripe.api_key = stripe_key
    try:
        acc = stripe.Account.retrieve(account_id)
        charges = bool(getattr(acc, "charges_enabled", False))
        payouts = bool(getattr(acc, "payouts_enabled", False))
        details_submitted = bool(getattr(acc, "details_submitted", False))
        if charges and payouts:
            status = "active"
        elif details_submitted:
            status = "pending"
        else:
            status = "incomplete"
        return {
            "name": name,
            "account_id": account_id,
            "status": status,
            "charges_enabled": charges,
            "payouts_enabled": payouts,
            "details_submitted": details_submitted,
        }
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "account_id": account_id, "status": "error", "error": str(exc)}
