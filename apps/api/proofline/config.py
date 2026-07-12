from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]
    import_roots: tuple[Path, ...] = ()
    ai_provider: str = "disabled"
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None
    embedding_provider: str = "disabled"
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_api_key: str | None = None
    allow_remote_ai: bool = False
    folder_watch_interval_seconds: int = 0


def _folder_watch_interval() -> int:
    raw_value = os.getenv("PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS", "0")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(
            "PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS must be 0 or an integer from 1 to 3600"
        ) from exc
    if value < 0 or value > 3600:
        raise ValueError(
            "PROOFLINE_FOLDER_WATCH_INTERVAL_SECONDS must be 0 or an integer from 1 to 3600"
        )
    return value


def get_settings() -> Settings:
    default_db = Path.cwd() / ".proofline" / "proofline.db"
    database_url = os.getenv("PROOFLINE_DATABASE_URL", f"sqlite:///{default_db}")
    origins = os.getenv("PROOFLINE_CORS_ORIGINS", "http://localhost:5173")
    allow_remote_ai = os.getenv("PROOFLINE_ALLOW_REMOTE_AI", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    configured_roots = os.getenv("PROOFLINE_IMPORT_ROOTS", "")
    import_roots = tuple(
        dict.fromkeys(
            Path(value.strip()).expanduser().resolve()
            for value in configured_roots.split(os.pathsep)
            if value.strip()
        )
    )
    return Settings(
        database_url=database_url,
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        import_roots=import_roots,
        ai_provider=os.getenv("PROOFLINE_AI_PROVIDER", "disabled"),
        ai_base_url=os.getenv("PROOFLINE_AI_BASE_URL"),
        ai_model=os.getenv("PROOFLINE_AI_MODEL"),
        ai_api_key=os.getenv("PROOFLINE_AI_API_KEY"),
        embedding_provider=os.getenv("PROOFLINE_EMBEDDING_PROVIDER", "disabled"),
        embedding_base_url=os.getenv("PROOFLINE_EMBEDDING_BASE_URL"),
        embedding_model=os.getenv("PROOFLINE_EMBEDDING_MODEL"),
        embedding_api_key=os.getenv("PROOFLINE_EMBEDDING_API_KEY"),
        allow_remote_ai=allow_remote_ai,
        folder_watch_interval_seconds=_folder_watch_interval(),
    )
