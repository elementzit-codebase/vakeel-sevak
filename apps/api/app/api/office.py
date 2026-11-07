"""Minimal case, audit and settings endpoints. Feature 3 grows the case workspace."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import ROLES
from ..db import get_db
from ..models import AuditLog, Case, Hearing, User
from ..services.audit import audit
from .deps import Principal, office_of, require

router = APIRouter()


def case_card(c: Case) -> dict:
    return {
        "id": str(c.id),
        "title": c.title,
        "case_number": c.case_number,
        "court": c.court,
        "stage": c.stage,
    }


@router.get("/portal/cases")
def portal_cases(p: Principal = Depends(require("portal.read")), db: Session = Depends(get_db)):
    """What a signed-in client sees: own cases, status and next date only. No notes or other clients."""
    if not p.user.client_id:
        return {"items": []}
    cases = db.scalars(select(Case).where(Case.client_id == p.user.client_id).order_by(Case.title))
    out = []
    for c in cases:
        nxt = db.scalar(
            select(func.min(Hearing.hearing_at)).where(Hearing.case_id == c.id, Hearing.status == "scheduled")
        )
        out.append(
            {
                "id": str(c.id),
                "title": c.title,
                "case_number": c.case_number,
                "stage": c.stage,
                "next_hearing": nxt.isoformat() if nxt else None,
            }
        )
        audit(
            db,
            "portal.view",
            p.user,
            entity_type="case",
            entity_id=str(c.id),
            case_id=c.id,
            request=p.request,
        )
    db.commit()
    return {"items": out}


@router.get("/audit")
def audit_list(
    user_id: UUID | None = None,
    case_id: UUID | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    p: Principal = Depends(require("audit.read")),
    db: Session = Depends(get_db),
):
    q = select(AuditLog).where(AuditLog.office_id == p.user.office_id)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if case_id:
        q = q.where(AuditLog.case_id == case_id)
    if action:
        q = q.where(AuditLog.action.like(action.replace("*", "%")))
    if since:
        q = q.where(AuditLog.at >= since)
    if until:
        q = q.where(AuditLog.at <= until)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(AuditLog.at.desc()).limit(min(limit, 200)).offset(offset))
    names = {u.id: u.name for u in db.scalars(select(User).where(User.office_id == p.user.office_id))}
    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "at": r.at.isoformat(),
                "user_id": str(r.user_id) if r.user_id else None,
                "user_name": names.get(r.user_id),
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "case_id": str(r.case_id) if r.case_id else None,
                "detail": r.detail,
            }
            for r in rows
        ],
    }


class MfaRolesIn(BaseModel):
    roles: list[str]


@router.get("/settings/security")
def security_settings(p: Principal = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    return {"mfa_roles": office_of(db, p.user).mfa_roles or []}


@router.put("/settings/security/mfa-roles")
def set_mfa_roles(
    body: MfaRolesIn,
    p: Principal = Depends(require("settings.manage")),
    db: Session = Depends(get_db),
):
    bad = [r for r in body.roles if r not in ROLES]
    if bad:
        raise HTTPException(422, f"Unknown roles: {', '.join(bad)}")
    office = office_of(db, p.user)
    before = list(office.mfa_roles or [])
    office.mfa_roles = sorted(set(body.roles))
    audit(
        db,
        "settings.mfa_roles_changed",
        p.user,
        entity_type="office",
        entity_id=str(office.id),
        detail={"before": before, "after": office.mfa_roles},
        request=p.request,
    )
    db.commit()
    return {"mfa_roles": office.mfa_roles}
