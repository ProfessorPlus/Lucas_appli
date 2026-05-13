"""Dashboard endpoints — feed the home page cards."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.auth import require_api_key
from app.services import dashboard as svc

router = APIRouter(tags=["dashboard"], dependencies=[Depends(require_api_key)])


@router.get("/dashboard/summary")
def dashboard_summary() -> dict[str, Any]:
    return svc.summary()


@router.get("/invoice-folders")
def invoice_folders() -> list[dict[str, Any]]:
    return svc.list_invoice_folders()


@router.get("/dashboard/payments")
def dashboard_payments(folder: str = Query(..., description="Folder month, e.g. 'Octobre 2025 - 28-10'")) -> dict[str, Any]:
    return svc.payments_for_folder(folder)


@router.get("/dashboard/emails")
def dashboard_emails() -> dict[str, Any]:
    return svc.email_history()


@router.get("/quotes/random")
def quotes_random() -> dict[str, Any]:
    return svc.random_quotes()
