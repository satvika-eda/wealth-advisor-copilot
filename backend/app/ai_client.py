"""
Shared OpenAI/Azure OpenAI client factory.

If AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are set, all AI calls
go through Azure OpenAI (data stays in your Azure tenant).
Otherwise falls back to direct OpenAI.
"""
from openai import AsyncOpenAI, AsyncAzureOpenAI
from app.config import get_settings

settings = get_settings()


def get_async_client() -> AsyncOpenAI:
    """Return an async OpenAI-compatible client (Azure or direct)."""
    if settings.use_azure_openai:
        return AsyncAzureOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def chat_model() -> str:
    """Return the model/deployment name for chat completions."""
    return (
        settings.AZURE_OPENAI_CHAT_DEPLOYMENT
        if settings.use_azure_openai
        else settings.OPENAI_CHAT_MODEL
    )


def embedding_model() -> str:
    """Return the model/deployment name for embeddings."""
    return (
        settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT
        if settings.use_azure_openai
        else settings.OPENAI_EMBEDDING_MODEL
    )
