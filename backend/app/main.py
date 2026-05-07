from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routes import health, jobs

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


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "professor-plus-backend", "docs": "/docs"}
