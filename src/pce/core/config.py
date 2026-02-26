"""PCE runtime configuration definitions."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from env and .env files."""

    app_name: str = "pce-python-core"
    environment: str = Field(default="dev", pattern="^(dev|test|prod)$")
    db_url: str = "sqlite:///./pce_state.db"
    event_schema_path: str = "docs/contracts/events.schema.json"
    action_schema_path: str = "docs/contracts/action.schema.json"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PCE_")
