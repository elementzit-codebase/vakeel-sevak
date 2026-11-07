import io
from datetime import date

from app.api.intel import load_statutes


def H(login, who):
    return login.headers(f"{who}@example.in")


def case_id(client, h, name):
    return next(c for c in client.get("/api/cases", headers=h).json()["items"] if name in c["title"])["id"]


def test_alerts_flag_cases_without_next_date(client, login):
    h = H(login, "menon")
    cid = case_id(client, h, "Pillai")
    d = client.get("/api/cases/" + cid, headers=h).json()
    # Mark Pillai's only hearing as held: now there is no next date.
    client.patch(f"/api/hearings/{d['hearings'][0]['id']}", headers=h, json={"status": "held"})
    rules = {(a["title"], a["rule"]) for a in client.get("/api/alerts", headers=h).json()["items"]}
    assert ("Pillai Estate matter", "no_next_date") in rules
    assert client.get("/api/alerts", headers=H(login, "anita")).status_code == 403


def test_statutes_search_map_and_unverified_flag(client, login, seeded):
    load_statutes(seeded, "act,number,title,text,verified\nBNS,103,Murder,,false\nBNS,318,Cheating,,true\n",
                  "old_act,old_number,new_act,new_number,note,verified\nIPC,302,BNS,103,,false\n")
    h = H(login, "iyer")
    r = client.get("/api/statutes/search?q=murder", headers=h).json()["items"]
    assert r[0]["number"] == "103" and r[0]["warning"]
    ver = client.get("/api/statutes/search?q=318", headers=h).json()["items"][0]
    assert ver["verified"] and ver["warning"] is None
    m = client.get("/api/statutes/map?act=IPC&number=302", headers=h).json()["items"][0]
    assert m["new"] == "BNS 103" and m["warning"]
    assert client.get("/api/statutes/map?act=BNS&number=103", headers=h).json()["items"][0]["old"] == "IPC 302"
    up = client.post("/api/statutes/import", headers=H(login, "iyer"), files={"sections": ("s.csv", io.BytesIO(b"x"), "text/csv")})
    assert up.status_code == 403
    up = client.post("/api/statutes/import", headers=H(login, "menon"),
                     files={"sections": ("s.csv", io.BytesIO(b"act,number,title,text,verified\nBNSS,173,FIR,,false\n"), "text/csv")})
    assert up.json() == {"sections": 1, "mappings": 0}


def test_consultation_flow_to_case(client, login):
    h = H(login, "iyer")
    c = client.post("/api/consultations", headers=h, json={"raw_notes": "- Tenant not paying since 2026-01-05\n- Wants eviction"}).json()
    assert c["status"] == "draft" and c["structured"]["facts"]
    assert client.get("/api/consultations", headers=H(login, "meera")).json()["items"] == []  # others' notes are private
    assert client.get("/api/consultations", headers=H(login, "menon")).json()["items"][0]["id"] == c["id"]
    cl = client.get("/api/clients", headers=h).json()["items"][0]["id"]
    body = {"title": "Landlord v. Tenant", "case_number": "R.C. 1/2026", "court": "Rent Court", "client_id": cl}
    assert client.post(f"/api/consultations/{c['id']}/create-case", headers=h, json=body).status_code == 409
    client.post(f"/api/consultations/{c['id']}/confirm", headers=h)
    assert client.post(f"/api/consultations/{c['id']}/create-case", headers=h, json=body).status_code == 201


def test_fee_ledger_receipt_numbers_balance_and_notice(client, login):
    acc = H(login, "anita")
    cl = next(c for c in client.get("/api/clients", headers=acc).json()["items"] if "Sharma" in c["name"])["id"]
    today = date.today().isoformat()
    for kind, amt in (("fee", 500000), ("expense", 25000), ("received", 200000), ("received", 100000)):
        body = {"kind": kind, "amount_paise": amt, "entry_date": today, "mode": "upi"}
        assert client.post(f"/api/clients/{cl}/fees", headers=acc, json=body).status_code == 201
    led = client.get(f"/api/clients/{cl}/fees", headers=acc).json()
    assert led["balance"] == {"billed_paise": 525000, "received_paise": 300000, "due_paise": 225000}
    nos = [e["receipt_no"] for e in led["items"] if e["receipt_no"]]
    assert nos == [f"VS/{date.today().year}/0001", f"VS/{date.today().year}/0002"]
    rid = next(e["id"] for e in led["items"] if e["receipt_no"])
    pdf = client.get(f"/api/fees/{rid}/receipt.pdf", headers=acc)
    assert pdf.content[:4] == b"%PDF"
    n = client.post(f"/api/clients/{cl}/fee-notice", headers=acc).json()
    assert "2,250.00" in n["body"]
    assert client.post(f"/api/messages/{n['id']}/approve", headers=acc).status_code == 403  # accountant cannot approve
    assert client.post(f"/api/messages/{n['id']}/approve", headers=H(login, "menon")).status_code == 200
    assert client.get("/api/fees/summary", headers=acc).json()["total_due_paise"] == 225000


