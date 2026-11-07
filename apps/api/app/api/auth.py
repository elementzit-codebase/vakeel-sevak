from datetime import timedelta

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AuthSession, PasswordReset, User
from ..permissions import PERMISSIONS
from ..services import mailer
from ..services.audit import audit
from ..services.security import (
    aware,
    digest,
    hash_password,
    new_token,
    password_problem,
    random_token,
    utcnow,
    verify_password,
)
from .deps import Principal, current, office_of, principal_allow_limited

router = APIRouter(prefix="/auth", tags=["auth"])
GENERIC = "Email or password is not correct"


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    otp: str | None = None
    client: str = "web"  # "web" or "mobile"


def user_view(db: Session, u: User) -> dict:
    return {
        "id": str(u.id),
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "language": u.language,
        "permissions": sorted(PERMISSIONS.get(u.role, set())),
        "totp_enabled": u.totp_enabled,
        "idle_minutes": get_settings().web_idle_minutes,
    }


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    now = utcnow()
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not user.is_active:
        audit(db, "auth.login_failed", None, detail={"reason": "unknown_or_inactive"}, request=request)
        db.commit()
        raise HTTPException(401, GENERIC)
    if user.locked_until and aware(user.locked_until) > now:
        audit(db, "auth.login_blocked", user, request=request)
        db.commit()
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")

    def fail(reason: str):
        user.failed_logins += 1
        if user.failed_logins >= s.max_failed_logins:
            user.locked_until = now + timedelta(minutes=s.lockout_minutes)
            user.failed_logins = 0
        audit(db, "auth.login_failed", user, detail={"reason": reason}, request=request)
        db.commit()
        raise HTTPException(401, GENERIC)

    if not verify_password(body.password, user.password_hash):
        fail("password")
    if user.totp_enabled:
        if not body.otp:
            return {"mfa_required": True}
        if not pyotp.TOTP(user.totp_secret).verify(body.otp, valid_window=1):
            fail("otp")

    office = office_of(db, user)
    needs_enrol = user.role in (office.mfa_roles or []) and not user.totp_enabled
    user.failed_logins, user.locked_until = 0, None
    session = AuthSession(
        user_id=user.id,
        kind="mobile" if body.client == "mobile" else "web",
        created_at=now,
        last_seen_at=now,
        limited=needs_enrol,
    )
    db.add(session)
    db.flush()
    audit(db, "auth.login", user, detail={"client": session.kind}, request=request)
    db.commit()
    return {
        "access_token": new_token(user.id, session.id),
        "token_type": "bearer",
        "mfa_enrollment_required": needs_enrol,
        "user": user_view(db, user),
    }


@router.get("/me")
def me(p: Principal = Depends(principal_allow_limited), db: Session = Depends(get_db)):
    return {**user_view(db, p.user), "mfa_enrollment_required": p.session.limited}


@router.post("/logout", status_code=204)
def logout(p: Principal = Depends(principal_allow_limited), db: Session = Depends(get_db)):
    p.session.revoked_at = utcnow()
    audit(db, "auth.logout", p.user, request=p.request)
    db.commit()


class CodeIn(BaseModel):
    code: str


@router.post("/mfa/setup")
def mfa_setup(p: Principal = Depends(principal_allow_limited), db: Session = Depends(get_db)):
    if p.user.totp_enabled:
        raise HTTPException(409, "Two-factor sign-in is already on")
    p.user.totp_secret = pyotp.random_base32()
    db.commit()
    uri = pyotp.TOTP(p.user.totp_secret).provisioning_uri(p.user.email, issuer_name=get_settings().product_name)
    return {"secret": p.user.totp_secret, "otpauth_uri": uri}


@router.post("/mfa/enable")
def mfa_enable(body: CodeIn, p: Principal = Depends(principal_allow_limited), db: Session = Depends(get_db)):
    if not p.user.totp_secret or not pyotp.TOTP(p.user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(400, "That code is not correct")
    p.user.totp_enabled = True
    p.session.limited = False
    audit(db, "auth.mfa_enabled", p.user, request=p.request)
    db.commit()
    return {"totp_enabled": True}


@router.post("/mfa/disable")
def mfa_disable(body: CodeIn, p: Principal = Depends(current), db: Session = Depends(get_db)):
    if p.user.role in (office_of(db, p.user).mfa_roles or []):
        raise HTTPException(403, "Your office requires two-factor sign-in for your role")
    if not p.user.totp_enabled or not pyotp.TOTP(p.user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(400, "That code is not correct")
    p.user.totp_enabled, p.user.totp_secret = False, None
    audit(db, "auth.mfa_disabled", p.user, request=p.request)
    db.commit()
    return {"totp_enabled": False}


class ForgotIn(BaseModel):
    email: EmailStr


@router.post("/password/forgot", status_code=202)
def forgot(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    """Always answers the same, so the form cannot be used to find out who has an account."""
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.is_active:
        token = random_token()
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=digest(token),
                expires_at=utcnow() + timedelta(minutes=get_settings().reset_link_minutes),
            )
        )
        audit(db, "auth.reset_requested", user, request=request)
        db.commit()
        mailer.send(
            user.email,
            f"Reset your {get_settings().product_name} password",
            f"Use this one-time link within {get_settings().reset_link_minutes} minutes: /reset?token={token}",
        )
    return {"status": "If that email has an account, a reset link has been sent."}


class ResetIn(BaseModel):
    token: str
    new_password: str


@router.post("/password/reset")
def reset(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    row = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == digest(body.token)))
    if not row or row.used_at or aware(row.expires_at) < utcnow():
        raise HTTPException(400, "This reset link is not valid or has expired")
    user = db.get(User, row.user_id)
    problem = password_problem(body.new_password, user.email)
    if problem:
        raise HTTPException(422, problem)
    user.password_hash = hash_password(body.new_password)
    user.failed_logins, user.locked_until = 0, None
    row.used_at = utcnow()
    for sess in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))):
        sess.revoked_at = utcnow()
    audit(db, "auth.password_reset", user, request=request)
    db.commit()
    return {"status": "Password changed. Sign in with the new password."}
