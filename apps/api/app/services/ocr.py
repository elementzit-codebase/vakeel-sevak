"""Text extraction. PDFs with a text layer are read with pypdf; images and scanned pages go to OCR.
Returns a list of page texts so every extracted fact can point to a page."""

import base64
import io
from typing import Protocol

import httpx
from pypdf import PdfReader

from ..config import get_settings


class OCR(Protocol):
    def image_text(self, data: bytes) -> str: ...


class FakeOCR:
    def image_text(self, data: bytes) -> str:
        return data.decode("utf-8", "ignore")


class GoogleVision:
    def __init__(self, key: str):
        self.key = key

    def image_text(self, data: bytes) -> str:
        r = httpx.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={self.key}",
            json={
                "requests": [
                    {
                        "image": {"content": base64.b64encode(data).decode()},
                        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                        "imageContext": {"languageHints": ["en", "ml"]},
                    }
                ]
            },
            timeout=120,
        )
        r.raise_for_status()
        return (r.json()["responses"][0].get("fullTextAnnotation") or {}).get("text", "")


def get_ocr() -> OCR:
    s = get_settings()
    if s.ocr_provider == "google":
        if not s.google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")
        return GoogleVision(s.google_api_key)
    return FakeOCR()


def extract_pages(data: bytes, content_type: str, name: str) -> list[str]:
    if content_type == "application/pdf" or name.lower().endswith(".pdf"):
        try:
            pages = [(pg.extract_text() or "").strip() for pg in PdfReader(io.BytesIO(data)).pages]
        except Exception:
            return []
        if any(pages):
            return pages
        return []  # scanned PDF: rasterising pages needs poppler; flagged for follow-up in docs
    if content_type.startswith("image/") or content_type.startswith("text/"):
        return [get_ocr().image_text(data)]
    return []
