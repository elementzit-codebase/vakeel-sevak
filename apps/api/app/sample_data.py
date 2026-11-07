"""Sample dataset for demos and proof of concept. Fictional people and matters."""

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
OFFICE = "Menon and Associates"
USERS = [
    ("Adv. K. Menon", "menon@example.in", "director", "en"),
    ("Adv. R. Iyer", "iyer@example.in", "advocate", "en"),
    ("Meera P.", "meera@example.in", "junior", "ml"),
    ("Suresh", "suresh@example.in", "clerk", "ml"),
    ("Anita", "anita@example.in", "accountant", "en"),
    ("Ramesh", "ramesh@example.in", "helper", "ml"),
]
CLIENTS = [
    ("Mr. A. Sharma", "+91 98765 43210", "a.sharma@example.in", "ml"),
    ("Rao Constructions", "+91 98450 11122", "office@raoconstructions.example.in", "en"),
    ("Mr. S. Nair", "+91 94470 55511", None, "ml"),
    ("Iyer family", "+91 99001 22334", None, "en"),
    ("Pillai Estate", "+91 98860 77880", None, "en"),
]
# (title, number, court, client index, lead user index, stage)
CASES = [
    (
        "Sharma v. State of Karnataka",
        "O.S. 1234/2024",
        "City Civil Court, Bengaluru",
        0,
        0,
        "Evidence",
    ),
    ("Rao Constructions v. BBMP", "W.P. 8812/2025", "High Court of Karnataka", 1, 1, "Arguments"),
    ("State v. Nair", "S.C. 410/2025", "Sessions Court", 2, 0, "Trial"),
    ("Iyer v. Iyer", "M.C. 77/2024", "Family Court", 3, 1, "Reply"),
    ("Pillai Estate matter", "O.S. 902/2023", "City Civil Court, Bengaluru", 4, 2, "Filing"),
]


def hearings(today: datetime):
    d = today.replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        (0, d + timedelta(hours=10, minutes=30), "Cross-examination of PW-2", "Hall 4"),
        (1, d + timedelta(hours=12, minutes=15), "Arguments", "Court 7"),
        (2, d + timedelta(days=6, hours=14, minutes=30), "Framing of charges", None),
        (3, d + timedelta(days=21, hours=10, minutes=30), "Reply by respondent", None),
        (4, d + timedelta(days=28, hours=11), "Filing of documents", "Hall 2"),
    ]
