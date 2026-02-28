"""Configuration helpers for the OpenRouter assistant plugin."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.2-3b-instruct:free"
DEFAULT_OPENROUTER_TIMEOUT_S = 5.0
DEFAULT_OPENROUTER_TITLE = "pce-python-engine"
DEFAULT_CONFIG_PATH = Path("config/openrouter_credentials.json")


def load_openrouter_credentials(path: str | Path | None = None) -> dict[str, Any]:
    """Load OpenRouter credentials from ENV and optional JSON file.

    Resolution order for each setting is: ENV -> JSON config -> defaults.
    The file is optional. When the file does not exist, defaults are returned so
    the API can still boot and emit controlled fallback messages.
    """

    raw_path = (
        str(path).strip()
        if path is not None
        else os.getenv("OPENROUTER_CONFIG_PATH", "").strip()
        or os.getenv("OPENROUTER_CREDENTIALS_FILE", "").strip()
    )
    config_path = Path(raw_path).expanduser() if raw_path else DEFAULT_CONFIG_PATH

    config_data: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as file_handle:
            raw_data = json.load(file_handle)
        if not isinstance(raw_data, dict):
            raise ValueError("OpenRouter credentials file must contain a JSON object")
        config_data = raw_data

    timeout_raw = _coalesce(
        os.getenv("OPENROUTER_TIMEOUT_S"),
        config_data.get("timeout_s"),
        DEFAULT_OPENROUTER_TIMEOUT_S,
    )
    timeout_value = float(timeout_raw)
    if timeout_value <= 0:
        raise ValueError("OpenRouter timeout_s must be greater than zero")

    return {
        "api_key": str(_coalesce(os.getenv("OPENROUTER_API_KEY"), config_data.get("api_key"), "")).strip(),
        "model": str(
            _coalesce(os.getenv("OPENROUTER_MODEL"), config_data.get("model"), DEFAULT_OPENROUTER_MODEL)
        ).strip(),
        "base_url": str(
            _coalesce(
                os.getenv("OPENROUTER_BASE_URL"),
                config_data.get("base_url"),
                DEFAULT_OPENROUTER_BASE_URL,
            )
        ).strip(),
        "timeout_s": timeout_value,
        "referer": str(
            _coalesce(os.getenv("OPENROUTER_HTTP_REFERER"), config_data.get("http_referer"), "")
        ).strip(),
        "title": str(
            _coalesce(os.getenv("OPENROUTER_X_TITLE"), config_data.get("x_title"), DEFAULT_OPENROUTER_TITLE)
        ).strip(),
        "credentials_path": str(config_path),
    }


def _coalesce(*values: Any) -> Any:
    """Return first non-empty value, preserving falsy numerics such as 0."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return ""
