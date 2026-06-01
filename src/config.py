"""Configuration management using Pydantic settings."""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM - DouBao (ByteDance)
    doubao_api_key: str
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_model: str = "doubao-pro-32k"  # Default model, can use: doubao-pro-4k, doubao-pro-32k, doubao-pro-128k, doubao-lite-4k

    # Vector DB (Optional - not needed for MVP)
    pinecone_api_key: Optional[str] = None
    pinecone_environment: str = "us-east-1"
    pinecone_index_name: str = "api-docs"

    # Database (Optional - will use in-memory if not provided)
    database_url: Optional[str] = None

    # Storage (Optional - will use local files if not provided)
    s3_endpoint: Optional[str] = None
    s3_bucket: str = "workplan-images"
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None

    # Redis (Optional - not needed for MVP)
    redis_url: Optional[str] = None

    # Limits
    max_clarification_rounds: int = 5
    max_review_iterations: int = 3

    # App
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
