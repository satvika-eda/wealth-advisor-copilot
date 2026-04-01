"""Application configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List, Optional


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    APP_NAME: str = "Wealth Advisor Copilot"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/wealth_advisor"

    # OpenAI (direct)
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o"

    # Azure OpenAI — set these to use Azure instead of OpenAI directly.
    # AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must both be set.
    # Deployment names must match what you created in Azure AI Foundry.
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-08-01-preview"
    AZURE_OPENAI_CHAT_DEPLOYMENT: str = "gpt-4o"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-3-small"

    COHERE_API_KEY: Optional[str] = None

    @property
    def use_azure_openai(self) -> bool:
        return bool(self.AZURE_OPENAI_ENDPOINT and self.AZURE_OPENAI_API_KEY)

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    RATE_LIMIT_CHAT: str = "30/minute"
    RATE_LIMIT_INGEST: str = "10/minute"
    RATE_LIMIT_DEFAULT: str = "200/hour"

    ADMIN_SEED_PASSWORD: str = ""

    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Leave empty in development to disable encryption
    FIELD_ENCRYPTION_KEY: str = ""

    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    RETRIEVAL_TOP_K: int = 30
    RERANK_TOP_K: int = 10

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
