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
DEFAULT_CREDENTIALS_PATH = Path("config/openrouter_credentials.json")


def load_openrouter_credentials(path: str | Path | None = None) -> dict[str, Any]:
    """Load OpenRouter credentials from JSON file with safe defaults.

    The file is optional. When the file does not exist, defaults are returned so
    the API can still boot and emit controlled fallback messages.
    """

    raw_path = path or os.getenv("OPENROUTER_CREDENTIALS_FILE", "").strip()
    credentials_path = Path(raw_path).expanduser() if raw_path else DEFAULT_CREDENTIALS_PATH

    credentials_data: dict[str, Any] = {}
    if credentials_path.exists():
        with credentials_path.open("r", encoding="utf-8") as file_handle:
            raw_data = json.load(file_handle)
        if not isinstance(raw_data, dict):
            raise ValueError("OpenRouter credentials file must contain a JSON object")
        credentials_data = raw_data

    timeout_raw = credentials_data.get("timeout_s", DEFAULT_OPENROUTER_TIMEOUT_S)
    timeout_value = float(timeout_raw)
    if timeout_value <= 0:
        raise ValueError("OpenRouter timeout_s must be greater than zero")

    return {
        "api_key": str(credentials_data.get("api_key", "")).strip(),
        "model": str(credentials_data.get("model", DEFAULT_OPENROUTER_MODEL)).strip(),
        "base_url": str(credentials_data.get("base_url", DEFAULT_OPENROUTER_BASE_URL)).strip(),
        "timeout_s": timeout_value,
        "referer": str(credentials_data.get("http_referer", "")).strip(),
        "title": str(credentials_data.get("x_title", DEFAULT_OPENROUTER_TITLE)).strip(),
        "credentials_path": str(credentials_path),
    }

