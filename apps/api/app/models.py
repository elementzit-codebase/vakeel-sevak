"""Core tables. Later features add to these through Alembic migrations."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id() -> uuid.UUID:
    return uuid.uuid4()


class Office(Base):
    __tablename__ = "offices"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Roles that must use a second factor. Empty until a Director turns it on.
    mfa_roles: Mapped[list] = mapped_column(JSON, default=list)
    # AUT-08: courts list, stage templates, reminder schedule, communication policy, quiet hours.
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    role: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(8), default="en")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    case_number: Mapped[str] = mapped_column(String(100))
    court: Mapped[str] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(100), default="Filing")
    lead_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    case_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    bench: Mapped[str | None] = mapped_column(String(120), nullable=True)
    judge: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cnr: Mapped[str | None] = mapped_column(String(32), nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hearings: Mapped[list["Hearing"]] = relationship(back_populates="case")


class CaseAssignment(Base):
    """Who may open a case. The Director sees every case without needing a row here."""

    __tablename__ = "case_assignments"
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Hearing(Base):
    __tablename__ = "hearings"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    hearing_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    court_room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    case: Mapped[Case] = relationship(back_populates="hearings")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual, direction, record
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # "web" or "mobile"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # True while the user still has to enrol a second factor the office requires.
    limited: Mapped[bool] = mapped_column(Boolean, default=False)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only. The application refuses updates and deletes; PostgreSQL also enforces it."""

    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("offices.id"), index=True, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


@event.listens_for(AuditLog, "before_update")
@event.listens_for(AuditLog, "before_delete")
def _audit_is_append_only(*_args):
    raise PermissionError("The audit log is append-only")



class CaseParty(Base):
    __tablename__ = "case_parties"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(40))  # petitioner, respondent, accused, complainant...


class CalendarEntry(Base):
    __tablename__ = "calendar_entries"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="meeting")


class Direction(Base):
    """A court direction noted at a hearing; it becomes a task with an owner and due date."""

    __tablename__ = "directions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    hearing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hearings.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_pages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ai: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # summary and extraction, each with a page
    ai_status: Mapped[str] = mapped_column(String(10), default="none")  # none, draft, approved
    ai_approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class HearingRecord(Base):
    __tablename__ = "hearing_records"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    hearing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hearings.id"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    language: Mapped[str] = mapped_column(String(8), default="en")
    source: Mapped[str] = mapped_column(String(10), default="text")  # voice or text
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # what the AI produced, kept unchanged
    final: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # what the advocate approved
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft or approved
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClientMessage(Base):
    __tablename__ = "client_messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), index=True, nullable=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # hearing_summary, fee_notice, reminder, custom
    language: Mapped[str] = mapped_column(String(8), default="en")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft, approved, sent
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hearing_records.id"), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReminderLog(Base):
    __tablename__ = "reminder_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    hearing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hearings.id"), index=True)
    offset_days: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(20))
    recipient: Mapped[str] = mapped_column(String(320))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("hearing_id", "offset_days", "channel", "recipient"),)


class PushToken(Base):
    __tablename__ = "push_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(200), unique=True)


class StatuteSection(Base):
    __tablename__ = "statute_sections"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    act: Mapped[str] = mapped_column(String(10), index=True)  # BNS, BNSS, BSA, IPC, CrPC, IEA
    number: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(300))
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class StatuteMap(Base):
    __tablename__ = "statute_map"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    old_act: Mapped[str] = mapped_column(String(10), index=True)
    old_number: Mapped[str] = mapped_column(String(20), index=True)
    new_act: Mapped[str] = mapped_column(String(10))
    new_number: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class Consultation(Base):
    __tablename__ = "consultations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    language: Mapped[str] = mapped_column(String(8), default="en")
    raw_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft or confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeeEntry(Base):
    __tablename__ = "fee_entries"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))  # fee, expense, received
    amount_paise: Mapped[int] = mapped_column(Integer)
    entry_date: Mapped[date] = mapped_column(Date)
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)  # cash, upi, cheque, bank
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    receipt_no: Mapped[str | None] = mapped_column(String(30), nullable=True, unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ShareLink(Base):
    __tablename__ = "share_links"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_client: Mapped[bool] = mapped_column(Boolean, default=False)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft")


class AskLog(Base):
    __tablename__ = "ask_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_id)
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("offices.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
