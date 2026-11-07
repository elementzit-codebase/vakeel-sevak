from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Office roles. A read-only Client is also a role; see docs/ARCHITECTURE.md.
DEV_SECRET = "dev-secret-change-me-not-for-production-0000"
ROLES = ["director", "advocate", "junior", "clerk", "accountant", "helper", "client"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    product_name: str = "VakeelSevak"
    database_url: str = "postgresql+psycopg://vakeelsevak:vakeelsevak@localhost:5432/vakeelsevak"
    app_env: str = "development"
    secret_key: str = DEV_SECRET
    web_idle_minutes: int = 30  # AUT-05: web sessions expire after 30 minutes of inactivity
    mobile_idle_days: int = 30  # mobile is protected by biometric or PIN unlock on the device
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    reset_link_minutes: int = 30
    languages: str = "en,ml"
    default_language: str = "en"
    # Providers. "fake" is used in development and tests; set to the live name with keys in the environment.
    ai_provider: str = "fake"  # fake | openai
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    speech_provider: str = "fake"  # fake | google
    ocr_provider: str = "fake"  # fake | google
    google_api_key: str = ""
    smtp_host: str = ""  # empty means log only
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@vakeelsevak.example"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 25
    public_web_url: str = "http://localhost:5173"

    def check_production(self) -> None:
        if self.app_env == "production" and (self.secret_key == DEV_SECRET or len(self.secret_key) < 32):
            raise RuntimeError("SECRET_KEY must be a unique value of at least 32 characters when APP_ENV=production")

    @property
    def language_list(self) -> list[str]:
        return [x.strip() for x in self.languages.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
