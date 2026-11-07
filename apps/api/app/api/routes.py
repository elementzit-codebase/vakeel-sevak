from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import ROLES, get_settings
from ..db import get_db

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("select 1"))
    return {"status": "ok"}


@router.get("/config")
def public_config():
    """Public, non-secret settings the apps read at start-up (product name, languages)."""
    s = get_settings()
    return {
        "product_name": s.product_name,
        "languages": s.language_list,
        "default_language": s.default_language,
        "roles": ROLES,
    }
