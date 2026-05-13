from __future__ import annotations
from datetime import date
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services import sync as svc

router = APIRouter(prefix="/sync", tags=["sync"], dependencies=[Depends(require_api_key)])


class SyncBody(BaseModel):
    mode: str = "no-split"  # "no-split" or "normal"
    since_date: date | None = None


@router.post("/stripe-to-notion", status_code=202)
async def sync_stripe_notion(body: SyncBody, background: BackgroundTasks,
                             manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("sync")
    async def _job(ctx):
        return await svc.run_sync_job(
            mode=body.mode, since_date=body.since_date,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}
