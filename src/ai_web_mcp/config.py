"""Project-local configuration and first-run token generation."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8765,
    "bridge_token": "",
    "response_timeout": 600,
    "timeout_grace_ms": 5000,
    "max_queue_size": 20,
    "max_active_jobs": 8,
    "rate_limit_per_minute": 0,
    "rate_limit_window_sec": 60,
    "max_text_chars": 200000,
    "log_retention_days": 14,
    "database_path": "data/ai_web_mcp.sqlite3",
    "debug": False,
}


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def load_config() -> dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        config = {}
    merged = {**DEFAULT_CONFIG, **config}
    if not str(merged.get("bridge_token", "")).strip() or merged["bridge_token"] == "CHANGE_ME":
        merged["bridge_token"] = _new_token()
        CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return merged


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path
