"""Feature 4: import cases from Excel or CSV with a preview before anything is saved."""

import csv
import io
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Case, CaseAssignment, Client, Hearing
from ..services.audit import audit
from .deps import Principal, require

router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))
ALIASES = {
    "title": ["title", "case title", "matter", "case name"],
    "case_number": ["case number", "case no", "case_number", "number", "case no."],
    "court": ["court"],
    "client": ["client", "client name"],
    "client_phone": ["client phone", "phone", "mobile", "client_phone"],
    "stage": ["stage", "status"],
    "case_type": ["type", "case type", "case_type"],
    "next_hearing": ["next date", "next hearing", "next_hearing", "next date of hearing"],
}
REQUIRED = ["title", "case_number", "court", "client"]


def _norm(h: str) -> str:
    h = (h or "").strip().lower()
    for key, names in ALIASES.items():
        if h in names:
            return key
    return h


def _date(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    for f in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(v).strip(), f).date()
        except ValueError:
            pass
    raise ValueError(f"cannot read date '{v}'")


def read_rows(name: str, data: bytes) -> list[dict]:
    if name.lower().endswith(".xlsx"):
        from openpyxl import load_workbook

        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        head = [_norm(str(h or "")) for h in rows[0]]
        return [dict(zip(head, r, strict=False)) for r in rows[1:] if any(c not in (None, "") for c in r)]
    if name.lower().endswith((".csv", ".txt")):
        text = data.decode("utf-8-sig", "replace")
        rd = csv.DictReader(io.StringIO(text))
        return [{_norm(k): v for k, v in r.items() if k} for r in rd if any((v or "").strip() for v in r.values())]
    raise HTTPException(422, "Upload an .xlsx or .csv file")


def check(db: Session, office_id, raw: list[dict]) -> list[dict]:
    seen: set[str] = set()
    existing = set(db.scalars(select(func.lower(Case.case_number)).where(Case.office_id == office_id)))
    out = []
    for i, r in enumerate(raw, start=2):  # row 1 is the header
        errs, warns = [], []
        row = {k: (str(r.get(k)).strip() if r.get(k) not in (None, "") else None) for k in
               ("title", "case_number", "court", "client", "client_phone", "stage", "case_type")}
        for k in REQUIRED:
            if not row[k]:
                errs.append(f"{k.replace('_', ' ')} is missing")
        nh = None
        try:
            nh = _date(r.get("next_hearing"))
        except ValueError as e:
            errs.append(str(e))
        row["next_hearing"] = nh.isoformat() if nh else None
        key = (row["case_number"] or "").lower()
        if key and key in existing:
            warns.append("a case with this number already exists; it will be skipped")
        elif key and key in seen:
            warns.append("repeated in this file; it will be skipped")
        seen.add(key)
        status = "error" if errs else ("skip" if warns else "ok")
        out.append({"row": i, "status": status, "errors": errs, "warnings": warns, "data": row})
    return out


@router.post("/import/preview")
async def preview(file: UploadFile = File(...), p: Principal = Depends(require("cases.write")), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "File is too large (limit 5 MB)")
    raw = read_rows(file.filename or "", data)
    if not raw:
        raise HTTPException(422, "The file has no rows")
    rows = check(db, p.user.office_id, raw)
    return {
        "total": len(rows),
        "ok": sum(r["status"] == "ok" for r in rows),
        "skip": sum(r["status"] == "skip" for r in rows),
        "errors": sum(r["status"] == "error" for r in rows),
        "rows": rows,
    }


class CommitIn(BaseModel):
    rows: list[dict]  # the data objects from the preview, optionally corrected


@router.post("/import/commit")
def commit(body: CommitIn, p: Principal = Depends(require("cases.write")), db: Session = Depends(get_db)):
    checked = check(db, p.user.office_id, body.rows)
    created = skipped = 0
    for r in checked:
        if r["status"] != "ok":
            skipped += 1
            continue
        d = r["data"]
        client = db.scalar(
            select(Client).where(Client.office_id == p.user.office_id, func.lower(Client.name) == d["client"].lower())
        )
        if not client:
            client = Client(office_id=p.user.office_id, name=d["client"], phone=d["client_phone"])
            db.add(client)
            db.flush()
        c = Case(
            office_id=p.user.office_id,
            client_id=client.id,
            title=d["title"],
            case_number=d["case_number"],
            court=d["court"],
            stage=d["stage"] or "Filing",
            case_type=d["case_type"],
            lead_user_id=None if p.user.role == "director" else p.user.id,
        )
        db.add(c)
        db.flush()
        if p.user.role != "director":
            db.add(CaseAssignment(case_id=c.id, user_id=p.user.id))
        if d["next_hearing"]:
            when = datetime.combine(date.fromisoformat(d["next_hearing"]), time(10, 30), tzinfo=IST)
            db.add(Hearing(case_id=c.id, hearing_at=when, purpose="Imported next date"))
        created += 1
    audit(db, "import.commit", p.user, detail={"created": created, "skipped": skipped}, request=p.request)
    db.commit()
    return {"created": created, "skipped": skipped}
