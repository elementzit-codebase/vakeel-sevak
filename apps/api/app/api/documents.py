"""Feature 7: documents with text extraction (OCR) and an AI summary that stays a draft until approved."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Document
from ..permissions import get_visible_case
from ..services import storage
from ..services.ai import get_ai
from ..services.audit import audit
from ..services.ocr import extract_pages
from ..services.security import aware, utcnow
from .deps import Principal, require
from .workspace import touch

router = APIRouter()
ALLOWED = ("application/pdf", "image/", "text/plain")
RESTORE_DAYS = 30


def doc_out(d: Document, full: bool = False) -> dict:
    out = {
        "id": str(d.id),
        "case_id": str(d.case_id),
        "name": d.name,
        "doc_type": d.doc_type,
        "content_type": d.content_type,
        "size": d.size,
        "uploaded_at": d.uploaded_at.isoformat(),
        "has_text": bool(d.ocr_text),
        "ai_status": d.ai_status,
        "deleted_at": d.deleted_at.isoformat() if d.deleted_at else None,
    }
    if full:
        out["ai"] = d.ai
        out["text_preview"] = (d.ocr_text or "")[:2000]
    return out


def _doc(db: Session, p: Principal, doc_id: UUID, include_deleted=False) -> Document:
    d = db.get(Document, doc_id)
    if not d or d.office_id != p.user.office_id or not get_visible_case(db, p.user, d.case_id):
        raise HTTPException(404, "Document not found")
    if d.deleted_at and not include_deleted:
        raise HTTPException(404, "Document not found")
    return d


@router.post("/cases/{case_id}/documents", status_code=201)
async def upload(
    case_id: UUID,
    file: UploadFile = File(...),
    doc_type: str | None = Form(default=None),
    p: Principal = Depends(require("docs.write")),
    db: Session = Depends(get_db),
):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    ct = file.content_type or "application/octet-stream"
    if not ct.startswith(ALLOWED):
        raise HTTPException(415, "Upload a PDF, an image or a text file")
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1_000_000:
        raise HTTPException(413, f"File is larger than {get_settings().max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    pages = extract_pages(data, ct, file.filename or "")
    d = Document(
        office_id=case.office_id,
        case_id=case.id,
        name=(file.filename or "document")[:300],
        doc_type=doc_type,
        content_type=ct,
        size=len(data),
        storage_key=storage.save(data),
        uploaded_by=p.user.id,
        uploaded_at=utcnow(),
        ocr_text="\n\n".join(pages) if pages else None,
        ocr_pages=pages or None,
    )
    db.add(d)
    db.flush()
    touch(case)
    audit(db, "doc.upload", p.user, entity_type="document", entity_id=str(d.id), case_id=case.id, request=p.request)
    db.commit()
    return doc_out(d)


@router.get("/cases/{case_id}/documents")
def list_docs(
    case_id: UUID,
    q: str | None = None,
    p: Principal = Depends(require("docs.read")),
    db: Session = Depends(get_db),
):
    case = get_visible_case(db, p.user, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    st = select(Document).where(Document.case_id == case.id, Document.deleted_at.is_(None))
    if q:
        like = f"%{q.lower()}%"
        from sqlalchemy import func, or_

        st = st.where(or_(func.lower(Document.name).like(like), func.lower(func.coalesce(Document.ocr_text, "")).like(like)))
    return {"items": [doc_out(d) for d in db.scalars(st.order_by(Document.uploaded_at.desc()))]}


@router.get("/documents/{doc_id}")
def get_doc(doc_id: UUID, p: Principal = Depends(require("docs.read")), db: Session = Depends(get_db)):
    return doc_out(_doc(db, p, doc_id), full=True)


@router.get("/documents/{doc_id}/download")
def download(doc_id: UUID, p: Principal = Depends(require("docs.read")), db: Session = Depends(get_db)):
    d = _doc(db, p, doc_id)
    audit(db, "doc.download", p.user, entity_type="document", entity_id=str(d.id), case_id=d.case_id, request=p.request)
    db.commit()
    safe = d.name.replace('"', "")
    return Response(storage.load(d.storage_key), media_type=d.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


@router.delete("/documents/{doc_id}")
def soft_delete(doc_id: UUID, p: Principal = Depends(require("docs.write")), db: Session = Depends(get_db)):
    d = _doc(db, p, doc_id)
    d.deleted_at = utcnow()
    audit(db, "doc.delete", p.user, entity_type="document", entity_id=str(d.id), case_id=d.case_id, request=p.request)
    db.commit()
    return {"status": f"Deleted. It can be restored for {RESTORE_DAYS} days."}


@router.post("/documents/{doc_id}/restore")
def restore(doc_id: UUID, p: Principal = Depends(require("docs.write")), db: Session = Depends(get_db)):
    d = _doc(db, p, doc_id, include_deleted=True)
    if not d.deleted_at or utcnow() - aware(d.deleted_at) > timedelta(days=RESTORE_DAYS):
        raise HTTPException(409, "This document cannot be restored")
    d.deleted_at = None
    audit(db, "doc.restore", p.user, entity_type="document", entity_id=str(d.id), case_id=d.case_id, request=p.request)
    db.commit()
    return doc_out(d)


def purge_expired(db: Session) -> int:
    """Removes files deleted more than 30 days ago. Run by the daily job."""
    cutoff = utcnow() - timedelta(days=RESTORE_DAYS)
    n = 0
    for d in list(db.scalars(select(Document).where(Document.deleted_at.is_not(None)))):
        if aware(d.deleted_at) < cutoff:
            storage.remove(d.storage_key)
            db.delete(d)
            n += 1
    db.commit()
    return n


@router.post("/documents/{doc_id}/summarize")
def summarize(doc_id: UUID, p: Principal = Depends(require("docs.write")), db: Session = Depends(get_db)):
    d = _doc(db, p, doc_id)
    if not d.ocr_text:
        raise HTTPException(422, "No text could be read from this document")
    d.ai = get_ai().run("document_summary", {"text": d.ocr_text[:40000], "pages": d.ocr_pages or []})
    d.ai_status, d.ai_approved_by = "draft", None
    audit(db, "doc.ai_summary", p.user, entity_type="document", entity_id=str(d.id), case_id=d.case_id, request=p.request)
    db.commit()
    return doc_out(d, full=True)


@router.post("/documents/{doc_id}/ai/approve")
def approve_summary(doc_id: UUID, p: Principal = Depends(require("records.approve")), db: Session = Depends(get_db)):
    d = _doc(db, p, doc_id)
    if d.ai_status != "draft":
        raise HTTPException(409, "There is no draft summary to approve")
    d.ai_status, d.ai_approved_by = "approved", p.user.id
    audit(db, "doc.ai_approve", p.user, entity_type="document", entity_id=str(d.id), case_id=d.case_id, request=p.request)
    db.commit()
    return doc_out(d, full=True)
