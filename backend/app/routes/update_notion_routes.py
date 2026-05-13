from __future__ import annotations
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services import update_notion_svc as svc

router = APIRouter(prefix="/update-notion", tags=["update-notion"], dependencies=[Depends(require_api_key)])


class UpdateAllBody(BaseModel):
    no_split: bool = False
    invoice_date_override: str | None = None
    additional_amounts: dict[str, Any] | None = None


class UpdateSelectiveBody(BaseModel):
    invoice_folder_path: str
    selected_family_ids: list[str] | None = None
    selected_teachers: list[str] | None = None
    no_split: bool = False


class AddMissingBody(BaseModel):
    missing_rows: list[dict[str, Any]]


@router.post("/all", status_code=202)
async def update_all(body: UpdateAllBody, background: BackgroundTasks,
                     manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("update-notion-all")
    async def _job(ctx):
        return await svc.run_update_all_job(
            no_split=body.no_split,
            invoice_date_override=body.invoice_date_override,
            additional_amounts=body.additional_amounts,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}


@router.post("/selection", status_code=202)
async def update_selective(body: UpdateSelectiveBody, background: BackgroundTasks,
                           manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("update-notion-selection")
    async def _job(ctx):
        return await svc.run_update_selective_job(
            invoice_folder_path=body.invoice_folder_path,
            selected_family_ids=body.selected_family_ids,
            selected_teachers=body.selected_teachers,
            no_split=body.no_split,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}


@router.get("/scan-compare")
def scan_compare(folder_path: str = Query(...)) -> dict[str, Any]:
    return svc.scan_and_compare(folder_path)


@router.post("/add-missing", status_code=202)
async def add_missing(body: AddMissingBody, background: BackgroundTasks,
                      manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("update-notion-missing")
    async def _job(ctx):
        return await svc.run_add_missing_job(
            missing_rows=body.missing_rows,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}
