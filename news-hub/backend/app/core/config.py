"""
Application Configuration Module

Loads configuration from environment variables with sensible defaults.
Uses Pydantic Settings for type validation and .env file support.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes:
        app_name: Application display name
        debug: Enable debug mode
        api_v1_prefix: API version 1 route prefix

        # Security
        secret_key: JWT signing key (CHANGE IN PRODUCTION!)
        algorithm: JWT algorithm
        access_token_expire_minutes: Token expiration time

        # MongoDB
        mongodb_url: MongoDB connection string
        mongodb_db_name: Database name

        # Elasticsearch
        elasticsearch_url: ES cluster URL
        elasticsearch_index_prefix: Index name prefix

        # CORS
        cors_origins: Allowed origins for CORS
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === Application ===
    app_name: str = "News Hub"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # === Security ===
    secret_key: str = Field(
        default="your-super-secret-key-change-in-production",
        description="JWT signing secret key",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # === MongoDB ===
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "news_hub"

    # === Elasticsearch ===
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_prefix: str = "news_hub"
    elasticsearch_username: Optional[str] = None
    elasticsearch_password: Optional[str] = None

    # === Vector Model ===
    embedding_model_name: str = "shibing624/text2vec-base-chinese"
    embedding_dimension: int = 768

    # === CORS ===
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # === Collector ===
    collector_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    collector_request_timeout: int = 30
    collector_default_interval_minutes: int = 30

    # === Media Proxy ===
    media_cache_dir: str = "./cache/media"
    media_cache_max_age_hours: int = 24

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Returns:
        Settings: Application settings singleton
    """
    return Settings()


# Export settings instance for convenience
settings = get_settings()
