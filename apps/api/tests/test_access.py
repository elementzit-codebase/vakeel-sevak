from sqlalchemy import select

from app.models import AuditLog, Case, CaseAssignment, User

MENON, IYER, MEERA = "menon@example.in", "iyer@example.in", "meera@example.in"
SURESH, ANITA, RAMESH, SHARMA = "suresh@example.in", "anita@example.in", "ramesh@example.in", "a.sharma@example.in"


def _titles(client, h):
    return {c["title"] for c in client.get("/api/cases", headers=h).json()["items"]}


def test_director_sees_all_cases(client, login):
    body = client.get("/api/cases", headers=login.headers(MENON)).json()
    assert body["total"] == 5


def test_assigned_staff_see_only_their_cases(client, login):
    assert _titles(client, login.headers(IYER)) == {"Rao Constructions v. BBMP", "Iyer v. Iyer"}
    assert _titles(client, login.headers(MEERA)) == {"Sharma v. State of Karnataka", "Pillai Estate matter"}
    assert _titles(client, login.headers(SURESH)) == {"Sharma v. State of Karnataka"}


def test_unassigned_advocate_cannot_open_or_count_a_case(client, login, seeded):
    sharma = seeded.scalar(select(Case).where(Case.case_number == "O.S. 1234/2024"))
    h = login.headers(IYER)
    assert client.get(f"/api/cases/{sharma.id}", headers=h).status_code == 404
    assert client.get("/api/cases", headers=h).json()["total"] == 2  # counts hide it too


def test_case_view_is_audited_with_the_case(client, login, seeded):
    rao = seeded.scalar(select(Case).where(Case.case_number == "W.P. 8812/2025"))
    assert client.get(f"/api/cases/{rao.id}", headers=login.headers(IYER)).status_code == 200
    row = seeded.scalar(select(AuditLog).where(AuditLog.action == "case.view"))
    assert row.case_id == rao.id


def test_roles_without_case_access_get_403(client, login):
    for email in (ANITA, RAMESH):
        assert client.get("/api/cases", headers=login.headers(email)).status_code == 403, email


def test_lower_roles_get_403_on_admin_endpoints(client, login):
    for email in (IYER, MEERA, SURESH, ANITA, RAMESH):
        h = login.headers(email)
        assert client.get("/api/settings/security", headers=h).status_code == 403, email
        assert client.put("/api/settings/security/mfa-roles", json={"roles": []}, headers=h).status_code == 403


def test_assignment_change_takes_effect_at_once(client, login, seeded):
    sharma = seeded.scalar(select(Case).where(Case.case_number == "O.S. 1234/2024"))
    iyer = seeded.scalar(select(User).where(User.email == IYER))
    h = login.headers(IYER)
    assert client.get(f"/api/cases/{sharma.id}", headers=h).status_code == 404
    seeded.add(CaseAssignment(case_id=sharma.id, user_id=iyer.id))
    seeded.commit()
    assert client.get(f"/api/cases/{sharma.id}", headers=h).status_code == 200


def test_client_signs_in_and_sees_only_own_cases_read_only(client, login):
    r = login(SHARMA)
    assert r.status_code == 200 and r.json()["user"]["role"] == "client"
    h = login.headers(SHARMA)
    items = client.get("/api/portal/cases", headers=h).json()["items"]
    assert [i["title"] for i in items] == ["Sharma v. State of Karnataka"]
    assert "next_hearing" in items[0] and "court" not in items[0]
    assert client.get("/api/cases", headers=h).status_code == 403  # the office case list is closed to clients
    assert client.get("/api/audit", headers=h).status_code == 403


def test_staff_cannot_use_the_client_portal(client, login):
    assert client.get("/api/portal/cases", headers=login.headers(MENON)).status_code == 403
