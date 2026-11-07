"""Feature 10: rule-based case alerts. No AI; every alert says which rule fired."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Case, Hearing, Office, Task, User
from ..permissions import visible_cases_query
from .firm import get_firm
from .security import aware, utcnow


def alerts_for(db: Session, user: User) -> list[dict]:
    office = db.get(Office, user.office_id)
    inactive_days = get_firm(office)["inactive_days"]
    now = utcnow()
    cases = list(db.scalars(visible_cases_query(user).where(Case.status == "open")))
    ids = [c.id for c in cases]
    if not ids:
        return []
    future = {
        cid
        for (cid,) in db.execute(
            select(Hearing.case_id).where(Hearing.case_id.in_(ids), Hearing.status == "scheduled", Hearing.hearing_at >= now)
        )
    }
    overdue = list(db.scalars(select(Task).where(Task.case_id.in_(ids), Task.done.is_(False), Task.due_date < date.today())))
    out: list[dict] = []
    for c in cases:
        base = {"case_id": str(c.id), "title": c.title}
        if c.id not in future:
            out.append({**base, "rule": "no_next_date", "severity": "high",
                        "message": "No next hearing date is recorded."})
        if c.last_activity_at and now - aware(c.last_activity_at) > timedelta(days=inactive_days):
            out.append({**base, "rule": "inactive", "severity": "low",
                        "message": f"No activity for more than {inactive_days} days."})
    by_case = {c.id: c for c in cases}
    for t in overdue:
        c = by_case[t.case_id]
        rule = "overdue_direction" if t.source == "direction" else "overdue_task"
        out.append({"case_id": str(c.id), "title": c.title, "rule": rule, "severity": "high",
                    "message": f"Overdue: {t.title}", "task_id": str(t.id)})
    order = {"high": 0, "low": 1}
    return sorted(out, key=lambda a: (order[a["severity"]], a["title"]))
