from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="dev", alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL")
    admin_api_token: str = Field(default="dev-admin-token", alias="ADMIN_API_TOKEN")
    agent_image: str = Field(default="docker-updater-agent:latest", alias="AGENT_IMAGE")


settings = Settings()
