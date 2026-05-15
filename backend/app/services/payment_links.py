"""Payment Links — wraps create_payment_links{,_no_split} as a fire-and-poll
job + utilities (n-2 unpaid detection, list existing, batch Stripe status).

Respects MIGRATION_SPEC critical behaviors:
- C. additional_amounts is {family_id: {amount, hours, dates}}
- D. Stripe SDK v15 — never dict(metadata), use .to_dict()
- AED currency support (handled inside the legacy scripts)
- Deactivation of previous links when regenerating
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable

from starlette.concurrency import run_in_threadpool

from app.services.config import (
    load_familles_euros,
    load_secrets,
    load_secrets_no_prof,
    load_tarifs_speciaux,
)
from app.services.paths import ensure_scripts_on_path, get_data_dir

ensure_scripts_on_path()


def _load_extracted_data() -> dict[str, Any]:
    path = get_data_dir() / "full_output_tb_SIMPLE.json"
    if not path.exists():
        raise RuntimeError("Pas de données extraites — lance d'abord une extraction.")
    return json.loads(path.read_text(encoding="utf-8"))


async def run_create_links_job(
    *,
    no_split: bool,
    selected_teachers: list[str] | None,
    payment_method_types: list[str] | None,
    target_family_ids: list[str] | None,
    additional_amounts: dict[str, Any] | None,
    skip_if_exists: bool,
    on_log: Callable[[str], None],
    on_progress: Callable[[float], None],
) -> dict[str, Any]:
    """Run the appropriate create-links script in a threadpool, with the
    legacy script's (progress: int 0..100, message: str) callback bridged to
    our JobContext.
    """

    on_log("📂 Chargement des données extraites + configs…")
    data = _load_extracted_data()
    familles_euros = load_familles_euros()
    on_log(f"  ✓ {len(data)} familles · {len(familles_euros)} familles EUR")

    def cb(progress: int, message: str) -> None:
        on_progress(max(0.0, min(progress / 100.0, 1.0)))
        if message:
            on_log(message)

    if no_split:
        on_log("💸 Mode NO-SPLIT — tout encaisse sur le compte principal")
        secrets_no_prof = load_secrets_no_prof()
        if not secrets_no_prof:
            raise RuntimeError("secrets_no_prof manquant — vérifie secrets.yaml.stripe_no_split")

        from scripts.create_payment_links_no_split import run_create_payment_links_no_split
        result = await run_in_threadpool(
            run_create_payment_links_no_split,
            data,
            secrets_no_prof,
            familles_euros,
            str(get_data_dir()),
            cb,
            payment_method_types,
            target_family_ids,
            skip_if_exists,
            additional_amounts,
        )
    else:
        on_log("💳 Mode SPLIT — transferts vers comptes Stripe Connect des profs")
        secrets = load_secrets()
        tarifs_speciaux = load_tarifs_speciaux()
        on_log(f"  ✓ {len(tarifs_speciaux)} tarifs spéciaux chargés")

        from scripts.create_payment_links import run_create_payment_links
        use_on_behalf = bool(selected_teachers)
        result = await run_in_threadpool(
            run_create_payment_links,
            data,
            secrets,
            familles_euros,
            tarifs_speciaux,
            use_on_behalf,
            selected_teachers or [],
            str(get_data_dir()),
            cb,
            payment_method_types,
            target_family_ids,
            skip_if_exists,
            additional_amounts,
        )

    if not result or not result.get("success", True):
        # Some scripts return success-less dicts; check explicitly.
        if result and result.get("error"):
            raise RuntimeError(result.get("error"))

    on_progress(1.0)
    on_log("✅ Génération des liens terminée")
    return result


# ── Utilities ──────────────────────────────────────────────────────────


def detect_unpaid_n2(year: int, month: int) -> dict[str, Any]:
    """List unpaid families from the target month (n-2) — Notion query."""
    from scripts.fetch_unpaid_notion import fetch_unpaid_n2

    secrets = load_secrets()
    return fetch_unpaid_n2(secrets, year, month)


def list_existing_links() -> dict[str, Any]:
    """Read the latest payment_links_output.json (source of truth for
    invoices/send/sync). Local cache; will fall back to Drive if missing."""
    path = get_data_dir() / "payment_links_output.json"
    if not path.exists():
        # Try Drive via storage_manager
        try:
            from scripts.storage_manager import load_json
            data = load_json("payment_links_output.json", "data", default=None)
            if data:
                return {"exists": True, "source": "drive", "links": data, "count": len(data)}
        except Exception:
            pass
        return {"exists": False, "links": [], "count": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"exists": True, "source": "local", "links": data, "count": len(data)}


def teachers_stripe_status() -> list[dict[str, Any]]:
    """Batch — return Stripe Connect status for every teacher who has a
    connect_account_id configured."""
    secrets = load_secrets()
    teachers = secrets.get("teachers", {}) or {}
    stripe_key = (secrets.get("stripe") or {}).get("platform_secret_key", "")

    out: list[dict[str, Any]] = []
    if not stripe_key:
        for name in sorted(teachers.keys()):
            out.append({"name": name, "status": "no_stripe_key"})
        return out

    try:
        import stripe
    except ImportError:
        for name in sorted(teachers.keys()):
            out.append({"name": name, "status": "stripe_not_installed"})
        return out

    stripe.api_key = stripe_key
    for name, cfg in sorted(teachers.items(), key=lambda x: x[0].lower()):
        cfg = cfg or {}
        account_id = cfg.get("connect_account_id", "")
        if not account_id:
            out.append({"name": name, "account_id": "", "status": "unconfigured"})
            continue
        try:
            acc = stripe.Account.retrieve(account_id)
            charges = bool(getattr(acc, "charges_enabled", False))
            payouts = bool(getattr(acc, "payouts_enabled", False))
            submitted = bool(getattr(acc, "details_submitted", False))
            status = "active" if (charges and payouts) else ("pending" if submitted else "incomplete")
            out.append({
                "name": name,
                "account_id": account_id,
                "status": status,
                "charges_enabled": charges,
                "payouts_enabled": payouts,
                "details_submitted": submitted,
            })
        except Exception as exc:  # noqa: BLE001
            out.append({"name": name, "account_id": account_id, "status": "error", "error": str(exc)})
    return out


def _effective_currency_for_family(fam: dict[str, Any], euro_parents_normalized: set[str]) -> str:
    """Same rule as page_accueil/extract: if any Notion-sourced lesson has a
    devise_client, that wins; else family.currency if set; else EUR if the
    parent is in familles_euros.yaml; else CHF default."""
    from scripts.update_notion import normalize_name

    # 1) Notion lessons carry per-lesson currencies — pick the dominant one
    notion_currencies: dict[str, int] = {}
    for L in fam.get("lessons", []) or []:
        if L.get("source") == "notion_hors_tb":
            c = (L.get("notion_devise_client") or "").upper()
            if c:
                notion_currencies[c] = notion_currencies.get(c, 0) + 1
    if notion_currencies:
        return max(notion_currencies.items(), key=lambda x: x[1])[0]

    # 2) Family-level explicit currency
    famcur = (fam.get("currency") or "").upper()
    if famcur:
        return famcur

    # 3) familles_euros.yaml override
    parent = fam.get("parent_name") or fam.get("family_name") or ""
    if normalize_name(parent) in euro_parents_normalized:
        return "EUR"

    # 4) Default
    return "CHF"


def get_extracted_families() -> list[dict[str, Any]]:
    """For the regenerate / selection tabs — return families currently in the
    extract with the EFFECTIVE currency (never empty)."""
    from scripts.update_notion import normalize_name

    try:
        data = _load_extracted_data()
    except RuntimeError:
        return []

    fe = load_familles_euros()
    euro_norm = {normalize_name(n) for n in fe}

    out = []
    for fam_id, fam in data.items():
        lessons = [L for L in (fam.get("lessons") or []) if L.get("attendance_status") != "AbsentNotice"]
        amount = sum(float(L.get("amount") or 0) for L in lessons)
        out.append({
            "family_id": fam_id,
            "parent_name": fam.get("parent_name") or fam.get("family_name") or fam_id,
            "currency": _effective_currency_for_family(fam, euro_norm),
            "currency_source": (
                "notion" if fam.get("source") == "notion_hors_tb"
                else "family.currency" if (fam.get("currency") or "")
                else "familles_euros.yaml" if normalize_name(fam.get("parent_name") or "") in euro_norm
                else "default-CHF"
            ),
            "lessons": len(lessons),
            "amount": round(amount, 2),
        })
    return sorted(out, key=lambda f: f["parent_name"].lower())
