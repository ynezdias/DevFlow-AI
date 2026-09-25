from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://devflow:devflow@postgres:5432/devflow"
    )

    redis_url: str = "redis://redis:6379/0"
    analyzer_timeout_seconds: int = Field(default=30, ge=1)
    max_source_bytes_per_file: int = Field(default=1_000_000, ge=1)
    max_files: int = Field(default=20, ge=1)
    max_patch_chars_per_file: int = Field(default=20_000, ge=1)
    max_total_patch_chars: int = Field(default=100_000, ge=1)
    ai_enabled: bool = False
    ai_provider: str = Field(default="gemini", pattern="^gemini$")
    ai_model: str = Field(default="gemini-3.8-flash", pattern=r"^[a-zA-Z0-9.-]+$")
    gemini_api_key: SecretStr = SecretStr("")
    ai_max_files: int = Field(default=20, ge=1, le=20)
    ai_max_diff_chars: int = Field(default=20_000, ge=1)
    ai_max_total_input_chars: int = Field(default=100_000, ge=1)
    ai_max_output_tokens: int = Field(default=4096, ge=1, le=8192)
    ai_timeout_seconds: int = Field(default=30, ge=1, le=120)
    ai_max_retries: int = Field(default=1, ge=0, le=2)
    environment: str = "development"
    github_checks_enabled: bool = False
    github_app_id: str = ""
    github_private_key_path: str = ""
    github_webhook_secret: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
