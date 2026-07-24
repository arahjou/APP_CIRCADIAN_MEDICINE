from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Settings:
    app_env: str
    db_path: str
    ncbi_api_key: str | None
    allowed_models: List[str]
    session_timeout_minutes: int
    max_login_attempts: int
    login_window_minutes: int
    lockout_minutes: int
    show_raw_pipeline_traces: bool


def _parse_csv(value: str, default: List[str]) -> List[str]:
    items = [x.strip() for x in value.split(",") if x.strip()]
    return items or default


def _parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv_if_present() -> None:
    """Load .env once, without overriding already-exported environment variables."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def get_settings() -> Settings:
    _load_dotenv_if_present()

    app_env = os.getenv("APP_ENV", "dev").strip().lower()
    if app_env not in {"dev", "staging", "prod"}:
        raise ValueError("APP_ENV must be one of: dev, staging, prod")

    db_path = os.getenv("DB_PATH", "Actigraph_record.db").strip()
    if not db_path:
        raise ValueError("DB_PATH must not be empty")

    allowed_models = _parse_csv(
        os.getenv("ALLOWED_MODELS", "phi4:14b,llama3.2,gemma3:12b,qwen3:8b,qwen3.5:9b,qwen3.5:4b"),
        default=["phi4:14b"],
    )

    session_timeout_minutes = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
    max_login_attempts = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
    login_window_minutes = int(os.getenv("LOGIN_WINDOW_MINUTES", "15"))
    lockout_minutes = int(os.getenv("LOCKOUT_MINUTES", "15"))

    if session_timeout_minutes < 5:
        raise ValueError("SESSION_TIMEOUT_MINUTES must be >= 5")
    if max_login_attempts < 3:
        raise ValueError("MAX_LOGIN_ATTEMPTS must be >= 3")

    return Settings(
        app_env=app_env,
        db_path=db_path,
        ncbi_api_key=os.getenv("NCBI_API_KEY") or None,
        allowed_models=allowed_models,
        session_timeout_minutes=session_timeout_minutes,
        max_login_attempts=max_login_attempts,
        login_window_minutes=login_window_minutes,
        lockout_minutes=lockout_minutes,
        show_raw_pipeline_traces=_parse_bool(os.getenv("SHOW_RAW_PIPELINE_TRACES", "0")),
    )
