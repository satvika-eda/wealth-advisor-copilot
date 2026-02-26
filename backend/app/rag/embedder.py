"""OpenAI embeddings for document chunks."""
import asyncio
from typing import List
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

settings = get_settings()


class Embedder:
    """Generate embeddings using OpenAI API."""
    
    def __init__(self, model: str = settings.OPENAI_EMBEDDING_MODEL):
        self.model = model
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.dimension = 1536  # text-embedding-3-small dimension
    
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
        return response.data[0].embedding
    
    async def embed_texts(self, texts: List[str], batch_size: int = 100) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call
        
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # Clean texts (OpenAI has input limits)
            cleaned_batch = [self._clean_text(t) for t in batch]
            
            response = await self.client.embeddings.create(
                model=self.model,
                input=cleaned_batch,
            )
            
            # Sort by index to maintain order
            sorted_embeddings = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([e.embedding for e in sorted_embeddings])
            
            # Small delay between batches to respect rate limits
            if i + batch_size < len(texts):
                await asyncio.sleep(0.1)
        
        return all_embeddings
    
    def _clean_text(self, text: str, max_tokens: int = 8000) -> str:
        """Clean and truncate text for embedding."""
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Rough truncation (1 token ≈ 4 chars for English)
        max_chars = max_tokens * 4
        if len(text) > max_chars:
            text = text[:max_chars]
        
        return text
    
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.
        
        Note: Some embedding models have different modes for queries vs documents.
        OpenAI's text-embedding-3 doesn't differentiate, but this method
        exists for compatibility with models that do.
        """
        return await self.embed_text(query)
