from __future__ import annotations
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services import reminders as svc

router = APIRouter(prefix="/reminders", tags=["reminders"], dependencies=[Depends(require_api_key)])


class TemplatePair(BaseModel):
    subject: str | None = None
    body: str | None = None


class RemindersBody(BaseModel):
    folder: str
    templates: dict[str, TemplatePair] = {}
    selected_families: list[str] | None = None
    send_to_test: bool = False


@router.get("/unpaid")
def unpaid(folder: str = Query(...)) -> dict[str, Any]:
    return svc.unpaid_families(folder)


@router.get("/default-template")
def default_template() -> dict[str, str]:
    return svc.default_template()


@router.get("/auto-candidates")
def auto_candidates() -> dict[str, Any]:
    return svc.should_send_auto()


@router.post("/send", status_code=202)
async def send_reminders(body: RemindersBody, background: BackgroundTasks,
                         manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("reminders")
    async def _job(ctx):
        return await svc.run_send_reminders_job(
            folder_name=body.folder,
            templates={k: v.model_dump() for k, v in body.templates.items()},
            selected_families=body.selected_families,
            send_to_test=body.send_to_test,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}


@router.post("/test", status_code=202)
async def test_reminder(body: RemindersBody, background: BackgroundTasks,
                        manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    body.send_to_test = True
    return await send_reminders(body, background, manager)
