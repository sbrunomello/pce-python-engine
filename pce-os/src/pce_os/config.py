"""Centralized configuration loader for PCE-OS.

This module is intentionally file-based (JSON) so runtime behavior is deterministic
and independent from shell environment variables.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpenRouterConfig:
    """OpenRouter integration settings used by the optional LLM client."""

    api_key: str
    model: str
    base_url: str


@dataclass(frozen=True)
class OSConfig:
    """Top-level PCE-OS settings grouped by integration area."""

    openrouter: OpenRouterConfig


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "os_config.json"


def _read_json(path: Path) -> dict[str, Any]:
    """Read and validate the JSON object from disk.

    Raises:
        RuntimeError: If the file is missing, malformed, or not a JSON object.
    """

    try:
        raw_content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"PCE-OS config file not found: {path}") from exc

    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in PCE-OS config file: {path}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"PCE-OS config root must be a JSON object: {path}")

    return payload


def load_os_config(config_path: Path | None = None) -> OSConfig:
    """Load PCE-OS settings from the unified JSON file.

    Args:
        config_path: Optional explicit config path for tests or custom runners.

    Returns:
        Parsed :class:`OSConfig` instance.

    Raises:
        RuntimeError: If required keys are missing or have invalid types.
    """

    path = config_path or _DEFAULT_CONFIG_PATH
    data = _read_json(path)

    openrouter = data.get("openrouter", {})
    if not isinstance(openrouter, dict):
        raise RuntimeError("Invalid 'openrouter' section in PCE-OS config; expected JSON object")

    api_key = openrouter.get("api_key", "")
    model = openrouter.get("model", "openai/gpt-4o-mini")
    base_url = openrouter.get("base_url", "https://openrouter.ai/api/v1/chat/completions")

    if not isinstance(api_key, str) or not isinstance(model, str) or not isinstance(base_url, str):
        raise RuntimeError("Invalid OpenRouter config values; expected string fields")

    return OSConfig(openrouter=OpenRouterConfig(api_key=api_key, model=model, base_url=base_url))
