"""Feature 3: clients and the case workspace (Client 360, parties, stages, hearings, search)."""

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Case, CaseAssignment, CaseParty, Client, Hearing, Task, User
from ..permissions import get_visible_case, has, visible_cases_query
from ..services.audit import audit
from ..services.firm import get_firm
from ..services.security import aware, utcnow
from .deps import Principal, office_of, require, require_any

router = APIRouter()
READ_CASES = ("cases.read_all", "cases.read_assigned")


def touch(case: Case) -> None:
    case.last_activity_at = utcnow()


def case_card(c: Case, next_hearing: datetime | None = None) -> dict:
    return {
        "id": str(c.id),
        "title": c.title,
        "case_number": c.case_number,
        "court": c.court,
        "stage": c.stage,
        "status": c.status,
        "client_id": str(c.client_id),
        "next_hearing": next_hearing.isoformat() if next_hearing else None,
    }


def next_hearing_map(db: Session, case_ids: list) -> dict:
    if not case_ids:
        return {}
    rows = db.execute(
        select(Hearing.case_id, func.min(Hearing.hearing_at))
        .where(Hearing.case_id.in_(case_ids), Hearing.status == "scheduled", Hearing.hearing_at >= utcnow())
        .group_by(Hearing.case_id)
    )
    return {cid: at for cid, at in rows}


@router.get("/cases")
def list_cases(
    q: str | None = None,
    stage: str | None = None,
    court: str | None = None,
    client_id: UUID | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    p: Principal = Depends(require_any(*READ_CASES)),
    db: Session = Depends(get_db),
):
    base = visible_cases_query(p.user)
    if q:
        like = f"%{q.lower()}%"
        party_ids = select(CaseParty.case_id).where(func.lower(CaseParty.name).like(like))
        client_ids = select(Client.id).where(func.lower(Client.name).like(like))
        base = base.where(
            or_(
                func.lower(Case.title).like(like),
                func.lower(Case.case_number).like(like),
                func.lower(func.coalesce(Case.cnr, "")).like(like),
                Case.id.in_(party_ids),
                Case.client_id.in_(client_ids),
            )
        )
    if stage:
        base = base.where(Case.stage == stage)
    if court:
        base = base.where(Case.court == court)
    if client_id:
        base = base.where(Case.client_id == client_id)
    if status:
        base = base.where(Case.status == status)
    rows = list(db.scalars(base.order_by(Case.title)))
    nxt = next_hearing_map(db, [c.id for c in rows])
    page = rows[offset : offset + min(limit, 500)]
    # The total counts only what this user may see (AUT-04).
    return {"total": len(rows), "items": [case_card(c, nxt.get(c.id)) for c in page]}


class PartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=40)


class CaseIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    case_number: str = Field(min_length=1, max_length=100)
    court: str = Field(min_length=1, max_length=200)
    client_id: UUID
    stage: str = "Filing"
    case_type: str | None = None
    bench: str | None = None
    judge: str | None = None
    cnr: str | None = None
    filing_date: date | None = None
    registration_date: date | None = None
    parties: list[PartyIn] = []


class CasePatch(BaseModel):
    title: str | None = None
    case_number: str | None = None
    court: str | None = None
    stage: str | None = None
    status: str | None = None
    case_type: str | None = None
    bench: str | None = None
    judge: str | None = None
    cnr: str | None = None
    filing_date: date | None = None
    registration_date: date | None = None


def _client_in_office(db: Session, user: User, client_id) -> Client:
    c = db.scalar(select(Client).where(Client.id == client_id, Client.office_id == user.office_id))
    if not c:
        raise HTTPException(422, "Choose one of your clients")
    return c


@router.post("/cases", status_code=201)
def create_case(body: CaseIn, p: Principal = Depends(require("cases.write")), db: Session = Depends(get_db)):
    _client_in_office(db, p.user, body.client_id)
    c = Case(
        office_id=p.user.office_id,
        lead_user_id=p.user.id if p.user.role != "director" else None,
        **body.model_dump(exclude={"parties"}),
    )
    touch(c)
    db.add(c)
    db.flush()
    for pt in body.parties:
        db.add(CaseParty(case_id=c.id, name=pt.name, role=pt.role))
    if p.user.role != "director":  # the creator must be able to open what they created
        db.add(CaseAssignment(case_id=c.id, user_id=p.user.id))
    audit(db, "case.create", p.user, entity_type="case", entity_id=str(c.id), case_id=c.id, request=p.request)
    db.commit()
    return case_card(c)


