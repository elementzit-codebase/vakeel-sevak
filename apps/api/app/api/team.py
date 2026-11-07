"""Feature 2: user management, case assignments, firm settings."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ROLES, get_settings
from ..db import get_db
from ..models import AuthSession, CaseAssignment, Client, PasswordReset, User
from ..permissions import get_visible_case
from ..services import mailer
from ..services.audit import audit
from ..services.firm import get_firm, set_firm
from ..services.security import digest, hash_password, random_token, utcnow
from .deps import Principal, current, office_of, require

router = APIRouter()


def user_out(u: User) -> dict:
    return {
        "id": str(u.id),
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "language": u.language,
        "is_active": u.is_active,
        "totp_enabled": u.totp_enabled,
        "client_id": str(u.client_id) if u.client_id else None,
    }


def _invite(db: Session, user: User) -> None:
    token = random_token()
    db.add(PasswordReset(user_id=user.id, token_hash=digest(token), expires_at=utcnow() + timedelta(days=3)))
    db.flush()
    name = get_settings().product_name
    mailer.send(user.email, f"You have been added to {name}", f"Set your password (valid 3 days): /reset?token={token}")


def _active_directors(db: Session, office_id) -> int:
    return len(
        list(db.scalars(select(User.id).where(User.office_id == office_id, User.role == "director", User.is_active)))
    )


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    role: str
    language: str = "en"
    client_id: UUID | None = None


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    language: str | None = None
    is_active: bool | None = None


@router.get("/users")
def list_users(p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.office_id == p.user.office_id).order_by(User.name))
    return {"items": [user_out(u) for u in rows]}


@router.get("/team")
def team_directory(p: Principal = Depends(current), db: Session = Depends(get_db)):
    """Names and roles of staff, for pickers (assignee, owner). No emails or status."""
    if p.user.role == "client":
        raise HTTPException(403, "Your role cannot do this")
    rows = db.scalars(select(User).where(User.office_id == p.user.office_id, User.role != "client", User.is_active))
    return {"items": [{"id": str(u.id), "name": u.name, "role": u.role} for u in rows]}


@router.post("/users", status_code=201)
def create_user(body: UserIn, request: Request, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise HTTPException(422, "Unknown role")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "That email already has an account")
    if body.role == "client":
        if not body.client_id or not db.scalar(
            select(Client).where(Client.id == body.client_id, Client.office_id == p.user.office_id)
        ):
            raise HTTPException(422, "A client sign-in must be linked to one of your clients")
    # No password is set here; the person sets their own through the emailed link.
    u = User(
        office_id=p.user.office_id,
        name=body.name,
        email=email,
        role=body.role,
        language=body.language,
        password_hash=hash_password(random_token()),
        client_id=body.client_id if body.role == "client" else None,
    )
    db.add(u)
    db.flush()
    _invite(db, u)
    audit(db, "user.create", p.user, entity_type="user", entity_id=str(u.id), detail={"role": u.role}, request=p.request)
    db.commit()
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: UUID, body: UserPatch, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.id == user_id, User.office_id == p.user.office_id))
    if not u:
        raise HTTPException(404, "User not found")
    new_role = body.role if body.role is not None else u.role
    new_active = body.is_active if body.is_active is not None else u.is_active
    if body.role is not None and body.role not in ROLES:
        raise HTTPException(422, "Unknown role")
    if u.role == "director" and u.is_active and (new_role != "director" or not new_active):
        if _active_directors(db, u.office_id) <= 1:
            raise HTTPException(409, "The office must keep at least one active Director")
    changes = {}
    if body.name is not None:
        u.name = body.name
    if body.language is not None:
        u.language = body.language
    if new_role != u.role:
        changes["role"] = [u.role, new_role]
        u.role = new_role
    if new_active != u.is_active:
        changes["is_active"] = new_active
        u.is_active = new_active
        if not new_active:  # deactivation ends every session at once
            for s in db.scalars(select(AuthSession).where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None))):
                s.revoked_at = utcnow()
    audit(db, "user.update", p.user, entity_type="user", entity_id=str(u.id), detail=changes or None, request=p.request)
    db.commit()
    return user_out(u)


@router.post("/users/{user_id}/invite", status_code=202)
def resend_invite(user_id: UUID, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.id == user_id, User.office_id == p.user.office_id))
    if not u:
        raise HTTPException(404, "User not found")
    _invite(db, u)
    audit(db, "user.invite", p.user, entity_type="user", entity_id=str(u.id), request=p.request)
    db.commit()
    return {"status": "Invitation sent"}


class AssignIn(BaseModel):
    user_ids: list[UUID]


@router.get("/cases/{case_id}/assignments")
def get_assignments(case_id: UUID, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    ids = [str(x) for x in db.scalars(select(CaseAssignment.user_id).where(CaseAssignment.case_id == case.id))]
    return {"user_ids": ids}


@router.put("/cases/{case_id}/assignments")
def set_assignments(case_id: UUID, body: AssignIn, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    ok = {
        u.id
        for u in db.scalars(select(User).where(User.office_id == p.user.office_id, User.is_active, User.role != "client"))
    }
    wanted = set(body.user_ids)
    if not wanted <= ok:
        raise HTTPException(422, "Only active staff of this office can be assigned")
    have = {a.user_id: a for a in db.scalars(select(CaseAssignment).where(CaseAssignment.case_id == case.id))}
    for uid, row in have.items():
        if uid not in wanted:
            db.delete(row)
    for uid in wanted - set(have):
        db.add(CaseAssignment(case_id=case.id, user_id=uid))
    audit(db, "case.assign", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id,
          detail={"count": len(wanted)}, request=p.request)
    db.commit()
    return {"user_ids": [str(x) for x in wanted]}


class FirmIn(BaseModel):
    courts: list[str] | None = None
    stage_templates: dict[str, list[str]] | None = None
    reminder_offsets: list[int] | None = None
    quiet_hours: dict[str, str] | None = None
    client_comms: dict | None = None
    inactive_days: int | None = Field(default=None, ge=1, le=365)


@router.get("/settings/firm")
def firm_get(p: Principal = Depends(current), db: Session = Depends(get_db)):
    if p.user.role == "client":
        raise HTTPException(403, "Your role cannot do this")
    return get_firm(office_of(db, p.user))


@router.put("/settings/firm")
def firm_put(body: FirmIn, p: Principal = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    patch = body.model_dump(exclude_none=True)
    if "reminder_offsets" in patch and any(x < 0 or x > 60 for x in patch["reminder_offsets"]):
        raise HTTPException(422, "Reminder days must be between 0 and 60")
    out = set_firm(db, office_of(db, p.user), patch)
    audit(db, "settings.firm", p.user, detail={"keys": sorted(patch)}, request=p.request)
    db.commit()
    return out
