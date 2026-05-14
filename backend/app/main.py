import asyncio
import sys

# Force UTF-8 on stdout/stderr — Windows defaults to cp1252 which raises
# UnicodeEncodeError on the emojis used in the legacy scripts/ logs (✅ ⚠️ ❌)
# and crashes endpoints with HTTP 500. Must run before any module that may print.
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # pragma: no cover
            pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.jobs import get_job_manager
from app.routes import (
    cleanup,
    dashboard,
    diagnostics,
    edit_invoice,
    extract,
    health,
    invoices,
    jobs,
    payment_links,
    payroll,
    reminders,
    send,
    sync,
)
from app.routes import settings as settings_routes
from app.routes import update_notion_routes
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
app.include_router(settings_routes.router, prefix="/api")
app.include_router(diagnostics.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(payment_links.router, prefix="/api")
app.include_router(invoices.router, prefix="/api")
app.include_router(send.router, prefix="/api")
app.include_router(reminders.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(update_notion_routes.router, prefix="/api")
app.include_router(cleanup.router, prefix="/api")
app.include_router(payroll.router, prefix="/api")
app.include_router(edit_invoice.router, prefix="/api")


@app.on_event("startup")
async def _capture_loop() -> None:
    # Required so SSE notifications are dispatched safely from threadpool callbacks.
    get_job_manager().set_loop(asyncio.get_running_loop())


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "professor-plus-backend", "docs": "/docs"}
