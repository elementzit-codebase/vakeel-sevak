"""Speech to text (English and Malayalam). Live adapter uses Google Cloud Speech-to-Text REST with an API key.
Not exercised against the real service here. For production use a service account and an Indian region."""

import base64
from typing import Protocol

import httpx

from ..config import get_settings

LANG = {"en": "en-IN", "ml": "ml-IN"}


class Speech(Protocol):
    def transcribe(self, audio: bytes, language: str, content_type: str) -> str: ...


class FakeSpeech:
    def transcribe(self, audio: bytes, language: str, content_type: str) -> str:
        return audio.decode("utf-8", "ignore")  # tests send text as the "audio"


class GoogleSpeech:
    def __init__(self, key: str):
        self.key = key

    def transcribe(self, audio: bytes, language: str, content_type: str) -> str:
        cfg = {"languageCode": LANG.get(language, "en-IN"), "enableAutomaticPunctuation": True}
        if "webm" in content_type or "opus" in content_type:
            cfg["encoding"] = "WEBM_OPUS"
        r = httpx.post(
            f"https://speech.googleapis.com/v1/speech:recognize?key={self.key}",
            json={"config": cfg, "audio": {"content": base64.b64encode(audio).decode()}},
            timeout=120,
        )
        r.raise_for_status()
        parts = [x["alternatives"][0]["transcript"] for x in r.json().get("results", []) if x.get("alternatives")]
        return " ".join(parts)


def get_speech() -> Speech:
    s = get_settings()
    if s.speech_provider == "google":
        if not s.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")
        return GoogleSpeech(s.google_api_key)
    return FakeSpeech()
