"""All Settings page endpoints (5 tabs)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.services import teachers as svc_teachers
from app.services import families_eur as svc_fe
from app.services import special_rates as svc_sr
from app.services import email as svc_email
from app.services import drive_test as svc_drive

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_api_key)])


# ─── Teachers ───────────────────────────────────────────────────────────

class TeacherIn(BaseModel):
    name: str
    connect_account_id: str = ""
    pay_rate_chf: float = 0
    pay_rate_eur: float = 0
    auto_chf: bool = False


class TeacherUpdate(BaseModel):
    connect_account_id: str | None = None
    pay_rate_chf: float | None = None
    pay_rate_eur: float | None = None
    auto_chf: bool | None = None


@router.get("/teachers")
def list_teachers() -> list[dict[str, Any]]:
    return svc_teachers.list_teachers()


@router.post("/teachers", status_code=201)
def create_teacher(body: TeacherIn) -> dict[str, Any]:
    try:
        return svc_teachers.create_teacher(
            body.name,
            connect_account_id=body.connect_account_id,
            pay_rate_chf=body.pay_rate_chf,
            pay_rate_eur=body.pay_rate_eur,
            auto_chf=body.auto_chf,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.patch("/teachers/{name}")
def update_teacher(name: str, body: TeacherUpdate) -> dict[str, Any]:
    try:
        return svc_teachers.update_teacher(name, **body.model_dump(exclude_none=True))
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.delete("/teachers/{name}", status_code=204)
def delete_teacher(name: str) -> None:
    try:
        svc_teachers.delete_teacher(name)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.get("/teachers/{name}/stripe-status")
def teacher_stripe_status(name: str) -> dict[str, Any]:
    try:
        return svc_teachers.stripe_connect_status(name)
    except KeyError as e:
        raise HTTPException(404, str(e))


# ─── Familles EUR ──────────────────────────────────────────────────────

class FamilyIn(BaseModel):
    name: str = Field(..., min_length=1)


@router.get("/families-eur")
def list_families_eur() -> list[str]:
    return svc_fe.list_families()


@router.post("/families-eur", status_code=201)
def create_family_eur(body: FamilyIn) -> list[str]:
    try:
        return svc_fe.add_family(body.name)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/families-eur/{name}", status_code=200)
def delete_family_eur(name: str) -> list[str]:
    try:
        return svc_fe.remove_family(name)
    except KeyError as e:
        raise HTTPException(404, str(e))


# ─── Tarifs spéciaux ───────────────────────────────────────────────────

class SpecialRateIn(BaseModel):
    teacher: str
    parent: str
    pay_rate: float
    currency: str = "EUR"
    student: str = ""


@router.get("/special-rates")
def list_special_rates() -> list[dict[str, Any]]:
    return svc_sr.list_rates()


@router.post("/special-rates", status_code=201)
def create_special_rate(body: SpecialRateIn) -> dict[str, Any]:
    try:
        return svc_sr.add_rate(
            teacher=body.teacher,
            parent=body.parent,
            pay_rate=body.pay_rate,
            currency=body.currency,
            student=body.student,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/special-rates/{rate_id}", status_code=200)
def delete_special_rate(rate_id: str) -> dict[str, int]:
    try:
        deleted = svc_sr.remove_rate(rate_id)
        return {"deleted": deleted}
    except KeyError as e:
        raise HTTPException(404, str(e))


# ─── Email (Gmail) ─────────────────────────────────────────────────────

class EmailUpdate(BaseModel):
    email: str
    app_password: str | None = None


@router.get("/email")
def get_email() -> dict[str, Any]:
    return svc_email.get_email_config()


@router.put("/email")
def update_email(body: EmailUpdate) -> dict[str, Any]:
    return svc_email.set_email_config(email=body.email, app_password=body.app_password)


class EmailTest(BaseModel):
    to: str | None = None


@router.post("/email/test")
def email_test(body: EmailTest = EmailTest()) -> dict[str, Any]:
    try:
        return svc_email.send_test(to=body.to)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, str(exc))


# ─── Drive tests ───────────────────────────────────────────────────────

@router.get("/drive/test")
def drive_read_test() -> dict[str, Any]:
    return svc_drive.drive_test()


@router.post("/drive/write-test")
def drive_write_test() -> dict[str, Any]:
    return svc_drive.drive_write_test()
