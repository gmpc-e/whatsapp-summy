from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # project root


class Settings(BaseSettings):
    # Logging
    LOG_LEVEL: str = "INFO"  # INFO | DEBUG | WARNING | ERROR
    DEBUG: bool = False  # when True, forces DEBUG level

    # Ingest security
    WA_JWT_SECRET: str = "change-me"
    WA_INGEST_MAX_BATCH: int = 500
    WA_ALLOWLIST_BRIDGES: str = ""  # comma-separated bridge IDs (optional)

    # Storage
    EVENTS_JSONL: str = "server/storage/wa_events.jsonl"
    LOG_FILE: str = "server/logs/app.log"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / "server" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
