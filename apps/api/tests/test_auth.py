from datetime import timedelta

import pyotp
from sqlalchemy import select

from app.models import AuditLog, AuthSession, Office, User
from app.seed import DEV_PASSWORD
from app.services import mailer
from app.services.security import utcnow

MENON, IYER, MEERA = "menon@example.in", "iyer@example.in", "meera@example.in"


def test_login_success_and_me(client, login):
    r = login(MENON)
    assert r.status_code == 200 and r.json()["user"]["role"] == "director"
    me = client.get("/api/auth/me", headers=login.headers(MENON)).json()
    assert "audit.read" in me["permissions"] and me["idle_minutes"] == 30


def test_wrong_password_and_unknown_user_look_the_same(login):
    a, b = login(MENON, "wrong-password-1"), login("nobody@example.in")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_lockout_after_five_failures(login):
    for _ in range(5):
        assert login(MENON, "wrong-password-1").status_code == 401
    assert login(MENON).status_code == 429  # even the right password waits


def test_inactive_user_cannot_sign_in_and_live_session_ends(client, login, seeded):
    h = login.headers(IYER)
    assert client.get("/api/cases", headers=h).status_code == 200
    seeded.scalar(select(User).where(User.email == IYER)).is_active = False
    seeded.commit()
    assert client.get("/api/cases", headers=h).status_code == 401  # AUT-02: ends at once
    assert login(IYER).status_code == 401


def test_web_session_expires_after_30_minutes_idle_but_mobile_does_not(client, login, seeded):
    web, mob = login.headers(MENON), login.headers(MENON, client="mobile")
    for s in seeded.scalars(select(AuthSession)):
        s.last_seen_at = utcnow() - timedelta(minutes=31)
    seeded.commit()
    assert client.get("/api/auth/me", headers=web).status_code == 401
    assert client.get("/api/auth/me", headers=mob).status_code == 200


def test_activity_keeps_a_web_session_alive(client, login, seeded):
    h = login.headers(MENON)
    for s in seeded.scalars(select(AuthSession)):
        s.last_seen_at = utcnow() - timedelta(minutes=29)
    seeded.commit()
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 200


def test_logout_ends_session(client, login):
    h = login.headers(MENON)
    assert client.post("/api/auth/logout", headers=h).status_code == 204
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_no_token_or_bad_token(client, seeded):
    assert client.get("/api/cases").status_code == 401
    assert client.get("/api/cases", headers={"Authorization": "Bearer nope"}).status_code == 401


