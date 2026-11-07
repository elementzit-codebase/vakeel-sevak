"""Expo push notifications. Development records messages in `sent`; with PUSH_LIVE=1 it calls exp.host."""

import os

import httpx

sent: list[dict] = []


def send(tokens: list[str], title: str, body: str) -> None:
    for t in tokens:
        sent.append({"to": t, "title": title, "body": body})
    if tokens and os.environ.get("PUSH_LIVE") == "1":
        httpx.post(
            "https://exp.host/--/api/v2/push/send",
            json=[{"to": t, "title": title, "body": body} for t in tokens],
            timeout=30,
        )
