"""AI behind one interface. Every task returns a JSON dict; outputs are drafts until a person approves them.

Tasks: document_summary, hearing_record, client_message, consultation, daily_summary, ask.
FakeAI is deterministic and used in development and tests. OpenAIAI is the live adapter (needs OPENAI_API_KEY)
and has not been exercised against the real service in this repository's tests.
"""

import json
import re
from typing import Protocol

import httpx

from ..config import get_settings

SYSTEM = (
    "You assist an Indian advocate's office. Reply with one JSON object only. Use only the facts given. "
    "If something is not stated, use null. Never invent section numbers, dates or case details."
)

SCHEMAS = {
    "document_summary": '{"summary": str, "dates": [{"date": "YYYY-MM-DD", "what": str, "page": int|null}], '
    '"parties": [{"name": str, "page": int|null}], "sections": [{"ref": str, "page": int|null}], "orders": [str]}',
    "hearing_record": '{"outcome": str, "next_date": "YYYY-MM-DD"|null, "directions": [{"text": str, '
    '"due_date": "YYYY-MM-DD"|null}], "tasks": [{"text": str, "due_date": "YYYY-MM-DD"|null}], "notes": str}',
    "client_message": '{"body": str}  (plain, kind language of the requested language, no legal jargon)',
    "consultation": '{"facts": [str], "issues": [str], "parties": [str], "dates": [{"date": str, "what": str}], '
    '"documents_needed": [str], "next_steps": [str]}',
    "daily_summary": '{"body": str}',
    "ask": '{"answer": str, "sources": [{"type": "case"|"hearing"|"task"|"document", "id": str}]}',
}


class AI(Protocol):
    def run(self, task: str, payload: dict) -> dict: ...


class FakeAI:
    """Deterministic stand-in. Pulls simple facts out of the text so the review flow can be tested."""

    def run(self, task: str, payload: dict) -> dict:
        text = payload.get("text", "") or ""
        dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if task == "document_summary":
            pages = payload.get("pages") or []
            return {
                "summary": (text[:200] or "No text found").strip(),
                "dates": [{"date": d, "what": "Date in document", "page": 1 if pages else None} for d in dates[:5]],
                "parties": [],
                "sections": [],
                "orders": [],
            }
        if task == "hearing_record":
            nxt = dates[-1] if dates else None
            directions = [
                {"text": ln.strip()[:200], "due_date": nxt}
                for ln in re.split(r"[.\n]", text)
                if re.search(r"\b(directed|to file|shall|must)\b", ln, re.I)
            ]
            return {
                "outcome": text[:160].strip() or "Adjourned",
                "next_date": nxt,
                "directions": directions,
                "tasks": [{"text": d["text"], "due_date": d["due_date"]} for d in directions],
                "notes": "",
            }
        if task == "client_message":
            lang = payload.get("language", "en")
            facts = payload.get("facts", {})
            if lang == "ml":
                return {"body": f"നിങ്ങളുടെ കേസ് {facts.get('title', '')}: അടുത്ത തീയതി {facts.get('next_date') or 'പിന്നീട് അറിയിക്കും'}."}
            return {"body": f"Your case {facts.get('title', '')}: next date is {facts.get('next_date') or 'to be confirmed'}."}
        if task == "consultation":
            lines = [ln.strip("-• ").strip() for ln in text.splitlines() if ln.strip()]
            return {
                "facts": lines[:5],
                "issues": [],
                "parties": [],
                "dates": [{"date": d, "what": "Mentioned"} for d in dates],
                "documents_needed": [],
                "next_steps": [],
            }
        if task == "daily_summary":
            items = payload.get("items", [])
            return {"body": f"{len(items)} activities today." + "".join(f"\n- {i}" for i in items[:20])}
        if task == "ask":
            ctx = payload.get("context", [])
            q = (payload.get("question") or "").lower()
            hits = [c for c in ctx if any(w in json.dumps(c).lower() for w in q.split() if len(w) > 3)]
            if not hits:
                return {"answer": "I could not find that in the cases you can access.", "sources": []}
            return {
                "answer": "Found: " + "; ".join(h.get("label", "") for h in hits[:5]),
                "sources": [{"type": h["type"], "id": h["id"]} for h in hits[:5]],
            }
        raise ValueError(f"unknown task {task}")


class OpenAIAI:
    def __init__(self, key: str, model: str):
        self.key, self.model = key, model

    def run(self, task: str, payload: dict) -> dict:
        user = f"Task: {task}\nReturn JSON shaped like: {SCHEMAS[task]}\nInput:\n{json.dumps(payload, ensure_ascii=False)}"
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "model": self.model,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                "temperature": 0.1,
            },
            timeout=90,
        )
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])


def get_ai() -> AI:
    s = get_settings()
    if s.ai_provider == "openai":
        if not s.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        return OpenAIAI(s.openai_api_key, s.openai_model)
    return FakeAI()
