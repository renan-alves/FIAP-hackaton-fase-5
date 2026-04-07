"""Application settings loaded from environment variables and .env file."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Provider credentials
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-1.5-pro"

    # LLM configuration
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # File constraints
    MAX_FILE_SIZE_MB: int = 10
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 2

    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "1.0.0"

    @field_validator("LLM_PROVIDER")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        normalized = v.lower()
        allowed = {"gemini", "openai"}
        if normalized not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}, got '{v}'")
        return normalized

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v.upper()


settings = Settings()