# ---------- two-factor
def _enrol(client, h):
    secret = client.post("/api/auth/mfa/setup", headers=h).json()["secret"]
    r = client.post("/api/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=h)
    assert r.status_code == 200
    return secret


def test_two_factor_is_off_by_default(login, seeded):
    assert seeded.scalar(select(Office)).mfa_roles == []
    assert login(MENON).json().get("mfa_required") is None


def test_enrolled_user_needs_the_code(client, login):
    secret = _enrol(client, login.headers(MENON))
    assert login(MENON).json() == {"mfa_required": True}
    assert login(MENON, otp="000000").status_code == 401
    assert login(MENON, otp=pyotp.TOTP(secret).now()).status_code == 200


def test_director_can_require_two_factor_for_a_role(client, login):
    d = login.headers(MENON)
    assert client.put("/api/settings/security/mfa-roles", json={"roles": ["junior"]}, headers=d).status_code == 200
    r = login(MEERA)
    assert r.json()["mfa_enrollment_required"] is True
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/cases", headers=h).status_code == 403  # blocked until enrolled
    _enrol(client, h)
    assert client.get("/api/cases", headers=h).status_code == 200
    assert client.post("/api/auth/mfa/disable", json={"code": "123456"}, headers=h).status_code == 403


def test_only_director_can_change_two_factor_rules(client, login):
    r = client.put("/api/settings/security/mfa-roles", json={"roles": ["clerk"]}, headers=login.headers(IYER))
    assert r.status_code == 403
    r = client.put("/api/settings/security/mfa-roles", json={"roles": ["wizard"]}, headers=login.headers(MENON))
    assert r.status_code == 422


# ---------- password reset
def _reset_token():
    return mailer.outbox[-1]["body"].split("token=")[1]


def test_reset_link_is_single_use_and_ends_sessions(client, login):
    mailer.outbox.clear()
    old = login.headers(IYER)
    assert client.post("/api/auth/password/forgot", json={"email": IYER}).status_code == 202
    token = _reset_token()
    r = client.post("/api/auth/password/reset", json={"token": token, "new_password": "A-new-passphrase-9"})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert login(IYER).status_code == 401 and login(IYER, "A-new-passphrase-9").status_code == 200
    again = client.post("/api/auth/password/reset", json={"token": token, "new_password": "Another-passphrase-9"})
    assert again.status_code == 400


def test_reset_link_expires(client, seeded):
    mailer.outbox.clear()
    client.post("/api/auth/password/forgot", json={"email": IYER})
    token = _reset_token()
    from app.models import PasswordReset

    seeded.scalar(select(PasswordReset)).expires_at = utcnow() - timedelta(minutes=1)
    seeded.commit()
    r = client.post("/api/auth/password/reset", json={"token": token, "new_password": "A-new-passphrase-9"})
    assert r.status_code == 400


def test_forgot_does_not_reveal_whether_an_email_exists(client, seeded):
    mailer.outbox.clear()
    a = client.post("/api/auth/password/forgot", json={"email": "nobody@example.in"})
    b = client.post("/api/auth/password/forgot", json={"email": IYER})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert len(mailer.outbox) == 1


def test_weak_password_is_refused(client, seeded):
    mailer.outbox.clear()
    client.post("/api/auth/password/forgot", json={"email": IYER})
    r = client.post("/api/auth/password/reset", json={"token": _reset_token(), "new_password": "short"})
    assert r.status_code == 422


# ---------- audit
def test_audit_records_sign_ins_and_filters(client, login, seeded):
    login(MENON, "wrong-password-1")
    d = login.headers(MENON)
    actions = {a["action"] for a in client.get("/api/audit", headers=d).json()["items"]}
    assert {"auth.login", "auth.login_failed"} <= actions
    only_fail = client.get("/api/audit?action=auth.login_failed", headers=d).json()
    assert only_fail["total"] == 1
    wild = client.get("/api/audit?action=auth.*", headers=d).json()["total"]
    assert wild >= 2
    uid = str(seeded.scalar(select(User).where(User.email == MENON)).id)
    assert all(i["user_id"] == uid for i in client.get(f"/api/audit?user_id={uid}", headers=d).json()["items"])


def test_audit_cannot_be_changed_through_the_application(seeded):
    import pytest

    from app.services.audit import audit

    audit(seeded, "test.entry")
    seeded.commit()
    row = seeded.scalar(select(AuditLog).where(AuditLog.action == "test.entry"))
    row.action = "tampered"
    with pytest.raises(PermissionError):
        seeded.commit()
    seeded.rollback()
    seeded.delete(seeded.scalar(select(AuditLog).where(AuditLog.action == "test.entry")))
    with pytest.raises(PermissionError):
        seeded.commit()
    seeded.rollback()


def test_permission_change_is_audited(client, login):
    d = login.headers(MENON)
    client.put("/api/settings/security/mfa-roles", json={"roles": ["clerk"]}, headers=d)
    items = client.get("/api/audit?action=settings.*", headers=d).json()["items"]
    assert items and items[0]["detail"] == {"before": [], "after": ["clerk"]}


def test_audit_log_is_director_only(client, login):
    for email in (IYER, MEERA, "suresh@example.in", "anita@example.in", "ramesh@example.in", "a.sharma@example.in"):
        assert client.get("/api/audit", headers=login.headers(email)).status_code == 403, email
    assert DEV_PASSWORD  # sample password only
