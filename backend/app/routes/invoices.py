from __future__ import annotations
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services import invoices as svc

router = APIRouter(prefix="/invoices", tags=["invoices"], dependencies=[Depends(require_api_key)])


class GenerateBody(BaseModel):
    target_folder_path: str | None = None
    force_new_folder: bool = False
    previous_unpaid_data: dict[str, Any] | None = None
    previous_month_label: str | None = None


@router.post("/generate", status_code=202)
async def generate(body: GenerateBody, background: BackgroundTasks,
                   manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("invoices")
    async def _job(ctx):
        return await svc.run_generate_job(
            target_folder_path=body.target_folder_path,
            force_new_folder=body.force_new_folder,
            previous_unpaid_data=body.previous_unpaid_data,
            previous_month_label=body.previous_month_label,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}


@router.get("/unpaid-detect")
def unpaid(year: int = Query(...), month: int = Query(..., ge=1, le=12)) -> dict[str, Any]:
    return svc.detect_unpaid_n2(year, month)
