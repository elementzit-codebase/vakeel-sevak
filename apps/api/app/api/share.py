"""Client read-only status link and client chat. Both need client communication switched on by a Director."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Case, ChatMessage, Hearing, Office, ShareLink
from ..permissions import get_visible_case
from ..services.audit import audit
from ..services.firm import clients_enabled
from ..services.security import aware, digest, random_token, utcnow
from .deps import Principal, require
from .workspace import touch

router = APIRouter()


class ShareIn(BaseModel):
    days: int = Field(default=14, ge=1, le=90)


def _on(db: Session, office_id) -> None:
    if not clients_enabled(db.get(Office, office_id)):
        raise HTTPException(403, "Client access is switched off. A Director can turn it on in firm settings.")


@router.post("/cases/{case_id}/share", status_code=201)
def create_link(case_id: UUID, body: ShareIn, p: Principal = Depends(require("share.manage")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    _on(db, case.office_id)
    token = random_token()
    db.add(ShareLink(case_id=case.id, token_hash=digest(token), expires_at=utcnow() + timedelta(days=body.days), created_by=p.user.id))
    audit(db, "share.create", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id, request=p.request)
    db.commit()
    return {"url": f"{get_settings().public_web_url}/status/{token}", "expires_in_days": body.days}


@router.delete("/cases/{case_id}/share", status_code=204)
def revoke(case_id: UUID, p: Principal = Depends(require("share.manage")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    for s in db.scalars(select(ShareLink).where(ShareLink.case_id == case.id, ShareLink.revoked_at.is_(None))):
        s.revoked_at = utcnow()
    audit(db, "share.revoke", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id, request=p.request)
    db.commit()


@router.get("/public/status/{token}")
def public_status(token: str, db: Session = Depends(get_db)):
    """No sign-in. Shows only the stage and next date. Every failure gives the same answer."""
    link = db.scalar(select(ShareLink).where(ShareLink.token_hash == digest(token)))
    nope = HTTPException(404, "This link is not valid")
    if not link or link.revoked_at or aware(link.expires_at) < utcnow():
        raise nope
    case = db.get(Case, link.case_id)
    if not clients_enabled(db.get(Office, case.office_id)):
        raise nope
    nxt = db.scalar(select(Hearing.hearing_at).where(Hearing.case_id == case.id, Hearing.status == "scheduled",
                                                       Hearing.hearing_at >= utcnow()).order_by(Hearing.hearing_at).limit(1))
    audit(db, "share.view", None, office_id=case.office_id, entity_type="case", entity_id=str(case.id), case_id=case.id)
    db.commit()
    return {"title": case.title, "case_number": case.case_number, "court": case.court, "stage": case.stage,
            "next_hearing": nxt.isoformat() if nxt else None, "office": db.get(Office, case.office_id).name}


# ---- chat ---------------------------------------------------------------------------------------------------------------
class ChatIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


def chat_out(m: ChatMessage) -> dict:
    return {"id": str(m.id), "from_client": m.from_client, "body": m.body, "at": m.created_at.isoformat()}


def _client_case(db: Session, p: Principal, case_id: UUID) -> Case:
    case = db.scalar(select(Case).where(Case.id == case_id, Case.client_id == p.user.client_id)) if p.user.client_id else None
    if not case:
        raise HTTPException(404, "Case not found")
    _on(db, case.office_id)
    return case


@router.get("/portal/cases/{case_id}/chat")
def client_chat_list(case_id: UUID, p: Principal = Depends(require("chat.use")), db: Session = Depends(get_db)):
    case = _client_case(db, p, case_id)
    rows = db.scalars(select(ChatMessage).where(ChatMessage.case_id == case.id).order_by(ChatMessage.created_at))
    return {"items": [chat_out(m) for m in rows]}


@router.post("/portal/cases/{case_id}/chat", status_code=201)
def client_chat_send(case_id: UUID, body: ChatIn, p: Principal = Depends(require("chat.use")), db: Session = Depends(get_db)):
    case = _client_case(db, p, case_id)
    m = ChatMessage(case_id=case.id, client_id=case.client_id, from_client=True, body=body.body, created_at=utcnow())
    db.add(m)
    db.flush()
    audit(db, "chat.client", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id, request=p.request)
    db.commit()
    return chat_out(m)


@router.get("/cases/{case_id}/chat")
def staff_chat_list(case_id: UUID, p: Principal = Depends(require("records.write")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    rows = db.scalars(select(ChatMessage).where(ChatMessage.case_id == case.id).order_by(ChatMessage.created_at))
    return {"items": [chat_out(m) for m in rows]}


@router.post("/cases/{case_id}/chat", status_code=201)
def staff_chat_send(case_id: UUID, body: ChatIn, p: Principal = Depends(require("messages.approve")), db: Session = Depends(get_db)):
    """Only people who may approve client messages can write to the client (O-6: policy on chat to be confirmed)."""
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    _on(db, case.office_id)
    m = ChatMessage(case_id=case.id, client_id=case.client_id, sender_user_id=p.user.id, body=body.body, created_at=utcnow())
    db.add(m)
    db.flush()
    touch(case)
    audit(db, "chat.staff", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id, request=p.request)
    db.commit()
    return chat_out(m)
