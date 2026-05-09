"""Extract route — fire-and-poll endpoint for TutorBird extraction."""
from __future__ import annotations

from datetime import date, time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager
from app.services.extract import (
    get_last_summary,
    run_extract_job,
    save_summary,
)
from app.services.notion import fetch_profs_hors_tb

router = APIRouter(tags=["extract"], dependencies=[Depends(require_api_key)])


class ExtractRequest(BaseModel):
    start_date: date = Field(..., description="Inclusive start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="Inclusive end date (YYYY-MM-DD)")
    start_time: time = Field(default=time(0, 0), description="Lower time bound (HH:MM)")
    end_time: time = Field(default=time(23, 59), description="Upper time bound (HH:MM)")
    notion_prof_page_ids: list[str] | None = Field(
        default=None,
        description=(
            "If provided, fetch Notion 'Profs hors TutorBird' and merge only the "
            "selected pages into the extraction. None = skip Notion entirely. "
            "Empty list = fetch but include zero (no-op)."
        ),
    )


class ExtractResponse(BaseModel):
    job_id: str


@router.post("/extract", response_model=ExtractResponse, status_code=202)
async def start_extract(
    body: ExtractRequest,
    background: BackgroundTasks,
    manager: JobManager = Depends(get_job_manager),
) -> ExtractResponse:
    job_id = manager.create("extract")

    async def _job(ctx):
        summary = await run_extract_job(
            start_date=body.start_date,
            end_date=body.end_date,
            start_time=body.start_time,
            end_time=body.end_time,
            notion_prof_page_ids=body.notion_prof_page_ids,
            on_log=ctx.log,
            on_progress=ctx.progress,
        )
        save_summary(summary)
        return summary

    background.add_task(manager.run, job_id, _job)
    return ExtractResponse(job_id=job_id)


@router.get("/extract/last-summary")
async def last_summary() -> dict[str, Any]:
    summary = get_last_summary()
    if summary is None:
        raise HTTPException(status_code=404, detail="No extraction yet")
    return summary


@router.get("/notion/profs-hors-tb")
async def list_profs_hors_tb() -> dict[str, Any]:
    """Read-only listing for the Extract page selector."""
    return fetch_profs_hors_tb()
