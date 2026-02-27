from __future__ import annotations

import json

import pytest

from pce.plugins.llm_assistant.config import load_openrouter_credentials


def test_load_openrouter_credentials_from_file(tmp_path) -> None:
    credentials_file = tmp_path / "openrouter_credentials.json"
    credentials_file.write_text(
        json.dumps(
            {
                "api_key": "key-123",
                "model": "provider/model",
                "base_url": "https://example.com/chat/completions",
                "timeout_s": 12.5,
                "http_referer": "https://app.example",
                "x_title": "example-title",
            }
        )
    )

    loaded = load_openrouter_credentials(credentials_file)

    assert loaded["api_key"] == "key-123"
    assert loaded["model"] == "provider/model"
    assert loaded["base_url"] == "https://example.com/chat/completions"
    assert loaded["timeout_s"] == 12.5
    assert loaded["referer"] == "https://app.example"
    assert loaded["title"] == "example-title"


def test_load_openrouter_credentials_env_overrides_file(tmp_path, monkeypatch) -> None:
    credentials_file = tmp_path / "openrouter_credentials.json"
    credentials_file.write_text(
        json.dumps(
            {
                "api_key": "file-key",
                "model": "file/model",
                "base_url": "https://file.example/chat/completions",
                "timeout_s": 5,
                "http_referer": "https://file.example",
                "x_title": "file-title",
            }
        )
    )

    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "env/model")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://env.example/chat/completions")
    monkeypatch.setenv("OPENROUTER_TIMEOUT_S", "11")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://env.example")
    monkeypatch.setenv("OPENROUTER_X_TITLE", "env-title")

    loaded = load_openrouter_credentials(credentials_file)

    assert loaded["api_key"] == "env-key"
    assert loaded["model"] == "env/model"
    assert loaded["base_url"] == "https://env.example/chat/completions"
    assert loaded["timeout_s"] == 11.0
    assert loaded["referer"] == "https://env.example"
    assert loaded["title"] == "env-title"


def test_load_openrouter_credentials_invalid_json_shape(tmp_path) -> None:
    credentials_file = tmp_path / "openrouter_credentials.json"
    credentials_file.write_text(json.dumps(["invalid"]))

    with pytest.raises(ValueError, match="must contain a JSON object"):
        load_openrouter_credentials(credentials_file)
