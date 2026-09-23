from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://devflow:devflow@postgres:5432/devflow"
    )

    redis_url: str = "redis://redis:6379/0"
    environment: str = "development"
    github_app_id: str = ""
    github_private_key_path: str = ""
    github_webhook_secret: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
