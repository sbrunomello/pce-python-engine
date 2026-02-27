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


def test_load_openrouter_credentials_invalid_json_shape(tmp_path) -> None:
    credentials_file = tmp_path / "openrouter_credentials.json"
    credentials_file.write_text(json.dumps(["invalid"]))

    with pytest.raises(ValueError, match="must contain a JSON object"):
        load_openrouter_credentials(credentials_file)
