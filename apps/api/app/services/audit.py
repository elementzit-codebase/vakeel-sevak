from fastapi import Request
from sqlalchemy.orm import Session

from ..models import AuditLog, User
from .security import utcnow


def audit(
    db: Session,
    action: str,
    user: User | None = None,
    *,
    office_id=None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    case_id=None,
    detail: dict | None = None,
    request: Request | None = None,
) -> None:
    """Add an audit entry in the caller's transaction. Never put case content in detail."""
    db.add(
        AuditLog(
            office_id=office_id or (user.office_id if user else None),
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            case_id=case_id,
            detail=detail,
            ip=request.client.host if request and request.client else None,
            at=utcnow(),
        )
    )
