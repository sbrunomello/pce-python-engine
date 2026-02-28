"""LLM adapter interfaces used for optional rationale enrichment."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from pce_os.config import load_os_config


class LLMClient(ABC):
    """Simple completion interface for pluggable LLM providers."""

    @abstractmethod
    def complete(self, prompt: str, *, timeout_s: float = 3.0) -> str:
        """Return a completion string for the provided prompt."""


class NullLLMClient(LLMClient):
    """Default no-op adapter to keep behavior deterministic by default."""

    def complete(self, prompt: str, *, timeout_s: float = 3.0) -> str:
        _ = (prompt, timeout_s)
        return ""


class OpenRouterLLMClient(LLMClient):
    """Best-effort OpenRouter adapter stub (optional, retries=0)."""

    def __init__(self) -> None:
        # Centralized OS config keeps runtime deterministic across environments.
        openrouter = load_os_config().openrouter
        self.api_key = openrouter.api_key
        self.model = openrouter.model
        self.base_url = openrouter.base_url

    def complete(self, prompt: str, *, timeout_s: float = 3.0) -> str:
        if not self.api_key:
            return ""

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError, KeyError):
            return ""

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            return ""
        content = message.get("content", "")
        return content if isinstance(content, str) else ""
