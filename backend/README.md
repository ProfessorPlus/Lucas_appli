# Professor+ Backend (FastAPI)

API backend for the Next.js admin dashboard. Wraps the existing Python scripts
in `../scripts/` as services.

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # Mac/Linux
pip install -r requirements.txt
cp .env.example .env             # then fill in your secrets
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## Auth

All endpoints require header `X-API-Key: <value of API_KEY in .env>`.

## Long-running jobs

`POST /api/extract` (and similar) return `{job_id}`.
- `GET /api/jobs/{job_id}` to poll
- `GET /api/jobs/{job_id}/stream` for SSE log streaming

Jobs are persisted to SQLite (`jobs.db`) so they survive a server restart.