def case_detail(db: Session, p: Principal, c: Case) -> dict:
    client = db.get(Client, c.client_id)
    parties = list(db.scalars(select(CaseParty).where(CaseParty.case_id == c.id)))
    hearings = list(db.scalars(select(Hearing).where(Hearing.case_id == c.id).order_by(Hearing.hearing_at)))
    tasks = list(db.scalars(select(Task).where(Task.case_id == c.id, Task.done.is_(False)).order_by(Task.due_date)))
    now = utcnow()
    upcoming = [h for h in hearings if h.status == "scheduled" and aware(h.hearing_at) >= now]
    firm = get_firm(office_of(db, p.user))
    stages = firm["stage_templates"].get(c.case_type or "", [])
    out = case_card(c, upcoming[0].hearing_at if upcoming else None)
    out.update(
        {
            "case_type": c.case_type,
            "bench": c.bench,
            "judge": c.judge,
            "cnr": c.cnr,
            "filing_date": c.filing_date.isoformat() if c.filing_date else None,
            "registration_date": c.registration_date.isoformat() if c.registration_date else None,
            "client": {"id": str(client.id), "name": client.name, "phone": client.phone, "email": client.email},
            "parties": [{"id": str(x.id), "name": x.name, "role": x.role} for x in parties],
            "stage_options": stages,
            "hearings": [
                {
                    "id": str(h.id),
                    "at": h.hearing_at.isoformat(),
                    "purpose": h.purpose,
                    "court_room": h.court_room,
                    "status": h.status,
                }
                for h in hearings
            ],
            "open_tasks": [
                {"id": str(t.id), "title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None}
                for t in tasks
            ],
        }
    )
    if has(p.user.role, "users.manage"):
        out["assignee_ids"] = [
            str(x) for x in db.scalars(select(CaseAssignment.user_id).where(CaseAssignment.case_id == c.id))
        ]
    return out


@router.get("/cases/{case_id}")
def get_case(case_id: UUID, p: Principal = Depends(require_any(*READ_CASES)), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")  # same answer whether it exists or not
    audit(db, "case.view", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id, request=p.request)
    db.commit()
    return case_detail(db, p, case)


@router.patch("/cases/{case_id}")
def update_case(case_id: UUID, body: CasePatch, p: Principal = Depends(require("cases.write")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    changed = []
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None and getattr(case, k) != v:
            setattr(case, k, v)
            changed.append(k)
    touch(case)
    audit(db, "case.update", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id,
          detail={"fields": changed}, request=p.request)
    db.commit()
    return case_detail(db, p, case)


@router.put("/cases/{case_id}/parties")
def set_parties(case_id: UUID, body: list[PartyIn], p: Principal = Depends(require("cases.write")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    for x in db.scalars(select(CaseParty).where(CaseParty.case_id == case.id)):
        db.delete(x)
    for pt in body:
        db.add(CaseParty(case_id=case.id, name=pt.name, role=pt.role))
    touch(case)
    audit(db, "case.parties", p.user, entity_type="case", entity_id=str(case.id), case_id=case.id, request=p.request)
    db.commit()
    return {"count": len(body)}


class HearingIn(BaseModel):
    hearing_at: datetime
    purpose: str | None = None
    court_room: str | None = None


class HearingPatch(BaseModel):
    hearing_at: datetime | None = None
    purpose: str | None = None
    court_room: str | None = None
    status: str | None = None  # scheduled, held, adjourned, cancelled


def clash(db: Session, user: User, when: datetime, exclude_hearing=None) -> list[dict]:
    """Other hearings of the same office within 60 minutes of `when` that this user can see."""
    from datetime import timedelta

    q = (
        select(Hearing, Case)
        .join(Case, Case.id == Hearing.case_id)
        .where(
            Case.id.in_(visible_cases_query(user).with_only_columns(Case.id)),
            Hearing.status == "scheduled",
            Hearing.hearing_at > when - timedelta(minutes=60),
            Hearing.hearing_at < when + timedelta(minutes=60),
        )
    )
    return [
        {"hearing_id": str(h.id), "case_id": str(c.id), "title": c.title, "at": h.hearing_at.isoformat()}
        for h, c in db.execute(q)
        if h.id != exclude_hearing
    ]


@router.post("/cases/{case_id}/hearings", status_code=201)
def add_hearing(case_id: UUID, body: HearingIn, p: Principal = Depends(require("calendar.write")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    h = Hearing(case_id=case.id, hearing_at=body.hearing_at, purpose=body.purpose, court_room=body.court_room)
    db.add(h)
    db.flush()
    touch(case)
    audit(db, "hearing.create", p.user, entity_type="hearing", entity_id=str(h.id), case_id=case.id, request=p.request)
    clashes = clash(db, p.user, body.hearing_at, exclude_hearing=h.id)
    db.commit()
    return {"id": str(h.id), "clashes": clashes}  # a warning, not a block


@router.patch("/hearings/{hearing_id}")
def update_hearing(hearing_id: UUID, body: HearingPatch, p: Principal = Depends(require("calendar.write")), db: Session = Depends(get_db)):
    h = db.get(Hearing, hearing_id)
    case = get_visible_case(db, p.user, h.case_id) if h else None
    if not h or not case:
        raise HTTPException(404, "Hearing not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(h, k, v)
    touch(case)
    audit(db, "hearing.update", p.user, entity_type="hearing", entity_id=str(h.id), case_id=case.id, request=p.request)
    clashes = clash(db, p.user, h.hearing_at, exclude_hearing=h.id) if h.status == "scheduled" else []
    db.commit()
    return {"id": str(h.id), "clashes": clashes}


# ---- clients ----------------------------------------------------------------------------------------------------


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    email: EmailStr | None = None
    language: str = "en"
    address: str | None = None
    notes: str | None = None


def client_out(c: Client) -> dict:
    return {"id": str(c.id), "name": c.name, "phone": c.phone, "email": c.email, "language": c.language,
            "address": c.address, "notes": c.notes}


@router.get("/clients")
def list_clients(q: str | None = None, p: Principal = Depends(require("clients.read")), db: Session = Depends(get_db)):
    st = select(Client).where(Client.office_id == p.user.office_id)
    if q:
        st = st.where(func.lower(Client.name).like(f"%{q.lower()}%"))
    return {"items": [client_out(c) for c in db.scalars(st.order_by(Client.name))]}


@router.post("/clients", status_code=201)
def create_client(body: ClientIn, p: Principal = Depends(require("clients.write")), db: Session = Depends(get_db)):
    c = Client(office_id=p.user.office_id, **{**body.model_dump(), "email": str(body.email) if body.email else None})
    db.add(c)
    db.flush()
    audit(db, "client.create", p.user, entity_type="client", entity_id=str(c.id), request=p.request)
    db.commit()
    return client_out(c)


@router.patch("/clients/{client_id}")
def update_client(client_id: UUID, body: ClientIn, p: Principal = Depends(require("clients.write")), db: Session = Depends(get_db)):
    c = db.scalar(select(Client).where(Client.id == client_id, Client.office_id == p.user.office_id))
    if not c:
        raise HTTPException(404, "Client not found")
    for k, v in body.model_dump().items():
        setattr(c, k, str(v) if k == "email" and v else v)
    audit(db, "client.update", p.user, entity_type="client", entity_id=str(c.id), request=p.request)
    db.commit()
    return client_out(c)


@router.get("/clients/{client_id}")
def client_360(client_id: UUID, p: Principal = Depends(require("clients.read")), db: Session = Depends(get_db)):
    """Everything about one client in one place. Cases are limited to those this user may see."""
    c = db.scalar(select(Client).where(Client.id == client_id, Client.office_id == p.user.office_id))
    if not c:
        raise HTTPException(404, "Client not found")
    cases = list(db.scalars(visible_cases_query(p.user).where(Case.client_id == c.id).order_by(Case.title)))
    nxt = next_hearing_map(db, [x.id for x in cases])
    out = {**client_out(c), "cases": [case_card(x, nxt.get(x.id)) for x in cases]}
    if has(p.user.role, "fees.read"):
        from .fees import balance_for

        out["balance"] = balance_for(db, c.id)
    audit(db, "client.view", p.user, entity_type="client", entity_id=str(c.id), request=p.request)
    db.commit()
    return out
