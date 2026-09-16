from __future__ import annotations
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services import twint as svc

router = APIRouter(prefix="/twint", tags=["twint"], dependencies=[Depends(require_api_key)])


class ActivateBody(BaseModel):
    account_ids: list[str]


@router.get("/status")
async def status() -> dict[str, Any]:
    return await svc.status()


@router.get("/accounts")
def accounts() -> list[dict[str, str]]:
    return svc.connect_accounts()


@router.post("/activate", status_code=202)
async def activate(body: ActivateBody, background: BackgroundTasks,
                   manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("twint-activate")
    async def _job(ctx):
        return await svc.run_activate_job(
            account_ids=body.account_ids,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}
