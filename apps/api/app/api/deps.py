from datetime import timedelta
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AuthSession, Office, User
from ..permissions import has
from ..services.security import aware, read_token, utcnow


class Principal:
    def __init__(self, user: User, session: AuthSession, request: Request):
        self.user, self.session, self.request = user, session, request


def _unauthorised(msg: str = "Not signed in") -> HTTPException:
    return HTTPException(401, msg, headers={"WWW-Authenticate": "Bearer"})


def principal_allow_limited(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Principal:
    """Checks the token, the live session and the user on every request, so deactivation is immediate."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorised()
    claims = read_token(authorization[7:])
    if not claims:
        raise _unauthorised("Session is not valid")
    try:
        session = db.get(AuthSession, UUID(claims["sid"]))
        user = db.get(User, UUID(claims["sub"]))
    except (KeyError, ValueError):
        raise _unauthorised("Session is not valid") from None
    if not session or session.revoked_at or not user or not user.is_active:
        raise _unauthorised("Session has ended")
    s = get_settings()
    idle = timedelta(minutes=s.web_idle_minutes) if session.kind == "web" else timedelta(days=s.mobile_idle_days)
    now = utcnow()
    if now - aware(session.last_seen_at) > idle:
        session.revoked_at = now
        db.commit()
        raise _unauthorised("Session expired after inactivity")
    session.last_seen_at = now
    db.commit()
    return Principal(user, session, request)


def current(p: Principal = Depends(principal_allow_limited)) -> Principal:
    if p.session.limited:
        raise HTTPException(403, "Set up two-factor sign-in to continue")
    return p


def require(permission: str):
    def dep(p: Principal = Depends(current)) -> Principal:
        if not has(p.user.role, permission):
            raise HTTPException(403, "Your role cannot do this")
        return p

    return dep


def office_of(db: Session, user: User) -> Office:
    return db.get(Office, user.office_id)


def require_any(*permissions: str):
    def dep(p: Principal = Depends(current)) -> Principal:
        if not any(has(p.user.role, x) for x in permissions):
            raise HTTPException(403, "Your role cannot do this")
        return p

    return dep
