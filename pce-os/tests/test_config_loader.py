from pathlib import Path

import pytest

from pce_os.config import load_os_config


def test_load_os_config_reads_unified_file() -> None:
    config = load_os_config()

    assert config.openrouter.api_key == ""
    assert config.openrouter.model == "openai/gpt-4o-mini"
    assert config.openrouter.base_url == "https://openrouter.ai/api/v1/chat/completions"


def test_load_os_config_rejects_invalid_types(tmp_path: Path) -> None:
    config_path = tmp_path / "os_config.json"
    config_path.write_text(
        '{"openrouter": {"api_key": "", "model": 123, "base_url": "https://example.test"}}',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Invalid OpenRouter config values"):
        load_os_config(config_path)
