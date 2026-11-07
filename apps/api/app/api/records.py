"""Feature 8: hearing records. Speak or type what happened; AI drafts; an advocate approves.
The AI draft is stored unchanged next to the approved version (SRS: review and approval)."""

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Hearing, HearingRecord
from ..permissions import get_visible_case
from ..services.ai import get_ai
from ..services.audit import audit
from ..services.security import utcnow
from ..services.speech import get_speech
from .deps import Principal, require
from .planner import make_direction
from .workspace import clash, touch

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))


def rec_out(r: HearingRecord) -> dict:
    return {
        "id": str(r.id),
        "hearing_id": str(r.hearing_id),
        "case_id": str(r.case_id),
        "language": r.language,
        "source": r.source,
        "transcript": r.transcript,
        "draft": r.draft,
        "final": r.final,
        "status": r.status,
        "approved_by": str(r.approved_by) if r.approved_by else None,
        "created_at": r.created_at.isoformat(),
    }


def _hearing(db: Session, p: Principal, hearing_id: UUID) -> Hearing:
    h = db.get(Hearing, hearing_id)
    if not h or not get_visible_case(db, p.user, h.case_id):
        raise HTTPException(404, "Hearing not found")
    return h


def _make(db: Session, p: Principal, h: Hearing, text: str, language: str, source: str) -> HearingRecord:
    if not text.strip():
        raise HTTPException(422, "Nothing was heard or typed")
    draft = get_ai().run("hearing_record", {"text": text, "language": language, "hearing_date": h.hearing_at.date().isoformat()})
    r = HearingRecord(
        hearing_id=h.id, case_id=h.case_id, created_by=p.user.id, language=language, source=source,
        transcript=text, draft=draft, final=deepcopy(draft), created_at=utcnow(),
    )
    db.add(r)
    db.flush()
    audit(db, "record.create", p.user, entity_type="record", entity_id=str(r.id), case_id=h.case_id,
          detail={"source": source}, request=p.request)
    db.commit()
    return r


class TextIn(BaseModel):
    text: str = Field(min_length=1)
    language: str = "en"


@router.post("/hearings/{hearing_id}/records", status_code=201)
def from_text(hearing_id: UUID, body: TextIn, p: Principal = Depends(require("records.write")), db: Session = Depends(get_db)):
    h = _hearing(db, p, hearing_id)
    return rec_out(_make(db, p, h, body.text, body.language, "text"))


@router.post("/hearings/{hearing_id}/records/audio", status_code=201)
async def from_audio(
    hearing_id: UUID,
    audio: UploadFile = File(...),
    language: str = Form(default="en"),
    p: Principal = Depends(require("records.write")),
    db: Session = Depends(get_db),
):
    h = _hearing(db, p, hearing_id)
    data = await audio.read()
    if len(data) > 25_000_000:
        raise HTTPException(413, "Recording is too large")
    try:
        text = get_speech().transcribe(data, language, audio.content_type or "")
    except Exception as exc:  # provider down, bad key or an audio format it cannot read
        raise HTTPException(502, "The recording could not be turned into text. Type the notes instead.") from exc
    return rec_out(_make(db, p, h, text, language, "voice"))


@router.get("/hearings/{hearing_id}/records")
def list_records(hearing_id: UUID, p: Principal = Depends(require("records.write")), db: Session = Depends(get_db)):
    h = _hearing(db, p, hearing_id)
    rows = db.scalars(select(HearingRecord).where(HearingRecord.hearing_id == h.id).order_by(HearingRecord.created_at.desc()))
    return {"items": [rec_out(r) for r in rows]}


class FinalIn(BaseModel):
    outcome: str
    next_date: date | None = None
    directions: list[dict] = []
    tasks: list[dict] = []
    notes: str = ""


def _rec(db: Session, p: Principal, record_id: UUID) -> HearingRecord:
    r = db.get(HearingRecord, record_id)
    if not r or not get_visible_case(db, p.user, r.case_id):
        raise HTTPException(404, "Record not found")
    return r


@router.patch("/records/{record_id}")
def edit_record(record_id: UUID, body: FinalIn, p: Principal = Depends(require("records.write")), db: Session = Depends(get_db)):
    r = _rec(db, p, record_id)
    if r.status != "draft":
        raise HTTPException(409, "An approved record cannot be changed")
    r.final = {**body.model_dump(mode="json")}  # the AI draft in r.draft is left as it was
    audit(db, "record.edit", p.user, entity_type="record", entity_id=str(r.id), case_id=r.case_id, request=p.request)
    db.commit()
    return rec_out(r)


@router.post("/records/{record_id}/approve")
def approve(record_id: UUID, p: Principal = Depends(require("records.approve")), db: Session = Depends(get_db)):
    r = _rec(db, p, record_id)
    if r.status != "draft":
        raise HTTPException(409, "Already approved")
    case = get_visible_case(db, p.user, r.case_id)
    h = db.get(Hearing, r.hearing_id)
    f = r.final or {}
    h.status = "held"
    clashes = []
    if f.get("next_date"):
        when = datetime.combine(date.fromisoformat(f["next_date"]), time(10, 30), tzinfo=IST)
        nh = Hearing(case_id=case.id, hearing_at=when, purpose="Next date from hearing record")
        db.add(nh)
        db.flush()
        clashes = clash(db, p.user, when, exclude_hearing=nh.id)
    seen = set()
    for d in f.get("directions") or []:  # directions become tasks
        if not d.get("text"):
            continue
        due = date.fromisoformat(d["due_date"]) if d.get("due_date") else None
        make_direction(db, p.user, case, d["text"], due, hearing_id=h.id)
        seen.add(d["text"])
    for t in f.get("tasks") or []:  # extra tasks that are not already a direction
        if t.get("text") and t["text"] not in seen:
            from ..models import Task

            db.add(Task(office_id=case.office_id, case_id=case.id, title=t["text"][:300], source="record",
                        due_date=date.fromisoformat(t["due_date"]) if t.get("due_date") else None,
                        assignee_id=case.lead_user_id, created_by=p.user.id))
    r.status, r.approved_by, r.approved_at = "approved", p.user.id, utcnow()
    touch(case)
    audit(db, "record.approve", p.user, entity_type="record", entity_id=str(r.id), case_id=case.id, request=p.request)
    db.commit()
    return {**rec_out(r), "clashes": clashes}
