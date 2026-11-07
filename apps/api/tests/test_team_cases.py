import io
from datetime import datetime, timedelta, timezone

from app.services import mailer

D, A, J, C, ACC, H = ("menon", "iyer", "meera", "suresh", "anita", "ramesh")


def hdr(login, who):
    return login.headers(f"{who}@example.in")


def test_director_creates_user_and_invite_is_emailed(client, login):
    h = hdr(login, D)
    mailer.outbox.clear()
    r = client.post("/api/users", headers=h, json={"name": "New Clerk", "email": "new@example.in", "role": "clerk"})
    assert r.status_code == 201
    assert any(m["to"] == "new@example.in" and "/reset?token=" in m["body"] for m in mailer.outbox)
    assert client.post("/api/users", headers=h, json={"name": "x", "email": "new@example.in", "role": "clerk"}).status_code == 409
    assert client.get("/api/users", headers=hdr(login, A)).status_code == 403


def test_last_director_cannot_be_removed_and_deactivation_ends_sessions(client, login):
    h = hdr(login, D)
    users = {u["email"]: u for u in client.get("/api/users", headers=h).json()["items"]}
    me = users["menon@example.in"]["id"]
    assert client.patch(f"/api/users/{me}", headers=h, json={"is_active": False}).status_code == 409
    assert client.patch(f"/api/users/{me}", headers=h, json={"role": "advocate"}).status_code == 409
    sid = users["suresh@example.in"]["id"]
    hs = hdr(login, C)
    assert client.get("/api/cases", headers=hs).status_code == 200
    assert client.patch(f"/api/users/{sid}", headers=h, json={"is_active": False}).status_code == 200
    assert client.get("/api/cases", headers=hs).status_code == 401


def test_assignment_controls_visibility(client, login):
    h = hdr(login, D)
    cases = client.get("/api/cases", headers=h).json()["items"]
    pillai = next(c for c in cases if "Pillai" in c["title"])
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=h).json()["items"]}
    hs = hdr(login, C)
    assert client.get(f"/api/cases/{pillai['id']}", headers=hs).status_code == 404
    r = client.put(f"/api/cases/{pillai['id']}/assignments", headers=h, json={"user_ids": [users["suresh@example.in"]]})
    assert r.status_code == 200
    assert client.get(f"/api/cases/{pillai['id']}", headers=hs).status_code == 200


def test_firm_settings_default_off_for_clients(client, login):
    h = hdr(login, D)
    f = client.get("/api/settings/firm", headers=h).json()
    assert f["client_comms"]["enabled"] is False and f["reminder_offsets"] == [7, 3, 1, 0]
    assert client.put("/api/settings/firm", headers=hdr(login, A), json={"reminder_offsets": [1]}).status_code == 403
    r = client.put("/api/settings/firm", headers=h, json={"reminder_offsets": [5, 1]})
    assert r.json()["reminder_offsets"] == [5, 1]
    assert client.put("/api/settings/firm", headers=h, json={"reminder_offsets": [99]}).status_code == 422


def test_create_case_search_and_creator_can_open(client, login):
    h = hdr(login, A)
    cl = client.get("/api/clients", headers=h).json()["items"][0]
    r = client.post("/api/cases", headers=h, json={
        "title": "Kumar v. Kumar", "case_number": "M.C. 5/2026", "court": "Family Court", "client_id": cl["id"],
        "parties": [{"name": "Lakshmi Kumar", "role": "respondent"}]})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert client.get(f"/api/cases/{cid}", headers=h).json()["parties"][0]["name"] == "Lakshmi Kumar"
    assert client.get("/api/cases?q=lakshmi", headers=h).json()["total"] == 1  # search by party name
    assert client.get(f"/api/cases/{cid}", headers=hdr(login, J)).status_code == 404  # not assigned
    assert client.post("/api/cases", headers=hdr(login, ACC), json={}).status_code == 403


def test_client_360_hides_cases_user_cannot_see(client, login):
    h = hdr(login, D)
    cl = next(c for c in client.get("/api/clients", headers=h).json()["items"] if "Sharma" in c["name"])
    full = client.get(f"/api/clients/{cl['id']}", headers=h).json()
    assert len(full["cases"]) == 1
    # Accountant has clients.read but no case access: sees the client and the balance, no cases.
    acc = client.get(f"/api/clients/{cl['id']}", headers=hdr(login, ACC)).json()
    assert acc["cases"] == [] and "balance" in acc


