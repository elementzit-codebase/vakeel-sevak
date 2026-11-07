from sqlalchemy import func, select

from app.models import Case, Hearing, User
from app.seed import seed


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_config_reads_product_name(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("PRODUCT_NAME", "RenamedApp")
    get_settings.cache_clear()
    body = client.get("/api/config").json()
    get_settings.cache_clear()
    assert body["product_name"] == "RenamedApp"
    assert body["languages"] == ["en", "ml"]
    assert "accountant" in body["roles"] and "helper" in body["roles"]


def test_seed_is_idempotent(db):
    first = seed(db)
    assert first["cases"] == 5 and first["users"] == 7
    assert seed(db) == {"skipped": 1}
    assert db.scalar(select(func.count()).select_from(User)) == 7
    assert db.scalar(select(func.count()).select_from(Hearing)) == 5
    assert db.scalar(select(func.count()).select_from(Case)) == 5


def test_production_refuses_the_development_secret(monkeypatch):
    import pytest

    from app.config import Settings

    with pytest.raises(RuntimeError):
        Settings(app_env="production").check_production()
    Settings(app_env="production", secret_key="x" * 40).check_production()