def test_fees_hidden_from_roles_without_permission(client, login):
    cl = client.get("/api/clients", headers=H(login, "menon")).json()["items"][0]["id"]
    for who in ("meera", "suresh", "ramesh"):
        assert client.get(f"/api/clients/{cl}/fees", headers=H(login, who)).status_code == 403
    bad = client.post(f"/api/clients/{cl}/fees", headers=H(login, "anita"),
                      json={"kind": "fee", "amount_paise": 0, "entry_date": "2026-01-01"})
    assert bad.status_code == 422


def test_share_link_off_by_default_expires_and_shows_little(client, login):
    h = H(login, "menon")
    cid = case_id(client, h, "Sharma")
    assert client.post(f"/api/cases/{cid}/share", headers=h, json={}).status_code == 403
    client.put("/api/settings/firm", headers=h, json={"client_comms": {"enabled": True}})
    url = client.post(f"/api/cases/{cid}/share", headers=h, json={"days": 7}).json()["url"]
    token = url.rsplit("/", 1)[1]
    pub = client.get(f"/api/public/status/{token}")
    assert pub.status_code == 200 and set(pub.json()) == {"title", "case_number", "court", "stage", "next_hearing", "office"}
    assert client.get("/api/public/status/not-a-token").status_code == 404
    client.delete(f"/api/cases/{cid}/share", headers=h)
    assert client.get(f"/api/public/status/{token}").status_code == 404


def test_client_chat_is_scoped_to_own_case_and_policy(client, login):
    h = H(login, "menon")
    cid = case_id(client, h, "Sharma")
    other = case_id(client, h, "Rao")
    cl = login.headers("a.sharma@example.in")
    assert client.post(f"/api/portal/cases/{cid}/chat", headers=cl, json={"body": "Hello"}).status_code == 403  # off
    client.put("/api/settings/firm", headers=h, json={"client_comms": {"enabled": True}})
    assert client.post(f"/api/portal/cases/{cid}/chat", headers=cl, json={"body": "When is the next date?"}).status_code == 201
    assert client.post(f"/api/portal/cases/{other}/chat", headers=cl, json={"body": "x"}).status_code == 404
    assert client.post(f"/api/cases/{cid}/chat", headers=h, json={"body": "On 20 Dec."}).status_code == 201
    msgs = client.get(f"/api/portal/cases/{cid}/chat", headers=cl).json()["items"]
    assert [m["from_client"] for m in msgs] == [True, False]
    assert client.post(f"/api/cases/{cid}/chat", headers=H(login, "meera"), json={"body": "hi"}).status_code == 403
    assert client.get("/api/cases", headers=cl).status_code == 403  # a client never uses the staff API


def test_daily_log_and_summary_need_approval(client, login):
    h = H(login, "menon")
    client.post("/api/tasks", headers=h, json={"title": "Prepare bundle"})
    day = date.today().isoformat()
    log = client.get(f"/api/daily/{day}", headers=h).json()
    assert any(i["action"] == "task.create" for i in log["items"]) and log["summary"] is None
    s = client.post(f"/api/daily/{day}/summary", headers=h).json()
    assert s["status"] == "draft" and "activities" in s["body"]
    assert client.post(f"/api/daily/{day}/approve", headers=h).json()["status"] == "approved"
    assert client.post(f"/api/daily/{day}/summary", headers=h).status_code == 409
    assert client.get(f"/api/daily/{day}", headers=H(login, "iyer")).status_code == 403


def test_ask_only_sees_what_user_may_see_and_is_logged(client, login):
    pill = "Pillai"
    assert client.post("/api/ask", headers=H(login, "menon"), json={"question": "Where is the Pillai matter?"}).json()["sources"]
    r = client.post("/api/ask", headers=H(login, "suresh"), json={"question": "Where is the Pillai matter?"}).json()
    assert r["sources"] == [] and "could not find" in r["answer"]  # clerk is not assigned to Pillai
    hist = client.get("/api/ask/history", headers=H(login, "menon")).json()["items"]
    assert any(pill in x["question"] for x in hist)
    assert client.post("/api/ask", headers=H(login, "ramesh"), json={"question": "anything at all"}).status_code == 403
