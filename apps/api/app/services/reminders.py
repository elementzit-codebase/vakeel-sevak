"""Hearing reminders at T-7, T-3, T-1 and the day itself (days are set in firm settings).
Idempotent: reminder_log has a unique row per hearing, offset, channel and recipient, so running the job
twice never sends twice. Quiet hours defer everything to the next run."""

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Case, CaseAssignment, Client, Hearing, Office, PushToken, ReminderLog, User
from . import mailer, push
from .firm import get_firm
from .security import aware, utcnow

IST = timezone(timedelta(hours=5, minutes=30))
TEXT = {
    "en": "Reminder: {title} ({number}) is listed on {date} at {time}, {court}.",
    "ml": "ഓർമ്മപ്പെടുത്തൽ: {title} ({number}) {date} {time}-ന് {court}-ൽ ലിസ്റ്റ് ചെയ്തിട്ടുണ്ട്.",
}


def in_quiet_hours(now_ist: datetime, quiet: dict) -> bool:
    s, e = (time.fromisoformat(quiet["start"]), time.fromisoformat(quiet["end"]))
    t = now_ist.time()
    return (s <= t or t < e) if s > e else (s <= t < e)


def _log(db: Session, hearing_id, offset, channel, recipient) -> bool:
    """Returns False if this reminder was already sent."""
    try:
        with db.begin_nested():
            db.add(ReminderLog(hearing_id=hearing_id, offset_days=offset, channel=channel, recipient=recipient, sent_at=utcnow()))
            db.flush()
        return True
    except IntegrityError:
        return False


def text_for(lang: str, case: Case, h: Hearing) -> str:
    at = aware(h.hearing_at).astimezone(IST)
    return TEXT.get(lang, TEXT["en"]).format(
        title=case.title, number=case.case_number, date=at.strftime("%d %b %Y"), time=at.strftime("%I:%M %p"), court=case.court)


def run(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    now_ist = now.astimezone(IST)
    counts = {"email": 0, "push": 0, "client_email": 0, "deferred": 0}
    for office in db.scalars(select(Office)):
        firm = get_firm(office)
        if in_quiet_hours(now_ist, firm["quiet_hours"]):
            counts["deferred"] += 1
            continue
        offsets = firm["reminder_offsets"]
        comms = firm["client_comms"]
        today = now_ist.date()
        rows = db.execute(
            select(Hearing, Case)
            .join(Case, Case.id == Hearing.case_id)
            .where(Case.office_id == office.id, Hearing.status == "scheduled", Hearing.hearing_at >= now - timedelta(days=1))
        )
        for h, case in rows:
            days = (aware(h.hearing_at).astimezone(IST).date() - today).days
            if days not in offsets:
                continue
            staff_ids = set(db.scalars(select(CaseAssignment.user_id).where(CaseAssignment.case_id == case.id)))
            if case.lead_user_id:
                staff_ids.add(case.lead_user_id)
            for u in db.scalars(select(User).where(User.id.in_(staff_ids), User.is_active)):
                msg = text_for(u.language, case, h)
                if _log(db, h.id, days, "email", u.email):
                    mailer.send(u.email, f"Hearing on {aware(h.hearing_at).astimezone(IST):%d %b}", msg)
                    counts["email"] += 1
                tokens = [t.token for t in db.scalars(select(PushToken).where(PushToken.user_id == u.id))]
                if tokens and _log(db, h.id, days, "push", u.email):
                    push.send(tokens, "Hearing reminder", msg)
                    counts["push"] += 1
            client = db.get(Client, case.client_id)
            if comms.get("enabled") and "email" in comms.get("channels", []) and client.email:
                if _log(db, h.id, days, "client_email", client.email):
                    mailer.send(client.email, "Hearing reminder", text_for(client.language, case, h))
                    counts["client_email"] += 1
    db.commit()
    return counts
