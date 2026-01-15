"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ecfr_database_url: str

    api_title: str = "eCFR Analyzer API"
    api_description: str = "Read-only REST API for analyzing federal regulations by agency"
    api_version: str = "0.0.1"

    # Server Configuration
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8000
    debug: bool = False

    # CORS
    cors_origins: list[str] = ["*"]


# Create a singleton instance
settings = Settings()
