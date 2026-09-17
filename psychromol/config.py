from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

def _env(name: str) -> str | None:
    return os.environ.get(f"PSYCHROMOL_{name}") or os.environ.get(name)

def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"PSYCHROMOL_{name} must be a whole number, got {raw!r}") from exc

def _env_list(name: str, default: list[str]) -> list[str]:
    raw = _env(name)
    if raw is None or raw == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]

def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")

def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"PSYCHROMOL_{name} must be a number, got {raw!r}") from exc

@dataclass(frozen=True)
class Settings:
    database_url: str = f"sqlite:///{DATA_DIR / 'psychromol.db'}"
    host: str = "127.0.0.1"
    port: int = 8888
    log_level: str = "INFO"
    log_file: str | None = None
    cors_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:8888",
            "http://127.0.0.1:8888",
        ]
    )
    hardware_enabled: bool = False
    hardware_profile_id: int | None = None
    hardware_poll_seconds: float = 5.0

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "log_level": self.log_level,
            "hardware_enabled": self.hardware_enabled,
        }

def load_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    port = _env_int("PORT", 8888)
    hardware_profile = _env("HARDWARE_PROFILE_ID")
    return Settings(
        database_url=_env("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'psychromol.db'}",
        host=_env("HOST") or "127.0.0.1",
        port=port,
        log_level=(_env("LOG_LEVEL") or "INFO").upper(),
        log_file=_env("LOG_FILE"),
        cors_origins=_env_list(
            "CORS_ORIGINS",
            [f"http://localhost:{port}", f"http://127.0.0.1:{port}"],
        ),
        hardware_enabled=_env_bool("HARDWARE_ENABLED", False),
        hardware_profile_id=int(hardware_profile) if hardware_profile else None,
        hardware_poll_seconds=_env_float("HARDWARE_POLL_SECONDS", 5.0),
    )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()

def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
