"""PCE runtime configuration definitions."""

from pathlib import Path
from typing import ClassVar

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from env and .env files."""

    app_name: str = "pce-python-core"
    environment: str = Field(default="dev", pattern="^(dev|test|prod)$")
    db_url: str = "sqlite:///./pce_state.db"
    _core_root: ClassVar[Path] = Path(__file__).resolve().parents[3]
    _repo_root: ClassVar[Path] = Path(__file__).resolve().parents[4]
    event_schema_path: str = str(_core_root / "docs/contracts/events.schema.json")
    action_schema_path: str = str(_core_root / "docs/contracts/action.schema.json")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PCE_")

    @classmethod
    def _resolve_contract_path(cls, configured_path: str) -> str:
        """Resolve configurable schema paths using common project roots.

        This keeps backward compatibility with older `.env` values like
        `docs/contracts/events.schema.json` by resolving them to the current
        repository layout.
        """

        path = Path(configured_path)
        if path.is_absolute():
            return str(path)

        candidates = [
            Path.cwd() / path,
            cls._repo_root / path,
            cls._repo_root / "pce-core" / path,
            cls._core_root / path,
        ]

        if list(path.parts[:2]) == ["docs", "contracts"]:
            candidates.append(cls._core_root / path.relative_to("docs/contracts"))

        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve())

        return configured_path

    @model_validator(mode="after")
    def _normalize_paths(self) -> "Settings":
        self.event_schema_path = self._resolve_contract_path(self.event_schema_path)
        self.action_schema_path = self._resolve_contract_path(self.action_schema_path)
        return self
