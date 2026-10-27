"""Settings from the environment (PLAN §19.2). The only module that reads env vars or secrets (§22 rule 8)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Meta Model API
    MODEL_API_KEY: str = Field(default="", repr=False)
    META_BASE_URL: str = "https://api.meta.ai/v1"
    MODEL_ANALYZER: str = "muse-spark-1.3"
    MODEL_INTERVIEWER: str = "muse-spark-1.3"
    MODEL_GRILL: str = "muse-spark-1.3"
    MODEL_AUDIT: str = "muse-wonder-1.0"
    MODEL_REPORT: str = "muse-wonder-1.0"
    MODEL_IMAGE: str = "muse-image-1.0"
    MODEL_SAM: str = "sam-3.1"
    ASR_URL: str = "wss://api.meta.ai/v1/asr/realtime"
    ASR_MODEL: str = "muse-voice-transcribe-1.0"
    USE_CONTRIBUTOR_MODELS: bool = False  # dev only, synthetic data only

    # Partners
    BASETEN_BASE_URL: str = ""
    BASETEN_API_KEY: str = Field(default="", repr=False)
    SPARK_OPEN_MODEL: str = "meta-models/muse-spark-open-1026"
    MODAL_TOKEN_ID: str = Field(default="", repr=False)
    MODAL_TOKEN_SECRET: str = Field(default="", repr=False)
    MODAL_APP_NAME: str = "crucible-runner"

    # App
    RUNNER: Literal["modal", "local"] = "modal"
    ALLOW_LOCAL_RUNNER: bool = False
    DATABASE_URL: str = "sqlite:///./var/crucible.db"
    MOCK: bool = False
    CORS_ORIGINS: str = "http://localhost:3000"
    MAX_SESSIONS_PER_IP_PER_DAY: int = 10

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def database_path(self) -> Path | None:
        """File path from a `sqlite:///path` URL (relative paths resolve against backend/); None = memory."""
        prefix = "sqlite:///"
        if not self.DATABASE_URL.startswith(prefix):
            raise ValueError(f"DATABASE_URL must be sqlite:///<path>, got {self.DATABASE_URL!r}")
        raw = self.DATABASE_URL.removeprefix(prefix)
        if raw in ("", ":memory:"):
            return None
        path = Path(raw)
        return path if path.is_absolute() else (REPO_ROOT / "backend" / path).resolve()

    @property
    def has_meta_key(self) -> bool:
        return bool(self.MODEL_API_KEY)

    @property
    def has_modal(self) -> bool:
        return bool(self.MODAL_TOKEN_ID and self.MODAL_TOKEN_SECRET) or (Path.home() / ".modal.toml").exists()


@lru_cache
def get_settings() -> Settings:
    return Settings()
