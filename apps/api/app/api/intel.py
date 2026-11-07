"""Features 10 to 12 and Ask VakeelSevak: alerts, statute search with the old-to-new mapping, consultations,
daily activity log with AI summary."""

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AskLog,
    AuditLog,
    Case,
    CaseParty,
    Client,
    Consultation,
    DailySummary,
    Hearing,
    StatuteMap,
    StatuteSection,
    Task,
    User,
)
from ..permissions import has, visible_cases_query
from ..services.ai import get_ai
from ..services.alerts import alerts_for
from ..services.audit import audit
from ..services.security import utcnow
from .deps import Principal, current, require, require_any
from .planner import visible_tasks_query
from .workspace import READ_CASES

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))


@router.get("/alerts")
def alerts(p: Principal = Depends(require_any(*READ_CASES)), db: Session = Depends(get_db)):
    items = alerts_for(db, p.user)
    return {"total": len(items), "items": items}


# ---- statutes (Feature 11) ------------------------------------------------------------------------------------------
UNVERIFIED = "Not checked against the official text. Confirm in the Gazette before relying on it."


def _staff(p: Principal = Depends(current)) -> Principal:
    if p.user.role == "client":
        raise HTTPException(403, "Your role cannot do this")
    return p


def sec_out(s: StatuteSection) -> dict:
    return {"id": str(s.id), "act": s.act, "number": s.number, "title": s.title, "text": s.text,
            "verified": s.verified, "warning": None if s.verified else UNVERIFIED}


@router.get("/statutes/search")
def statute_search(q: str, act: str | None = None, limit: int = 30, p: Principal = Depends(_staff), db: Session = Depends(get_db)):
    like = f"%{q.lower().strip()}%"
    st = select(StatuteSection).where(
        or_(func.lower(StatuteSection.number) == q.lower().strip(), func.lower(StatuteSection.title).like(like),
            func.lower(func.coalesce(StatuteSection.text, "")).like(like)))
    if act:
        st = st.where(StatuteSection.act == act.upper())
    rows = db.scalars(st.order_by(StatuteSection.act, StatuteSection.number).limit(min(limit, 100)))
    return {"items": [sec_out(s) for s in rows]}


@router.get("/statutes/map")
def statute_map(act: str, number: str, p: Principal = Depends(_staff), db: Session = Depends(get_db)):
    """Old to new (IPC to BNS, CrPC to BNSS, IEA to BSA) and back."""
    a, n = act.upper(), number.strip().upper()
    fwd = db.scalars(select(StatuteMap).where(StatuteMap.old_act == a, func.upper(StatuteMap.old_number) == n))
    back = db.scalars(select(StatuteMap).where(StatuteMap.new_act == a, func.upper(StatuteMap.new_number) == n))
    out = [{"old": f"{m.old_act} {m.old_number}", "new": f"{m.new_act} {m.new_number}", "note": m.note,
            "verified": m.verified, "warning": None if m.verified else UNVERIFIED} for m in [*fwd, *back]]
    return {"items": out}


def load_statutes(db: Session, sections_csv: str | None, map_csv: str | None) -> dict:
    """sections: act,number,title,text,verified   map: old_act,old_number,new_act,new_number,note,verified"""
    ns = nm = 0
    for r in csv.DictReader(io.StringIO(sections_csv or "")):
        act, num = r["act"].strip().upper(), r["number"].strip()
        row = db.scalar(select(StatuteSection).where(StatuteSection.act == act, StatuteSection.number == num))
        ver = (r.get("verified") or "").strip().lower() in ("1", "true", "yes")
        if row:
            row.title, row.text, row.verified = r["title"], r.get("text") or None, ver
        else:
            db.add(StatuteSection(act=act, number=num, title=r["title"], text=r.get("text") or None, verified=ver))
        ns += 1
    for r in csv.DictReader(io.StringIO(map_csv or "")):
        oa, on, na, nn = r["old_act"].strip().upper(), r["old_number"].strip(), r["new_act"].strip().upper(), r["new_number"].strip()
        ver = (r.get("verified") or "").strip().lower() in ("1", "true", "yes")
        row = db.scalar(select(StatuteMap).where(StatuteMap.old_act == oa, StatuteMap.old_number == on,
                                                 StatuteMap.new_act == na, StatuteMap.new_number == nn))
        if row:
            row.note, row.verified = r.get("note") or None, ver
        else:
            db.add(StatuteMap(old_act=oa, old_number=on, new_act=na, new_number=nn, note=r.get("note") or None, verified=ver))
        nm += 1
    db.commit()
    return {"sections": ns, "mappings": nm}


