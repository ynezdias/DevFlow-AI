from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://devflow:devflow@postgres:5432/devflow"
    )

    redis_url: str = "redis://redis:6379/0"
    max_files: int = Field(default=20, ge=1)
    max_patch_chars_per_file: int = Field(default=20_000, ge=1)
    max_total_patch_chars: int = Field(default=100_000, ge=1)
    environment: str = "development"
    github_app_id: str = ""
    github_private_key_path: str = ""
    github_webhook_secret: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
