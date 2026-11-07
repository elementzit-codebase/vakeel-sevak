"""Features 5 and 6: calendar, next date and the Today dashboard, tasks, court directions."""

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CalendarEntry, Case, Direction, Hearing, Task, User
from ..permissions import get_visible_case, has, visible_cases_query
from ..services.audit import audit
from ..services.security import utcnow
from .deps import Principal, current, require
from .workspace import touch

router = APIRouter()
IST_TZ = timezone(timedelta(hours=5, minutes=30))


def visible_tasks_query(user: User):
    q = select(Task).where(Task.office_id == user.office_id)
    mine = Task.assignee_id == user.id
    if has(user.role, "cases.read_all"):
        return q
    if has(user.role, "cases.read_assigned"):
        ids = visible_cases_query(user).with_only_columns(Case.id)
        return q.where(or_(mine, Task.case_id.in_(ids)))
    return q.where(mine)


def task_out(t: Task, case_title: str | None = None) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "case_id": str(t.case_id) if t.case_id else None,
        "case_title": case_title,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "assignee_id": str(t.assignee_id) if t.assignee_id else None,
        "done": t.done,
        "priority": t.priority,
        "source": t.source,
    }


def _titles(db: Session, tasks: list[Task]) -> dict:
    ids = {t.case_id for t in tasks if t.case_id}
    return {c.id: c.title for c in db.scalars(select(Case).where(Case.id.in_(ids)))} if ids else {}


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    case_id: UUID | None = None
    due_date: date | None = None
    assignee_id: UUID | None = None
    priority: str = "normal"


class TaskPatch(BaseModel):
    title: str | None = None
    due_date: date | None = None
    assignee_id: UUID | None = None
    priority: str | None = None
    done: bool | None = None


def _check_assignee(db: Session, user: User, assignee_id) -> None:
    if assignee_id and not db.scalar(
        select(User.id).where(User.id == assignee_id, User.office_id == user.office_id, User.is_active, User.role != "client")
    ):
        raise HTTPException(422, "Choose an active member of your office")


@router.get("/tasks")
def list_tasks(
    mine: bool = False,
    case_id: UUID | None = None,
    done: bool | None = False,
    overdue: bool = False,
    p: Principal = Depends(require("tasks.read")),
    db: Session = Depends(get_db),
):
    q = visible_tasks_query(p.user)
    if mine:
        q = q.where(Task.assignee_id == p.user.id)
    if case_id:
        q = q.where(Task.case_id == case_id)
    if done is not None:
        q = q.where(Task.done.is_(done))
    if overdue:
        q = q.where(Task.done.is_(False), Task.due_date < date.today())
    rows = list(db.scalars(q.order_by(Task.due_date.is_(None), Task.due_date, Task.title)))
    titles = _titles(db, rows)
    return {"total": len(rows), "items": [task_out(t, titles.get(t.case_id)) for t in rows]}


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, p: Principal = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    if body.case_id and not get_visible_case(db, p.user, body.case_id):
        raise HTTPException(404, "Case not found")
    _check_assignee(db, p.user, body.assignee_id)
    t = Task(office_id=p.user.office_id, created_by=p.user.id, **body.model_dump())
    db.add(t)
    db.flush()
    audit(db, "task.create", p.user, entity_type="task", entity_id=str(t.id), case_id=t.case_id, request=p.request)
    db.commit()
    return task_out(t)


