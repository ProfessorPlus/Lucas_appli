"""Payment Links endpoints — fire-and-poll job + helpers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services import payment_links as svc

router = APIRouter(tags=["payment-links"], dependencies=[Depends(require_api_key)])


class CreateLinksBody(BaseModel):
    no_split: bool = False
    selected_teachers: list[str] | None = Field(
        default=None,
        description="Teacher names to use as on_behalf_of (split mode only). Empty/None = no on-behalf.",
    )
    payment_method_types: list[str] | None = None
    target_family_ids: list[str] | None = Field(
        default=None,
        description="Families to (re)generate. None = all extracted families.",
    )
    additional_amounts: dict[str, Any] | None = Field(
        default=None,
        description="n-2 unpaid amounts to bundle: {family_id: {amount, hours, dates}}.",
    )
    skip_if_exists: bool = True


@router.post("/payment-links/create", status_code=202)
async def create_links(
    body: CreateLinksBody,
    background: BackgroundTasks,
    manager: JobManager = Depends(get_job_manager),
) -> dict[str, str]:
    job_id = manager.create("payment-links")

    async def _job(ctx):
        return await svc.run_create_links_job(
            no_split=body.no_split,
            selected_teachers=body.selected_teachers,
            payment_method_types=body.payment_method_types,
            target_family_ids=body.target_family_ids,
            additional_amounts=body.additional_amounts,
            skip_if_exists=body.skip_if_exists,
            on_log=ctx.log,
            on_progress=ctx.progress,
        )

    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}


@router.get("/payment-links/list")
def list_links() -> dict[str, Any]:
    return svc.list_existing_links()


@router.get("/payment-links/unpaid-detect")
def unpaid_detect(year: int = Query(...), month: int = Query(..., ge=1, le=12)) -> dict[str, Any]:
    return svc.detect_unpaid_n2(year, month)


@router.get("/payment-links/families")
def extracted_families() -> list[dict[str, Any]]:
    """For the regenerate tab — current families in the extract."""
    return svc.get_extracted_families()


@router.get("/teachers/stripe-status")
def teachers_stripe_status() -> list[dict[str, Any]]:
    return svc.teachers_stripe_status()
