import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from ..config import get_settings

_hasher = PasswordHasher()


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def hash_password(pw: str) -> str:
    return _hasher.hash(pw)


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def password_problem(pw: str, email: str = "") -> str | None:
    if len(pw) < 10:
        return "Use at least 10 characters."
    if email and pw.lower() == email.lower():
        return "The password cannot be your email."
    if pw.lower() in {"password123", "1234567890", "qwertyuiop"}:
        return "That password is too common."
    return None


def new_token(user_id: uuid.UUID, session_id: uuid.UUID, hours: int = 24 * 31) -> str:
    s = get_settings()
    claims = {"sub": str(user_id), "sid": str(session_id), "exp": utcnow() + timedelta(hours=hours)}
    return jwt.encode(claims, s.secret_key, algorithm="HS256")


def read_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def random_token() -> str:
    return secrets.token_urlsafe(32)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
