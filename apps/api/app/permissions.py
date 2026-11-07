"""Server-side permissions per role (SRS section 3.1). Every protected route calls require()."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Case, CaseAssignment, User

_COMMON_WORK = {"tasks.read", "tasks.write", "docs.read", "docs.write", "calendar.read"}
_RECORDS = {"records.write", "consult.write", "ask.use", "clients.write"}
PERMISSIONS: dict[str, set[str]] = {
    "director": {
        "cases.read_all",
        "cases.write",
        "clients.read",
        "fees.read",
        "fees.write",
        "users.manage",
        "audit.read",
        "settings.manage",
        "messages.approve",
        "records.approve",
        "calendar.write",
        "share.manage",
        "daily.read",
        *_RECORDS,
        *_COMMON_WORK,
    },
    "advocate": {
        "cases.read_assigned",
        "cases.write",
        "clients.read",
        "fees.read",
        "messages.approve",
        "records.approve",
        "calendar.write",
        "share.manage",
        *_RECORDS,
        *_COMMON_WORK,
    },
    "junior": {"cases.read_assigned", "calendar.write", *_RECORDS, *_COMMON_WORK},
    "clerk": {"cases.read_assigned", "calendar.write", "ask.use", "clients.write", *_COMMON_WORK},
    "accountant": {"clients.read", "fees.read", "fees.write", "tasks.read", "calendar.read"},
    "helper": {"tasks.read", "calendar.read", "docs.upload"},
    "client": {"portal.read", "chat.use"},
}


def has(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())


def visible_cases_query(user: User):
    """The only place that decides which cases a user may see (AUT-04)."""
    q = select(Case).where(Case.office_id == user.office_id)
    if has(user.role, "cases.read_all"):
        return q
    if has(user.role, "cases.read_assigned"):
        return q.join(CaseAssignment, CaseAssignment.case_id == Case.id).where(CaseAssignment.user_id == user.id)
    return q.where(Case.id.is_(None))  # nothing


def get_visible_case(db: Session, user: User, case_id) -> Case | None:
    return db.scalar(visible_cases_query(user).where(Case.id == case_id))
