"""OpenAI / Azure OpenAI embeddings for document chunks."""
import asyncio
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential

from app.ai_client import get_async_client, embedding_model
from app.logging_config import get_logger

logger = get_logger(__name__)


class Embedder:
    """Generate embeddings using OpenAI or Azure OpenAI."""

    def __init__(self):
        self.model = embedding_model()
        self.client = get_async_client()
        self.dimension = 1536

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        if not response.data:
            raise ValueError(f"OpenAI returned empty embedding response for model '{self.model}'")
        return response.data[0].embedding

    async def embed_texts(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call

        Returns:
            List of embedding vectors in the same order as input
        """
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            cleaned_batch = [self._clean_text(t) for t in batch]

            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=cleaned_batch,
                )
            except Exception:
                logger.error(
                    "Embedding API call failed for batch starting at index %d",
                    i,
                    exc_info=True,
                )
                raise

            if not response.data:
                raise ValueError(
                    f"OpenAI returned empty embedding response for batch at index {i}"
                )

            sorted_embeddings = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([e.embedding for e in sorted_embeddings])

            if i + batch_size < len(texts):
                await asyncio.sleep(0.1)

        return all_embeddings

    def _clean_text(self, text: str, max_tokens: int = 8000) -> str:
        """Clean and truncate text to stay within the embedding token limit."""
        import tiktoken
        text = ' '.join(text.split())
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        if len(tokens) > max_tokens:
            text = enc.decode(tokens[:max_tokens])
        return text

    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.

        Note: Some embedding models have different modes for queries vs documents.
        OpenAI's text-embedding-3 doesn't differentiate, but this method
        exists for compatibility with models that do.
        """
        return await self.embed_text(query)
