"""Fee ledger (manual: no payment collection). Amounts are stored in paise. Receipts are numbered in sequence
per year (VS/2026/0001). A fee notice is a client message and follows the same approve-then-send path."""

import io
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Case, Client, ClientMessage, FeeEntry, Office
from ..services.audit import audit
from ..services.security import utcnow
from .deps import Principal, require

router = APIRouter()
KINDS = ("fee", "expense", "received")


def balance_for(db: Session, client_id) -> dict:
    rows = dict(tuple(r) for r in db.execute(select(FeeEntry.kind, func.coalesce(func.sum(FeeEntry.amount_paise), 0))
                                             .where(FeeEntry.client_id == client_id).group_by(FeeEntry.kind)))
    billed = int(rows.get("fee", 0)) + int(rows.get("expense", 0))
    received = int(rows.get("received", 0))
    return {"billed_paise": billed, "received_paise": received, "due_paise": billed - received}


def rupees(paise: int) -> str:
    return f"Rs {paise / 100:,.2f}"


def entry_out(e: FeeEntry) -> dict:
    return {"id": str(e.id), "client_id": str(e.client_id), "case_id": str(e.case_id) if e.case_id else None,
            "kind": e.kind, "amount_paise": e.amount_paise, "entry_date": e.entry_date.isoformat(), "mode": e.mode,
            "reference": e.reference, "note": e.note, "receipt_no": e.receipt_no}


def _client(db: Session, p: Principal, client_id: UUID) -> Client:
    c = db.scalar(select(Client).where(Client.id == client_id, Client.office_id == p.user.office_id))
    if not c:
        raise HTTPException(404, "Client not found")
    return c


class EntryIn(BaseModel):
    kind: str
    amount_paise: int = Field(gt=0, le=10_000_000_00)
    entry_date: date
    case_id: UUID | None = None
    mode: str | None = None
    reference: str | None = None
    note: str | None = Field(default=None, max_length=300)


def next_receipt_no(db: Session, office_id, year: int) -> str:
    n = db.scalar(select(func.count()).select_from(FeeEntry).where(
        FeeEntry.office_id == office_id, FeeEntry.receipt_no.like(f"VS/{year}/%"))) or 0
    return f"VS/{year}/{n + 1:04d}"


@router.post("/clients/{client_id}/fees", status_code=201)
def add_entry(client_id: UUID, body: EntryIn, p: Principal = Depends(require("fees.write")), db: Session = Depends(get_db)):
    c = _client(db, p, client_id)
    if body.kind not in KINDS:
        raise HTTPException(422, "Kind must be fee, expense or received")
    if body.case_id:
        case = db.scalar(select(Case).where(Case.id == body.case_id, Case.office_id == p.user.office_id,
                                            Case.client_id == c.id))
        if not case:
            raise HTTPException(422, "That case does not belong to this client")
    e = FeeEntry(office_id=p.user.office_id, client_id=c.id, created_by=p.user.id, created_at=utcnow(), **body.model_dump())
    if e.kind == "received":
        e.receipt_no = next_receipt_no(db, p.user.office_id, e.entry_date.year)
    db.add(e)
    db.flush()
    audit(db, "fee.create", p.user, entity_type="fee", entity_id=str(e.id), case_id=e.case_id,
          detail={"kind": e.kind}, request=p.request)
    db.commit()
    return entry_out(e)


@router.get("/clients/{client_id}/fees")
def ledger(client_id: UUID, p: Principal = Depends(require("fees.read")), db: Session = Depends(get_db)):
    c = _client(db, p, client_id)
    rows = db.scalars(select(FeeEntry).where(FeeEntry.client_id == c.id).order_by(FeeEntry.entry_date, FeeEntry.created_at))
    return {"balance": balance_for(db, c.id), "items": [entry_out(e) for e in rows]}


@router.get("/fees/summary")
def summary(p: Principal = Depends(require("fees.read")), db: Session = Depends(get_db)):
    """Who owes what, for the Fees screen. Largest balance first."""
    out = []
    for c in db.scalars(select(Client).where(Client.office_id == p.user.office_id)):
        b = balance_for(db, c.id)
        if b["billed_paise"] or b["received_paise"]:
            out.append({"client_id": str(c.id), "client": c.name, **b})
    out.sort(key=lambda x: -x["due_paise"])
    return {"items": out, "total_due_paise": sum(max(x["due_paise"], 0) for x in out)}


@router.get("/fees/{entry_id}/receipt.pdf")
def receipt(entry_id: UUID, p: Principal = Depends(require("fees.read")), db: Session = Depends(get_db)):
    e = db.get(FeeEntry, entry_id)
    if not e or e.office_id != p.user.office_id or e.kind != "received":
        raise HTTPException(404, "Receipt not found")
    from reportlab.lib.pagesizes import A5
    from reportlab.pdfgen import canvas

    office, c = db.get(Office, e.office_id), db.get(Client, e.client_id)
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A5)
    w, h = A5
    y = h - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, office.name)
    pdf.setFont("Helvetica", 11)
    y -= 28
    pdf.drawString(40, y, f"Receipt {e.receipt_no}")
    pdf.drawRightString(w - 40, y, f"Date: {e.entry_date:%d %b %Y}")
    y -= 36
    for label, val in (("Received from", c.name), ("Amount", rupees(e.amount_paise)), ("Mode", (e.mode or "-").upper()),
                       ("Reference", e.reference or "-"), ("Towards", e.note or "Professional fees")):
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(40, y, label)
        pdf.setFont("Helvetica", 11)
        pdf.drawString(140, y, str(val)[:60])
        y -= 22
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(40, 40, f"Issued from {get_settings().product_name}. Manual record; no online payment was taken.")
    pdf.showPage()
    pdf.save()
    audit(db, "fee.receipt", p.user, entity_type="fee", entity_id=str(e.id), request=p.request)
    db.commit()
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{e.receipt_no.replace("/", "-")}.pdf"'})


@router.post("/clients/{client_id}/fee-notice", status_code=201)
def fee_notice(client_id: UUID, p: Principal = Depends(require("fees.write")), db: Session = Depends(get_db)):
    """Drafts a polite notice of the balance due. A Director or Advocate approves it before it can be sent."""
    c = _client(db, p, client_id)
    b = balance_for(db, c.id)
    if b["due_paise"] <= 0:
        raise HTTPException(409, "Nothing is due for this client")
    office = db.get(Office, c.office_id)
    body = (f"Dear {c.name}, this is a gentle reminder that {rupees(b['due_paise'])} is outstanding against your "
            f"account with {office.name}. Please contact the office if you have any questions. Thank you.")
    m = ClientMessage(case_id=None, client_id=c.id, kind="fee_notice", language=c.language, body=body,
                      created_by=p.user.id, created_at=utcnow())
    db.add(m)
    db.flush()
    audit(db, "fee.notice_draft", p.user, entity_type="message", entity_id=str(m.id), request=p.request)
    db.commit()
    return {"id": str(m.id), "body": body, "status": m.status}
