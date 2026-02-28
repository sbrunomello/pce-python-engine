"""PCE runtime configuration definitions."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from env and .env files."""

    app_name: str = "pce-python-core"
    environment: str = Field(default="dev", pattern="^(dev|test|prod)$")
    db_url: str = "sqlite:///./pce_state.db"
    _core_root = Path(__file__).resolve().parents[3]
    event_schema_path: str = str(_core_root / "docs/contracts/events.schema.json")
    action_schema_path: str = str(_core_root / "docs/contracts/action.schema.json")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PCE_")
