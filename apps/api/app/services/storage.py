"""File storage on local disk (development) behind a small interface; swap for object storage later."""

import uuid
from pathlib import Path

from ..config import get_settings


def _root() -> Path:
    p = Path(get_settings().upload_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(data: bytes) -> str:
    key = uuid.uuid4().hex
    (_root() / key).write_bytes(data)
    return key


def load(key: str) -> bytes:
    if "/" in key or ".." in key:
        raise ValueError("bad key")
    return (_root() / key).read_bytes()


def remove(key: str) -> None:
    if "/" in key or ".." in key:
        return
    (_root() / key).unlink(missing_ok=True)
