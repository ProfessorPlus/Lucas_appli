import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.jobs import get_job_manager
from app.routes import extract, health, jobs
from app.services.paths import ensure_scripts_on_path

# Make the legacy scripts/ package importable from anywhere in this app.
ensure_scripts_on_path()

app = FastAPI(
    title="Professor+ Backend",
    description="API backend for the Next.js admin dashboard",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(extract.router, prefix="/api")


@app.on_event("startup")
async def _capture_loop() -> None:
    # Required so SSE notifications are dispatched safely from threadpool callbacks.
    get_job_manager().set_loop(asyncio.get_running_loop())


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "professor-plus-backend", "docs": "/docs"}
