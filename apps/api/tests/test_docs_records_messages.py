import io
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.services import mailer, push
from app.services import reminders as rem

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture(autouse=True)
def uploads(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setattr(get_settings(), "upload_dir", d)


def H(login, who):
    return login.headers(f"{who}@example.in")


def first_case(client, h, name="Sharma"):
    return next(c for c in client.get("/api/cases", headers=h).json()["items"] if name in c["title"])


def upload(client, h, cid, text="Order dated 2026-12-01. Next date 2026-12-20.", name="order.txt"):
    return client.post(f"/api/cases/{cid}/documents", headers=h,
                       files={"file": (name, io.BytesIO(text.encode()), "text/plain")}, data={"doc_type": "Order"})


def test_document_upload_search_download_audit_and_restore(client, login):
    h = H(login, "menon")
    cid = first_case(client, h)["id"]
    r = upload(client, h, cid)
    assert r.status_code == 201 and r.json()["has_text"]
    did = r.json()["id"]
    assert len(client.get(f"/api/cases/{cid}/documents?q=next date", headers=h).json()["items"]) == 1
    assert client.get(f"/api/documents/{did}/download", headers=h).content.startswith(b"Order dated")
    acts = [a["action"] for a in client.get("/api/audit?action=doc.*", headers=h).json()["items"]]
    assert "doc.upload" in acts and "doc.download" in acts
    assert client.delete(f"/api/documents/{did}", headers=h).status_code == 200
    assert client.get(f"/api/documents/{did}", headers=h).status_code == 404
    assert client.post(f"/api/documents/{did}/restore", headers=h).status_code == 200


def test_document_access_follows_case_access_and_type_rules(client, login):
    h = H(login, "menon")
    pillai = first_case(client, h, "Pillai")["id"]
    did = upload(client, h, pillai).json()["id"]
    hs = H(login, "suresh")  # clerk, not assigned to Pillai
    assert client.get(f"/api/documents/{did}", headers=hs).status_code == 404
    assert client.get(f"/api/cases/{pillai}/documents", headers=hs).status_code == 404
    bad = client.post(f"/api/cases/{pillai}/documents", headers=h,
                      files={"file": ("a.exe", io.BytesIO(b"MZ"), "application/x-msdownload")})
    assert bad.status_code == 415


def test_ai_summary_is_draft_until_an_advocate_approves(client, login):
    h = H(login, "menon")
    cid = first_case(client, h)["id"]
    did = upload(client, h, cid).json()["id"]
    s = client.post(f"/api/documents/{did}/summarize", headers=h).json()
    assert s["ai_status"] == "draft" and s["ai"]["dates"][0]["date"] == "2026-12-01"
    assert client.post(f"/api/documents/{did}/ai/approve", headers=H(login, "meera")).status_code == 403  # junior
    assert client.post(f"/api/documents/{did}/ai/approve", headers=h).json()["ai_status"] == "approved"


def make_record(client, h, cid, text):
    hearing = client.get(f"/api/cases/{cid}", headers=h).json()["hearings"][0]["id"]
    r = client.post(f"/api/hearings/{hearing}/records", headers=h, json={"text": text})
    assert r.status_code == 201
    return hearing, r.json()


def test_record_review_approve_creates_next_date_and_tasks(client, login):
    h = H(login, "menon")
    cid = first_case(client, h)["id"]
    hearing, rec = make_record(client, h, cid, "PW-2 cross-examined. Court directed to file reply. Next date 2027-01-15.")
    assert rec["status"] == "draft" and rec["draft"]["next_date"] == "2027-01-15"
    edit = {**rec["final"], "outcome": "Cross-examination done"}
    ed = client.patch(f"/api/records/{rec['id']}", headers=h, json=edit).json()
    assert ed["final"]["outcome"] == "Cross-examination done"
    assert ed["draft"]["outcome"] != "Cross-examination done"  # the AI draft is kept unchanged
    assert client.post(f"/api/records/{rec['id']}/approve", headers=H(login, "meera")).status_code in (403, 404)
    ok = client.post(f"/api/records/{rec['id']}/approve", headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    c = client.get(f"/api/cases/{cid}", headers=h).json()
    assert any(x["at"].startswith("2027-01-15") for x in c["hearings"])
    assert any(t["title"].startswith("Court directed") for t in c["open_tasks"])
    assert client.patch(f"/api/records/{rec['id']}", headers=h, json=edit).status_code == 409


def test_voice_record_uses_speech_provider(client, login):
    h = H(login, "menon")
    cid = first_case(client, h)["id"]
    hearing = client.get(f"/api/cases/{cid}", headers=h).json()["hearings"][0]["id"]
    r = client.post(f"/api/hearings/{hearing}/records/audio", headers=h,
                    files={"audio": ("a.webm", io.BytesIO(b"Adjourned. Next date 2027-02-01."), "audio/webm")},
                    data={"language": "ml"})
    assert r.status_code == 201 and r.json()["source"] == "voice" and r.json()["language"] == "ml"


def approved_message(client, h, cid):
    _, rec = make_record(client, h, cid, "Adjourned. Next date 2027-03-01.")
    client.post(f"/api/records/{rec['id']}/approve", headers=h)
    return client.post(f"/api/records/{rec['id']}/client-message", headers=h).json()


def test_client_messages_are_off_by_default_then_send(client, login):
    h = H(login, "menon")
    cid = first_case(client, h)["id"]
    m = approved_message(client, h, cid)
    assert m["status"] == "draft"
    assert client.post(f"/api/messages/{m['id']}/send", headers=h, json={"channel": "email"}).status_code in (403, 409)
    assert client.post(f"/api/messages/{m['id']}/approve", headers=h).json()["status"] == "approved"
    off = client.post(f"/api/messages/{m['id']}/send", headers=h, json={"channel": "email"})
    assert off.status_code == 403  # nothing reaches a client until a Director turns it on
    client.put("/api/settings/firm", headers=h, json={"client_comms": {"enabled": True, "channels": ["email"]}})
    mailer.outbox.clear()
    sent = client.post(f"/api/messages/{m['id']}/send", headers=h, json={"channel": "email"})
    assert sent.status_code == 200 and mailer.outbox[-1]["to"] == "a.sharma@example.in"
    wa = client.post(f"/api/messages/{m['id']}/send", headers=h, json={"channel": "whatsapp"}).json()
    assert wa["link"].startswith("https://wa.me/919876543210?text=")


def test_junior_can_draft_but_not_approve_messages(client, login):
    h = H(login, "menon")
    cid = first_case(client, h)["id"]
    m = client.post(f"/api/cases/{cid}/messages", headers=H(login, "meera"), json={"body": "Please bring documents."}).json()
    assert client.post(f"/api/messages/{m['id']}/approve", headers=H(login, "meera")).status_code == 403


def test_reminders_send_once_respect_quiet_hours_and_client_switch(client, login, seeded):
    h = H(login, "menon")
    day = datetime.now(IST).date()
    # Sharma's seeded hearing is today (offset 0). 11:00 IST is outside quiet hours.
    now = datetime(day.year, day.month, day.day, 11, 0, tzinfo=IST)
    mailer.outbox.clear()
    push.sent.clear()
    first = rem.run(seeded, now)
    assert first["email"] >= 1 and first["client_email"] == 0  # clients are off
    again = rem.run(seeded, now)
    assert again == {"email": 0, "push": 0, "client_email": 0, "deferred": 0}  # idempotent
    late = rem.run(seeded, datetime(day.year, day.month, day.day, 22, 0, tzinfo=IST))
    assert late["deferred"] == 1 and late["email"] == 0
    client.put("/api/settings/firm", headers=h, json={"client_comms": {"enabled": True, "channels": ["email"]}})
    rem_log = rem.run(seeded, now + timedelta(minutes=5))
    assert rem_log["client_email"] >= 1


def test_push_token_registration_feeds_reminders(client, login, seeded):
    h = H(login, "iyer")
    assert client.post("/api/push/register", headers=h, json={"token": "ExponentPushToken[abcdef]"}).status_code == 204
    day = datetime.now(IST).date()
    push.sent.clear()
    rem.run(seeded, datetime(day.year, day.month, day.day, 11, 0, tzinfo=IST))
    assert any(p["to"] == "ExponentPushToken[abcdef]" for p in push.sent)
