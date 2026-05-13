from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response

from app.auth import require_api_key
from app.services import payroll as svc

router = APIRouter(prefix="/payroll", tags=["payroll"], dependencies=[Depends(require_api_key)])


@router.get("/summary")
def summary(auto_chf_target: float | None = Query(None)) -> dict[str, Any]:
    return svc.summary(auto_chf_target=auto_chf_target)


@router.get("/teacher/{name}/pdf")
def teacher_pdf(name: str, mois: str | None = Query(None)) -> Response:
    try:
        b = svc.pdf_for_teacher(name, mois_label=mois)
        return Response(
            content=b, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="recap_{name}.pdf"'},
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/zip")
def zip_pdfs(mois: str | None = Query(None)) -> Response:
    try:
        b = svc.zip_all_pdfs(mois_label=mois)
        return Response(
            content=b, media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="recap_profs.zip"'},
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.get("/combined-pdf")
def combined_pdf(mois: str | None = Query(None)) -> Response:
    try:
        b = svc.combined_pdf(mois_label=mois)
        return Response(
            content=b, media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="recap_profs_combined.pdf"'},
        )
    except Exception as exc:
        raise HTTPException(500, str(exc))
