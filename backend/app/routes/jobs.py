import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.auth import require_api_key
from app.jobs import JobManager, get_job_manager

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])


@router.get("/{job_id}")
async def get_job(job_id: str, manager: JobManager = Depends(get_job_manager)) -> dict:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/stream")
async def stream_job(
    job_id: str,
    request: Request,
    manager: JobManager = Depends(get_job_manager),
):
    if manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    queue = manager.subscribe(job_id)

    async def event_source():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"data": payload}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "keep-alive"}
        finally:
            manager.unsubscribe(job_id, queue)

    return EventSourceResponse(event_source())
