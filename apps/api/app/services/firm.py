"""Firm settings (AUT-08): courts, stage templates, reminder schedule, quiet hours, client communication policy."""

from copy import deepcopy

from sqlalchemy.orm import Session

from ..models import Office

DEFAULTS: dict = {
    "courts": ["High Court of Kerala", "District Court, Ernakulam", "Magistrate Court, Kochi"],
    "stage_templates": {
        "Civil suit": ["Filing", "Summons", "Written statement", "Issues", "Evidence", "Arguments", "Judgment"],
        "Criminal": ["FIR", "Charge sheet", "Charges", "Evidence", "Arguments", "Judgment"],
    },
    "reminder_offsets": [7, 3, 1, 0],
    "quiet_hours": {"start": "21:00", "end": "07:00"},
    # Off until a Director turns it on; nothing reaches a client before that.
    "client_comms": {"enabled": False, "channels": ["email"], "default_language": "en"},
    "inactive_days": 30,
}


def get_firm(office: Office) -> dict:
    out = deepcopy(DEFAULTS)
    for k, v in (office.settings or {}).items():
        if k in out:
            if isinstance(out[k], dict) and isinstance(v, dict):
                out[k].update(v)
            else:
                out[k] = v
    return out


def set_firm(db: Session, office: Office, patch: dict) -> dict:
    cur = dict(office.settings or {})
    cur.update({k: v for k, v in patch.items() if k in DEFAULTS})
    office.settings = cur
    db.flush()
    return get_firm(office)


def clients_enabled(office: Office) -> bool:
    return bool(get_firm(office)["client_comms"].get("enabled"))
