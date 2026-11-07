"""Feature 9: client messages. AI drafts; a person approves; sending is off until a Director turns client
communication on. Channels: email (SMTP), app push (Expo) and WhatsApp click-to-send (a link, nothing automatic)."""

import re
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Client, ClientMessage, HearingRecord, PushToken, User
from ..permissions import get_visible_case, has
from ..services import mailer, push
from ..services.ai import get_ai
from ..services.audit import audit
from ..services.firm import clients_enabled
from ..services.security import utcnow
from .deps import Principal, current, office_of, require, require_any

router = APIRouter()


def msg_out(m: ClientMessage) -> dict:
    return {"id": str(m.id), "case_id": str(m.case_id) if m.case_id else None, "client_id": str(m.client_id),
            "kind": m.kind, "language": m.language, "body": m.body, "status": m.status, "channel": m.channel,
            "created_at": m.created_at.isoformat(), "sent_at": m.sent_at.isoformat() if m.sent_at else None}


def _msg(db: Session, p: Principal, mid: UUID) -> ClientMessage:
    m = db.get(ClientMessage, mid)
    ok = m and ((m.case_id and get_visible_case(db, p.user, m.case_id)) or (not m.case_id and has(p.user.role, "fees.read")))
    if not ok:
        raise HTTPException(404, "Message not found")
    return m


@router.post("/records/{record_id}/client-message", status_code=201)
def draft_from_record(record_id: UUID, language: str | None = None, p: Principal = Depends(require("records.write")), db: Session = Depends(get_db)):
    r = db.get(HearingRecord, record_id)
    case = get_visible_case(db, p.user, r.case_id) if r else None
    if not r or not case:
        raise HTTPException(404, "Record not found")
    if r.status != "approved":
        raise HTTPException(409, "Approve the hearing record first")
    client = db.get(Client, case.client_id)
    lang = language or client.language
    facts = {"title": case.title, "outcome": (r.final or {}).get("outcome"), "next_date": (r.final or {}).get("next_date")}
    body = get_ai().run("client_message", {"language": lang, "facts": facts})["body"]
    m = ClientMessage(case_id=case.id, client_id=client.id, kind="hearing_summary", language=lang, body=body,
                      record_id=r.id, created_by=p.user.id, created_at=utcnow())
    db.add(m)
    db.flush()
    audit(db, "message.draft", p.user, entity_type="message", entity_id=str(m.id), case_id=case.id, request=p.request)
    db.commit()
    return msg_out(m)


class CustomIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    language: str = "en"


@router.post("/cases/{case_id}/messages", status_code=201)
def draft_custom(case_id: UUID, body: CustomIn, p: Principal = Depends(require("records.write")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    m = ClientMessage(case_id=case.id, client_id=case.client_id, kind="custom", language=body.language, body=body.body,
                      created_by=p.user.id, created_at=utcnow())
    db.add(m)
    db.flush()
    audit(db, "message.draft", p.user, entity_type="message", entity_id=str(m.id), case_id=case.id, request=p.request)
    db.commit()
    return msg_out(m)


@router.get("/cases/{case_id}/messages")
def list_messages(case_id: UUID, p: Principal = Depends(require_any("records.write", "messages.approve")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    rows = db.scalars(select(ClientMessage).where(ClientMessage.case_id == case.id).order_by(ClientMessage.created_at.desc()))
    return {"items": [msg_out(m) for m in rows]}


class BodyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.patch("/messages/{mid}")
def edit(mid: UUID, body: BodyIn, p: Principal = Depends(require("records.write")), db: Session = Depends(get_db)):
    m = _msg(db, p, mid)
    if m.status != "draft":
        raise HTTPException(409, "Only a draft can be edited")
    m.body = body.body
    audit(db, "message.edit", p.user, entity_type="message", entity_id=str(m.id), case_id=m.case_id, request=p.request)
    db.commit()
    return msg_out(m)


@router.post("/messages/{mid}/approve")
def approve(mid: UUID, p: Principal = Depends(require("messages.approve")), db: Session = Depends(get_db)):
    m = _msg(db, p, mid)
    if m.status != "draft":
        raise HTTPException(409, "Already approved")
    m.status, m.approved_by, m.approved_at = "approved", p.user.id, utcnow()
    audit(db, "message.approve", p.user, entity_type="message", entity_id=str(m.id), case_id=m.case_id, request=p.request)
    db.commit()
    return msg_out(m)


class SendIn(BaseModel):
    channel: str  # email, whatsapp, push


def deliver(db: Session, office, m: ClientMessage, channel: str) -> dict:
    """Sends an approved message. Shared by the message and fee-notice endpoints."""
    if not clients_enabled(office):
        raise HTTPException(403, "Client messages are switched off. A Director can turn them on in firm settings.")
    if m.status not in ("approved", "sent"):
        raise HTTPException(409, "Approve the message before sending")
    client = db.get(Client, m.client_id)
    result: dict = {}
    if channel == "email":
        if not client.email:
            raise HTTPException(422, "This client has no email address")
        mailer.send(client.email, "Message from your advocate", m.body)
    elif channel == "whatsapp":
        digits = re.sub(r"\D", "", client.phone or "")
        if len(digits) < 10:
            raise HTTPException(422, "This client has no usable phone number")
        if len(digits) == 10:
            digits = "91" + digits
        # Click-to-send: the advocate opens this link and presses send in WhatsApp themselves.
        result["link"] = f"https://wa.me/{digits}?text={quote(m.body)}"
    elif channel == "push":
        uid = db.scalar(select(User.id).where(User.client_id == client.id, User.is_active))
        tokens = [t.token for t in db.scalars(select(PushToken).where(PushToken.user_id == uid))] if uid else []
        if not tokens:
            raise HTTPException(409, "The client has not installed the app")
        push.send(tokens, "Update from your advocate", m.body)
    else:
        raise HTTPException(422, "Channel must be email, whatsapp or push")
    m.status, m.channel, m.sent_at = "sent", channel, utcnow()
    return result


@router.post("/messages/{mid}/send")
def send(mid: UUID, body: SendIn, p: Principal = Depends(require("messages.approve")), db: Session = Depends(get_db)):
    m = _msg(db, p, mid)
    result = deliver(db, office_of(db, p.user), m, body.channel)
    audit(db, "message.send", p.user, entity_type="message", entity_id=str(m.id), case_id=m.case_id,
          detail={"channel": body.channel}, request=p.request)
    db.commit()
    return {**msg_out(m), **result}


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/push/register", status_code=204)
def register_push(body: TokenIn, p: Principal = Depends(current), db: Session = Depends(get_db)):
    row = db.scalar(select(PushToken).where(PushToken.token == body.token))
    if row:
        row.user_id = p.user.id
    else:
        db.add(PushToken(user_id=p.user.id, token=body.token))
    db.commit()
