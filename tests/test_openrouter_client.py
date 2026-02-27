from __future__ import annotations

import asyncio

import httpx
import pytest

from pce.plugins.llm_assistant.client import OpenRouterClient, OpenRouterError


def test_generate_reply_includes_status_and_body_excerpt(monkeypatch) -> None:
    async def fake_post(self, url, *, headers, json):  # type: ignore[no-untyped-def]
        del self, url, headers, json
        return httpx.Response(
            status_code=401,
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            text="Unauthorized " + "x" * 700,
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    client = OpenRouterClient(api_key="test-key", model="provider/model")

    with pytest.raises(OpenRouterError, match=r"status=401") as exc_info:
        asyncio.run(
            client.generate_reply(
                [{"role": "user", "content": "oi"}],
                temperature=0.2,
                top_p=0.9,
                presence_penalty=0.0,
            )
        )

    message = str(exc_info.value)
    assert "body='Unauthorized" in message
    assert len(message) < 650


def test_generate_reply_retries_only_timeout(monkeypatch) -> None:
    calls = {"count": 0}

    async def fake_post(self, url, *, headers, json):  # type: ignore[no-untyped-def]
        del self, url, headers, json
        calls["count"] += 1
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    client = OpenRouterClient(api_key="test-key", model="provider/model")

    with pytest.raises(OpenRouterError, match="timeout after retry"):
        asyncio.run(
            client.generate_reply(
                [{"role": "user", "content": "oi"}],
                temperature=0.2,
                top_p=0.9,
                presence_penalty=0.0,
            )
        )

    assert calls["count"] == 2