@router.post("/statutes/import")
async def statute_import(sections: UploadFile | None = File(default=None), mapping: UploadFile | None = File(default=None),
                         p: Principal = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    s = (await sections.read()).decode("utf-8-sig") if sections else None
    m = (await mapping.read()).decode("utf-8-sig") if mapping else None
    if not s and not m:
        raise HTTPException(422, "Upload a sections file, a mapping file, or both")
    out = load_statutes(db, s, m)
    audit(db, "statutes.import", p.user, detail=out, request=p.request)
    db.commit()
    return out


# ---- consultations (Feature 12) --------------------------------------------------------------------------------------
def cons_out(c: Consultation) -> dict:
    return {"id": str(c.id), "client_id": str(c.client_id) if c.client_id else None, "language": c.language,
            "raw_notes": c.raw_notes, "structured": c.structured, "status": c.status,
            "created_at": c.created_at.isoformat()}


def _cons(db: Session, p: Principal, cid: UUID) -> Consultation:
    c = db.get(Consultation, cid)
    if not c or c.office_id != p.user.office_id or (c.created_by != p.user.id and not has(p.user.role, "cases.read_all")):
        raise HTTPException(404, "Consultation not found")
    return c


class ConsultIn(BaseModel):
    raw_notes: str = Field(min_length=1)
    client_id: UUID | None = None
    language: str = "en"


@router.post("/consultations", status_code=201)
def new_consult(body: ConsultIn, p: Principal = Depends(require("consult.write")), db: Session = Depends(get_db)):
    if body.client_id and not db.scalar(select(Client.id).where(Client.id == body.client_id, Client.office_id == p.user.office_id)):
        raise HTTPException(422, "Choose one of your clients")
    c = Consultation(office_id=p.user.office_id, client_id=body.client_id, created_by=p.user.id, language=body.language,
                     raw_notes=body.raw_notes, structured=get_ai().run("consultation", {"text": body.raw_notes, "language": body.language}),
                     created_at=utcnow())
    db.add(c)
    db.flush()
    audit(db, "consult.create", p.user, entity_type="consultation", entity_id=str(c.id), request=p.request)
    db.commit()
    return cons_out(c)


@router.get("/consultations")
def list_consults(p: Principal = Depends(require("consult.write")), db: Session = Depends(get_db)):
    st = select(Consultation).where(Consultation.office_id == p.user.office_id)
    if not has(p.user.role, "cases.read_all"):
        st = st.where(Consultation.created_by == p.user.id)
    return {"items": [cons_out(c) for c in db.scalars(st.order_by(Consultation.created_at.desc()))]}


@router.patch("/consultations/{cid}")
def edit_consult(cid: UUID, structured: dict, p: Principal = Depends(require("consult.write")), db: Session = Depends(get_db)):
    c = _cons(db, p, cid)
    if c.status != "draft":
        raise HTTPException(409, "A confirmed consultation cannot be changed")
    c.structured = structured
    db.commit()
    return cons_out(c)


@router.post("/consultations/{cid}/confirm")
def confirm_consult(cid: UUID, p: Principal = Depends(require("consult.write")), db: Session = Depends(get_db)):
    c = _cons(db, p, cid)
    c.status, c.confirmed_at = "confirmed", utcnow()
    audit(db, "consult.confirm", p.user, entity_type="consultation", entity_id=str(c.id), request=p.request)
    db.commit()
    return cons_out(c)


class ToCase(BaseModel):
    title: str
    case_number: str
    court: str
    client_id: UUID


@router.post("/consultations/{cid}/create-case", status_code=201)
def consult_to_case(cid: UUID, body: ToCase, p: Principal = Depends(require("cases.write")), db: Session = Depends(get_db)):
    c = _cons(db, p, cid)
    if c.status != "confirmed":
        raise HTTPException(409, "Confirm the consultation first")
    if not db.scalar(select(Client.id).where(Client.id == body.client_id, Client.office_id == p.user.office_id)):
        raise HTTPException(422, "Choose one of your clients")
    from ..models import CaseAssignment

    case = Case(office_id=p.user.office_id, client_id=body.client_id, title=body.title, case_number=body.case_number,
                court=body.court, lead_user_id=None if p.user.role == "director" else p.user.id, last_activity_at=utcnow())
    db.add(case)
    db.flush()
    if p.user.role != "director":
        db.add(CaseAssignment(case_id=case.id, user_id=p.user.id))
    for name in (c.structured or {}).get("parties") or []:
        db.add(CaseParty(case_id=case.id, name=str(name)[:200], role="party"))
    audit(db, "case.create", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id,
          detail={"from": "consultation"}, request=p.request)
    db.commit()
    return {"case_id": str(case.id)}


# ---- daily activity log (Should) -------------------------------------------------------------------------------------
def _day_bounds(day: date):
    s = datetime.combine(day, time(0, 0), tzinfo=IST)
    return s, s + timedelta(days=1)


def activity_items(db: Session, user: User, day: date) -> list[dict]:
    s, e = _day_bounds(day)
    rows = db.execute(
        select(AuditLog.action, AuditLog.user_id, AuditLog.case_id)
        .where(AuditLog.office_id == user.office_id, AuditLog.at >= s, AuditLog.at < e,
               ~AuditLog.action.like("auth.%"), ~AuditLog.action.like("%.view"))
    ).all()
    names = {u.id: u.name for u in db.scalars(select(User).where(User.office_id == user.office_id))}
    titles = {c.id: c.title for c in db.scalars(select(Case).where(Case.office_id == user.office_id))}
    tally: dict = {}
    for action, uid, cid in rows:
        k = (names.get(uid, "System"), action, titles.get(cid, ""))
        tally[k] = tally.get(k, 0) + 1
    return [{"user": u, "action": a, "case": c, "count": n} for (u, a, c), n in sorted(tally.items())]


@router.get("/daily/{day}")
def daily(day: date, p: Principal = Depends(require("daily.read")), db: Session = Depends(get_db)):
    sm = db.scalar(select(DailySummary).where(DailySummary.office_id == p.user.office_id, DailySummary.day == day))
    return {"day": day.isoformat(), "items": activity_items(db, p.user, day),
            "summary": {"body": sm.body, "status": sm.status} if sm else None}


@router.post("/daily/{day}/summary")
def daily_summary(day: date, p: Principal = Depends(require("daily.read")), db: Session = Depends(get_db)):
    items = activity_items(db, p.user, day)
    lines = [f"{i['user']}: {i['action']} x{i['count']}" + (f" ({i['case']})" if i["case"] else "") for i in items]
    body = get_ai().run("daily_summary", {"day": day.isoformat(), "items": lines})["body"]
    sm = db.scalar(select(DailySummary).where(DailySummary.office_id == p.user.office_id, DailySummary.day == day))
    if sm and sm.status == "approved":
        raise HTTPException(409, "This day's summary is already approved")
    if sm:
        sm.body = body
    else:
        db.add(DailySummary(office_id=p.user.office_id, day=day, body=body))
    audit(db, "daily.summary", p.user, request=p.request)
    db.commit()
    return {"day": day.isoformat(), "body": body, "status": "draft"}


@router.post("/daily/{day}/approve")
def daily_approve(day: date, p: Principal = Depends(require("daily.read")), db: Session = Depends(get_db)):
    sm = db.scalar(select(DailySummary).where(DailySummary.office_id == p.user.office_id, DailySummary.day == day))
    if not sm:
        raise HTTPException(404, "No summary for that day")
    sm.status = "approved"
    db.commit()
    return {"day": day.isoformat(), "body": sm.body, "status": sm.status}


# ---- Ask VakeelSevak (Should) ----------------------------------------------------------------------------------------
class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def ask_context(db: Session, user: User, limit: int = 200) -> list[dict]:
    """Only what this user may see. The model never receives other cases."""
    cases = list(db.scalars(visible_cases_query(user).order_by(Case.title).limit(limit)))
    ids = [c.id for c in cases]
    out = [{"type": "case", "id": str(c.id), "label": f"{c.title} | {c.case_number} | {c.court} | stage {c.stage}"} for c in cases]
    if ids:
        for h in db.scalars(select(Hearing).where(Hearing.case_id.in_(ids), Hearing.status == "scheduled").limit(limit)):
            c = next(x for x in cases if x.id == h.case_id)
            out.append({"type": "hearing", "id": str(h.id), "label": f"{c.title} hearing {h.hearing_at:%Y-%m-%d %H:%M} {h.purpose or ''}"})
    if has(user.role, "tasks.read"):
        for t in db.scalars(visible_tasks_query(user).where(Task.done.is_(False)).limit(limit)):
            out.append({"type": "task", "id": str(t.id), "label": f"Task: {t.title} due {t.due_date or 'no date'}"})
    return out


@router.post("/ask")
def ask(body: AskIn, p: Principal = Depends(require("ask.use")), db: Session = Depends(get_db)):
    ctx = ask_context(db, p.user)
    res = get_ai().run("ask", {"question": body.question, "context": ctx})
    known = {(c["type"], c["id"]) for c in ctx}
    sources = [s for s in res.get("sources", []) if (s.get("type"), s.get("id")) in known]  # drop anything not in scope
    answer = res.get("answer", "")
    db.add(AskLog(office_id=p.user.office_id, user_id=p.user.id, question=body.question, answer=answer, sources=sources, at=utcnow()))
    audit(db, "ask.query", p.user, request=p.request)  # the question text is in ask_log, not the audit detail
    db.commit()
    return {"answer": answer, "sources": sources}


@router.get("/ask/history")
def ask_history(p: Principal = Depends(require("ask.use")), db: Session = Depends(get_db)):
    st = select(AskLog).where(AskLog.office_id == p.user.office_id)
    if not has(p.user.role, "audit.read"):
        st = st.where(AskLog.user_id == p.user.id)
    rows = db.scalars(st.order_by(AskLog.at.desc()).limit(50))
    return {"items": [{"id": str(r.id), "question": r.question, "answer": r.answer, "at": r.at.isoformat()} for r in rows]}
