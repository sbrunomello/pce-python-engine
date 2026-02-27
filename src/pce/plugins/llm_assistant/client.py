"""OpenRouter async HTTP client wrapper used by assistant decision plugin."""

from __future__ import annotations

import asyncio
import concurrent.futures
import re
from collections.abc import Coroutine
from typing import Any

import httpx


class OpenRouterError(Exception):
    """Base OpenRouter client error."""


class OpenRouterMissingAPIKeyError(OpenRouterError):
    """Raised when API key is not configured."""


class OpenRouterClient:
    """Async OpenRouter chat completion client with short timeout and single retry."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1/chat/completions",
        timeout_s: float = 5.0,
        referer: str = "",
        title: str = "",
    ) -> None:
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._base_url = base_url
        self._timeout_s = timeout_s
        self._referer = referer.strip()
        self._title = title.strip()

    @property
    def model(self) -> str:
        """Model configured for requests."""
        return self._model

    async def generate_reply(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        top_p: float,
        presence_penalty: float,
    ) -> str:
        """Generate assistant text from chat-completions endpoint."""
        if not self._api_key:
            raise OpenRouterMissingAPIKeyError("OPENROUTER_API_KEY is not configured")
        if not self._model:
            raise OpenRouterError("OPENROUTER_MODEL is not configured")

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
        }

        headers = {"Authorization": f"Bearer {self._api_key}"}
        if self._referer:
            headers["HTTP-Referer"] = self._referer
        if self._title:
            headers["X-Title"] = self._title

        for attempt in range(2):
            try:
                timeout = httpx.Timeout(self._timeout_s)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(self._base_url, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
                choices = body.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise OpenRouterError("OpenRouter response without choices")
                message = choices[0].get("message")
                if not isinstance(message, dict):
                    raise OpenRouterError("OpenRouter response without message payload")
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise OpenRouterError("OpenRouter returned empty content")
                return content.strip()
            except httpx.TimeoutException as exc:
                if attempt == 0:
                    await asyncio.sleep(0.1)
                    continue
                raise OpenRouterError("OpenRouter timeout after retry") from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                body_excerpt = _extract_response_excerpt(exc.response.text, limit=500)
                raise OpenRouterError(
                    "OpenRouter request failed "
                    f"(status={status_code}, body={body_excerpt!r})"
                ) from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc

        raise OpenRouterError("OpenRouter request failed unexpectedly")

    def generate_reply_sync(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        top_p: float,
        presence_penalty: float,
    ) -> str:
        """Sync bridge for environments where plugin interfaces are synchronous."""
        coro = self.generate_reply(
            messages,
            temperature=temperature,
            top_p=top_p,
            presence_penalty=presence_penalty,
        )
        return _run_coro_sync(coro)


def _run_coro_sync(coro: Coroutine[Any, Any, str]) -> str:
    """Execute coroutine safely from synchronous plugin code."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def _extract_response_excerpt(raw_text: str, *, limit: int) -> str:
    """Normalize body text and keep only a short excerpt for safe diagnostics."""
    compact = re.sub(r"\s+", " ", raw_text).strip()
    if not compact:
        return "<empty>"
    return compact[:limit]
