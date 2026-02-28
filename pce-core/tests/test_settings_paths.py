from pathlib import Path

from pce.core.config import Settings


def test_settings_resolve_legacy_contract_paths() -> None:
    settings = Settings(
        event_schema_path="docs/contracts/events.schema.json",
        action_schema_path="docs/contracts/action.schema.json",
    )

    assert Path(settings.event_schema_path).exists()
    assert Path(settings.action_schema_path).exists()
    assert settings.event_schema_path.endswith("pce-core/docs/contracts/events.schema.json")
    assert settings.action_schema_path.endswith("pce-core/docs/contracts/action.schema.json")


def test_settings_keep_absolute_paths(tmp_path: Path) -> None:
    event_schema = tmp_path / "events.schema.json"
    action_schema = tmp_path / "action.schema.json"
    event_schema.write_text("{}", encoding="utf-8")
    action_schema.write_text("{}", encoding="utf-8")

    settings = Settings(
        event_schema_path=str(event_schema),
        action_schema_path=str(action_schema),
    )

    assert settings.event_schema_path == str(event_schema)
    assert settings.action_schema_path == str(action_schema)