def test_hearing_clash_is_a_warning(client, login):
    h = hdr(login, D)
    cases = client.get("/api/cases", headers=h).json()["items"]
    when = (datetime.now(timezone.utc) + timedelta(days=40)).replace(hour=10, minute=0, second=0, microsecond=0)
    a = client.post(f"/api/cases/{cases[0]['id']}/hearings", headers=h, json={"hearing_at": when.isoformat()})
    assert a.status_code == 201 and a.json()["clashes"] == []
    b = client.post(f"/api/cases/{cases[1]['id']}/hearings", headers=h,
                    json={"hearing_at": (when + timedelta(minutes=30)).isoformat()})
    assert b.status_code == 201 and len(b.json()["clashes"]) == 1


def test_import_preview_then_commit(client, login):
    h = hdr(login, D)
    csv = (
        "Title,Case Number,Court,Client,Next Date\n"
        "Gopal v. Bank,O.S. 11/2026,District Court,Gopal,15-12-2026\n"
        "Bad row,,District Court,Gopal,\n"
        "Dup,O.S. 1234/2024,City Civil Court,Someone,\n"
    )
    r = client.post("/api/import/preview", headers=h, files={"file": ("cases.csv", io.BytesIO(csv.encode()), "text/csv")})
    body = r.json()
    assert (body["ok"], body["skip"], body["errors"]) == (1, 1, 1)
    before = client.get("/api/cases", headers=h).json()["total"]
    c = client.post("/api/import/commit", headers=h, json={"rows": [x["data"] for x in body["rows"]]}).json()
    assert c == {"created": 1, "skipped": 2}
    assert client.get("/api/cases", headers=h).json()["total"] == before + 1
    assert client.post("/api/import/preview", headers=hdr(login, C),
                       files={"file": ("a.csv", io.BytesIO(b"x"), "text/csv")}).status_code == 403


def test_directions_become_tasks_and_alerts(client, login):
    h = hdr(login, D)
    cid = client.get("/api/cases", headers=h).json()["items"][0]["id"]
    r = client.post(f"/api/cases/{cid}/directions", headers=h, json={"text": "File reply", "due_date": "2020-01-01"})
    assert r.status_code == 201
    tasks = client.get(f"/api/tasks?case_id={cid}", headers=h).json()["items"]
    assert any(t["source"] == "direction" and t["title"] == "File reply" for t in tasks)
    today = client.get("/api/today", headers=h).json()
    assert any(a["rule"] == "overdue_direction" for a in today["alerts"])
    assert any(t["overdue"] for t in today["tasks"])
    tid = r.json()["task_id"]
    assert client.patch(f"/api/tasks/{tid}", headers=h, json={"done": True}).json()["done"] is True


def test_task_visibility_follows_case_access(client, login):
    h = hdr(login, D)
    cases = client.get("/api/cases", headers=h).json()["items"]
    pillai = next(c for c in cases if "Pillai" in c["title"])
    t = client.post("/api/tasks", headers=h, json={"title": "Secret prep", "case_id": pillai["id"]}).json()
    # Suresh is not assigned to Pillai; the task must not appear for him.
    ids = [x["id"] for x in client.get("/api/tasks", headers=hdr(login, C)).json()["items"]]
    assert t["id"] not in ids
    assert client.patch(f"/api/tasks/{t['id']}", headers=hdr(login, C), json={"done": True}).status_code == 404


def test_today_for_helper_has_only_own_tasks(client, login):
    h = hdr(login, D)
    users = {u["email"]: u["id"] for u in client.get("/api/users", headers=h).json()["items"]}
    client.post("/api/tasks", headers=h, json={"title": "Photocopy", "assignee_id": users["ramesh@example.in"]})
    t = client.get("/api/today", headers=hdr(login, H)).json()
    assert [x["title"] for x in t["tasks"]] == []  # no due date, so not due today
    mine = client.get("/api/tasks", headers=hdr(login, H)).json()["items"]
    assert [x["title"] for x in mine] == ["Photocopy"]
    assert t["alerts"] == []
