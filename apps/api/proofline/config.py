from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]
    ai_provider: str = "disabled"
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None
    allow_remote_ai: bool = False


def get_settings() -> Settings:
    default_db = Path.cwd() / ".proofline" / "proofline.db"
    database_url = os.getenv("PROOFLINE_DATABASE_URL", f"sqlite:///{default_db}")
    origins = os.getenv("PROOFLINE_CORS_ORIGINS", "http://localhost:5173")
    allow_remote_ai = os.getenv("PROOFLINE_ALLOW_REMOTE_AI", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    return Settings(
        database_url=database_url,
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        ai_provider=os.getenv("PROOFLINE_AI_PROVIDER", "disabled"),
        ai_base_url=os.getenv("PROOFLINE_AI_BASE_URL"),
        ai_model=os.getenv("PROOFLINE_AI_MODEL"),
        ai_api_key=os.getenv("PROOFLINE_AI_API_KEY"),
        allow_remote_ai=allow_remote_ai,
    )
