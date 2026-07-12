from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]


def get_settings() -> Settings:
    default_db = Path.cwd() / ".proofline" / "proofline.db"
    database_url = os.getenv("PROOFLINE_DATABASE_URL", f"sqlite:///{default_db}")
    origins = os.getenv("PROOFLINE_CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        database_url=database_url,
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
    )
