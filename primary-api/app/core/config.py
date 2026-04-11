from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="dev", alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL")
    agent_image: str = Field(default="docker-updater-agent:latest", alias="AGENT_IMAGE")
    update_check_ttl_seconds: int = Field(default=900, alias="UPDATE_CHECK_TTL_SECONDS")


settings = Settings()
