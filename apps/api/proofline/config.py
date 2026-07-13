from __future__ import annotations

import json
import os
import tempfile
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
    provider_config_path: Path | None = None


PROVIDER_CONFIG_KEYS = {
    "ai_provider",
    "ai_base_url",
    "ai_model",
    "ai_api_key",
    "embedding_provider",
    "embedding_base_url",
    "embedding_model",
    "embedding_api_key",
    "allow_remote_ai",
}


def provider_config_path() -> Path:
    configured = os.getenv("PROOFLINE_PROVIDER_CONFIG_PATH")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (Path.cwd() / ".proofline" / "providers.json")
    )


def load_provider_config(path: Path | None = None) -> dict:
    target = path or provider_config_path()
    if not target.exists():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("provider configuration file is invalid") from exc
    if not isinstance(value, dict) or not set(value).issubset(PROVIDER_CONFIG_KEYS):
        raise ValueError("provider configuration file has unsupported fields")
    return value


def save_provider_config(values: dict, path: Path | None = None) -> None:
    target = path or provider_config_path()
    if not set(values).issubset(PROVIDER_CONFIG_KEYS):
        raise ValueError("provider configuration has unsupported fields")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="providers-", suffix=".json", dir=target.parent)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(values, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


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
    stored = load_provider_config()
    allow_remote_raw = os.getenv("PROOFLINE_ALLOW_REMOTE_AI")
    allow_remote_ai = (
        allow_remote_raw
        if allow_remote_raw is not None
        else str(stored.get("allow_remote_ai", False))
    ).lower() in {
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
        ai_provider=os.getenv("PROOFLINE_AI_PROVIDER", stored.get("ai_provider", "disabled")),
        ai_base_url=os.getenv("PROOFLINE_AI_BASE_URL", stored.get("ai_base_url")),
        ai_model=os.getenv("PROOFLINE_AI_MODEL", stored.get("ai_model")),
        ai_api_key=os.getenv("PROOFLINE_AI_API_KEY", stored.get("ai_api_key")),
        embedding_provider=os.getenv(
            "PROOFLINE_EMBEDDING_PROVIDER", stored.get("embedding_provider", "disabled")
        ),
        embedding_base_url=os.getenv(
            "PROOFLINE_EMBEDDING_BASE_URL", stored.get("embedding_base_url")
        ),
        embedding_model=os.getenv("PROOFLINE_EMBEDDING_MODEL", stored.get("embedding_model")),
        embedding_api_key=os.getenv("PROOFLINE_EMBEDDING_API_KEY", stored.get("embedding_api_key")),
        allow_remote_ai=allow_remote_ai,
        folder_watch_interval_seconds=_folder_watch_interval(),
        provider_config_path=provider_config_path(),
    )
