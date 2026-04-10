from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_id: str = Field(alias="AGENT_ID")
    agent_name: str = Field(alias="AGENT_NAME")
    primary_api_base_url: str = Field(alias="PRIMARY_API_BASE_URL")
    agent_shared_token: str = Field(alias="AGENT_SHARED_TOKEN")
    poll_interval_seconds: int = Field(default=5, alias="POLL_INTERVAL_SECONDS")


settings = Settings()
