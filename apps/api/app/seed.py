"""Load the sample dataset: python -m app.seed [--reset]"""

import sys
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import sample_data as s_
from .db import SessionLocal
from .models import (
    AuthSession,
    Case,
    CaseAssignment,
    Client,
    Hearing,
    Office,
    PasswordReset,
    Task,
    User,
)
from .services.security import hash_password

DEV_PASSWORD = "ChangeMe#2026"  # sample dataset only; never use in production


def seed(db: Session) -> dict[str, int]:
    if db.scalar(select(Office).where(Office.name == s_.OFFICE)):
        return {"skipped": 1}
    office = Office(name=s_.OFFICE)
    db.add(office)
    db.flush()
    pw = hash_password(DEV_PASSWORD)
    users = [
        User(office_id=office.id, name=n, email=e, role=r, language=lang, password_hash=pw)
        for n, e, r, lang in s_.USERS
    ]
    clients = [Client(office_id=office.id, name=n, phone=p, email=e, language=lang) for n, p, e, lang in s_.CLIENTS]
    db.add_all(users + clients)
    db.flush()
    # A client who can sign in and see only their own cases (read-only).
    db.add(
        User(
            office_id=office.id,
            name=clients[0].name,
            email=clients[0].email,
            role="client",
            language=clients[0].language,
            password_hash=pw,
            client_id=clients[0].id,
        )
    )
    cases = [
        Case(
            office_id=office.id,
            client_id=clients[ci].id,
            title=t,
            case_number=num,
            court=court,
            stage=stage,
            lead_user_id=users[ui].id,
        )
        for t, num, court, ci, ui, stage in s_.CASES
    ]
    db.add_all(cases)
    db.flush()
    # Assignments: the lead on each case, plus the junior on two cases and the clerk on one.
    pairs = {(case.id, users[ui].id) for case, (*_, ui, _) in zip(cases, s_.CASES, strict=True)}
    pairs |= {(cases[0].id, users[2].id), (cases[4].id, users[2].id), (cases[0].id, users[3].id)}
    db.add_all(CaseAssignment(case_id=c, user_id=u) for c, u in pairs)
    db.flush()
    for idx, at, purpose, room in s_.hearings(datetime.now(s_.IST)):
        db.add(Hearing(case_id=cases[idx].id, hearing_at=at, purpose=purpose, court_room=room))
    db.add(
        Task(
            office_id=office.id,
            case_id=cases[4].id,
            title="File vakalatnama",
            assignee_id=users[3].id,
        )
    )
    db.add(
        Task(
            office_id=office.id,
            case_id=cases[0].id,
            title="Certified copy of order",
            assignee_id=users[3].id,
        )
    )
    db.commit()
    return {
        "users": len(users) + 1,
        "clients": len(clients),
        "cases": len(cases),
        "hearings": 5,
        "tasks": 2,
    }


if __name__ == "__main__":
    with SessionLocal() as db:
        if "--reset" in sys.argv:
            for m in (PasswordReset, AuthSession, Task, Hearing, CaseAssignment, Case, User, Client, Office):
                db.query(m).delete()
            db.commit()
        print(seed(db))
