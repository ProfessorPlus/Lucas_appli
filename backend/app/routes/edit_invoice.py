"""Invoice editor endpoints."""
from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth import require_api_key
from app.services import edit_invoice as svc

router = APIRouter(prefix="/edit", tags=["edit-invoice"], dependencies=[Depends(require_api_key)])


@router.get("/folders/{folder_name}/families")
def families(folder_name: str) -> dict[str, Any]:
    return svc.list_families(folder_name)


@router.get("/folders/{folder_name}/family/{family}/pdfs")
def pdfs(folder_name: str, family: str) -> list[str]:
    return svc.list_pdfs(folder_name, family)


class LoadBody(BaseModel):
    folder: str
    family: str
    pdf_filename: str


@router.post("/load")
def load(body: LoadBody) -> dict[str, Any]:
    try:
        return svc.load_invoice(body.folder, body.family, body.pdf_filename)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.get("/empty-fields")
def empty_fields() -> dict[str, Any]:
    return svc.empty_fields()


class RenderBody(BaseModel):
    fields: dict[str, Any]


@router.post("/render")
def render(body: RenderBody) -> Response:
    try:
        pdf = svc.render_pdf(body.fields)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=edited.pdf"})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc))


class SendBody(BaseModel):
    fields: dict[str, Any]
    pdf_base64: str


@router.post("/send-email")
def send_email(body: SendBody) -> dict[str, Any]:
    try:
        pdf_bytes = base64.b64decode(body.pdf_base64)
        return svc.send_pdf_email(fields=body.fields, pdf_bytes=pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc))


class SaveBody(BaseModel):
    pdf_base64: str
    origin_drive_folder_id: str
    family_subfolder: str
    pdf_filename: str


@router.post("/save-to-drive")
def save_to_drive(body: SaveBody) -> dict[str, Any]:
    try:
        pdf_bytes = base64.b64decode(body.pdf_base64)
        return svc.save_to_drive(
            pdf_bytes=pdf_bytes,
            origin_drive_folder_id=body.origin_drive_folder_id,
            family_subfolder=body.family_subfolder,
            pdf_filename=body.pdf_filename,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc))
