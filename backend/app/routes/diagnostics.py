"""Diagnostics — config-sync (Drive vs local) + phantom-teachers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.services import diagnostics as svc

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"], dependencies=[Depends(require_api_key)])


@router.get("/config-sync")
def config_sync() -> dict[str, Any]:
    return svc.config_sync_report()


@router.get("/phantom-teachers")
def phantom_teachers() -> dict[str, Any]:
    return svc.phantom_teachers_report()