@router.patch("/tasks/{task_id}")
def update_task(task_id: UUID, body: TaskPatch, p: Principal = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    t = db.scalar(visible_tasks_query(p.user).where(Task.id == task_id))
    if not t:
        raise HTTPException(404, "Task not found")
    data = body.model_dump(exclude_unset=True)
    if "assignee_id" in data:
        _check_assignee(db, p.user, data["assignee_id"])
    for k, v in data.items():
        setattr(t, k, v)
    if body.done is not None:
        t.completed_at = utcnow() if body.done else None
    audit(db, "task.update", p.user, entity_type="task", entity_id=str(t.id), case_id=t.case_id, request=p.request)
    db.commit()
    return task_out(t)


class DirectionIn(BaseModel):
    text: str = Field(min_length=1)
    due_date: date | None = None
    hearing_id: UUID | None = None
    assignee_id: UUID | None = None


def make_direction(db: Session, user: User, case: Case, text: str, due, hearing_id=None, assignee_id=None) -> Direction:
    """A court direction always becomes a task, so nothing said in court is forgotten."""
    _check_assignee(db, user, assignee_id)
    t = Task(
        office_id=case.office_id,
        case_id=case.id,
        title=text[:300],
        due_date=due,
        assignee_id=assignee_id or case.lead_user_id,
        source="direction",
        created_by=user.id,
        priority="high",
    )
    db.add(t)
    db.flush()
    d = Direction(case_id=case.id, hearing_id=hearing_id, text=text, due_date=due, task_id=t.id, created_at=utcnow())
    db.add(d)
    db.flush()
    touch(case)
    return d


@router.get("/cases/{case_id}/directions")
def list_directions(case_id: UUID, p: Principal = Depends(require("tasks.read")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    rows = db.scalars(select(Direction).where(Direction.case_id == case.id).order_by(Direction.created_at.desc()))
    out = []
    for d in rows:
        t = db.get(Task, d.task_id) if d.task_id else None
        out.append({"id": str(d.id), "text": d.text, "due_date": d.due_date.isoformat() if d.due_date else None,
                    "task_id": str(d.task_id) if d.task_id else None, "done": bool(t and t.done)})
    return {"items": out}


@router.post("/cases/{case_id}/directions", status_code=201)
def add_direction(case_id: UUID, body: DirectionIn, p: Principal = Depends(require("tasks.write")), db: Session = Depends(get_db)):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    d = make_direction(db, p.user, case, body.text, body.due_date, body.hearing_id, body.assignee_id)
    audit(db, "direction.create", p.user, entity_type="direction", entity_id=str(d.id), case_id=case.id, request=p.request)
    db.commit()
    return {"id": str(d.id), "task_id": str(d.task_id)}


# ---- calendar -----------------------------------------------------------------------------------------------------


class EntryIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    starts_at: datetime
    ends_at: datetime | None = None
    case_id: UUID | None = None
    kind: str = "meeting"


@router.post("/calendar", status_code=201)
def add_entry(body: EntryIn, p: Principal = Depends(require("calendar.write")), db: Session = Depends(get_db)):
    if body.case_id and not get_visible_case(db, p.user, body.case_id):
        raise HTTPException(404, "Case not found")
    e = CalendarEntry(office_id=p.user.office_id, user_id=p.user.id, **body.model_dump())
    db.add(e)
    db.flush()
    audit(db, "calendar.create", p.user, entity_type="calendar", entity_id=str(e.id), case_id=e.case_id, request=p.request)
    db.commit()
    return {"id": str(e.id)}


def calendar_items(db: Session, user: User, start: datetime, end: datetime) -> list[dict]:
    hs = db.execute(
        select(Hearing, Case)
        .join(Case, Case.id == Hearing.case_id)
        .where(
            Case.id.in_(visible_cases_query(user).with_only_columns(Case.id)),
            Hearing.hearing_at >= start,
            Hearing.hearing_at < end,
        )
    )
    items = [
        {"type": "hearing", "id": str(h.id), "at": h.hearing_at.isoformat(), "title": c.title,
         "detail": h.purpose, "court": c.court, "room": h.court_room, "case_id": str(c.id), "status": h.status}
        for h, c in hs
    ]
    es = db.scalars(
        select(CalendarEntry).where(
            CalendarEntry.office_id == user.office_id,
            CalendarEntry.starts_at >= start,
            CalendarEntry.starts_at < end,
            or_(CalendarEntry.user_id == user.id, CalendarEntry.user_id.is_(None)),
        )
    )
    items += [
        {"type": "entry", "id": str(e.id), "at": e.starts_at.isoformat(), "title": e.title, "detail": e.kind,
         "case_id": str(e.case_id) if e.case_id else None}
        for e in es
    ]
    return sorted(items, key=lambda x: x["at"])


@router.get("/calendar")
def calendar(
    start: datetime,
    end: datetime,
    p: Principal = Depends(require("calendar.read")),
    db: Session = Depends(get_db),
):
    if end <= start or end - start > timedelta(days=100):
        raise HTTPException(422, "Choose a range of up to 100 days")
    return {"items": calendar_items(db, p.user, start, end)}


@router.get("/today")
def today(p: Principal = Depends(current), db: Session = Depends(get_db)):
    """The first screen: today's hearings, overdue and due tasks, the next week, and open alerts."""
    if p.user.role == "client":
        raise HTTPException(403, "Your role cannot do this")
    from ..services.alerts import alerts_for

    now = utcnow()
    day0 = datetime.combine(now.astimezone(IST_TZ).date(), time(0, 0), tzinfo=IST_TZ)
    out: dict = {"date": day0.date().isoformat(), "hearings_today": [], "week": [], "tasks": [], "alerts": []}
    if has(p.user.role, "calendar.read"):
        items = calendar_items(db, p.user, day0, day0 + timedelta(days=8))
        cut = (day0 + timedelta(days=1)).isoformat()
        out["hearings_today"] = [i for i in items if i["at"] < cut]
        out["week"] = [i for i in items if i["at"] >= cut]
    if has(p.user.role, "tasks.read"):
        q = visible_tasks_query(p.user).where(Task.done.is_(False), Task.due_date <= day0.date() + timedelta(days=1))
        rows = list(db.scalars(q.order_by(Task.due_date)))
        titles = _titles(db, rows)
        out["tasks"] = [{**task_out(t, titles.get(t.case_id)), "overdue": bool(t.due_date and t.due_date < day0.date())} for t in rows]
    if has(p.user.role, "cases.read_all") or has(p.user.role, "cases.read_assigned"):
        out["alerts"] = alerts_for(db, p.user)
    return out
