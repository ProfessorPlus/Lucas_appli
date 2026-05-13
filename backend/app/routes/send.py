from __future__ import annotations
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services import send as svc

router = APIRouter(prefix="/send", tags=["send"], dependencies=[Depends(require_api_key)])


class TemplatePair(BaseModel):
    subject: str | None = None
    body: str | None = None


class SendBody(BaseModel):
    folder: str
    templates: dict[str, TemplatePair] = {}
    selected_families: list[str] | None = None
    send_to_test: bool = False


@router.get("/diagnostic")
def diagnostic(folder: str = Query(...)) -> dict[str, Any]:
    return svc.diagnostic(folder)


@router.get("/preview")
def preview(folder: str = Query(...)) -> dict[str, list[str]]:
    return svc.preview_per_template(folder)


@router.get("/default-templates")
def default_templates(month: str | None = None, year: int | None = None) -> dict[str, Any]:
    return svc.default_templates(month, year)


@router.post("/test", status_code=202)
async def send_test(body: SendBody, background: BackgroundTasks,
                    manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("send-test")
    body.send_to_test = True
    async def _job(ctx):
        return await svc.run_send_job(
            folder_name=body.folder,
            templates={k: v.model_dump() for k, v in body.templates.items()},
            selected_families=body.selected_families,
            send_to_test=True,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}


@router.post("/invoices", status_code=202)
async def send_invoices(body: SendBody, background: BackgroundTasks,
                        manager: JobManager = Depends(get_job_manager)) -> dict[str, str]:
    job_id = manager.create("send-invoices")
    async def _job(ctx):
        return await svc.run_send_job(
            folder_name=body.folder,
            templates={k: v.model_dump() for k, v in body.templates.items()},
            selected_families=body.selected_families,
            send_to_test=body.send_to_test,
            on_log=ctx.log, on_progress=ctx.progress,
        )
    background.add_task(manager.run, job_id, _job)
    return {"job_id": job_id}
