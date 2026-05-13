from __future__ import annotations
from datetime import date
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services import cleanup as svc

router = APIRouter(prefix="/cleanup", tags=["cleanup"], dependencies=[Depends(require_api_key)])


class DeleteOldBody(BaseModel):
    keep_from_date: date
    dry_run: bool = True


class DuplicatesBody(BaseModel):
    dry_run: bool = True


@router.get("/scan-dates")
async def scan_dates() -> dict[str, Any]:
    return await svc.scan_dates()


@router.post("/delete-old", status_code=202)
async def delete_old(body: DeleteOldBody, background: BackgroundTasks,
                     manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("cleanup-delete-old")
    async def _job(ctx):
        return await svc.run_delete_old_job(
            keep_from_date=body.keep_from_date, dry_run=body.dry_run,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}


@router.post("/duplicates", status_code=202)
async def cleanup_duplicates(body: DuplicatesBody, background: BackgroundTasks,
                             manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("cleanup-duplicates")
    async def _job(ctx):
        return await svc.run_cleanup_duplicates_job(
            dry_run=body.dry_run,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}
