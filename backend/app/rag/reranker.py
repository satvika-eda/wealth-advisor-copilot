"""Reranking with Cohere or local model."""
import os
from typing import List, Optional
from dataclasses import dataclass

from app.rag.retriever import RetrievedChunk
from app.config import get_settings

settings = get_settings()


@dataclass
class RerankResult:
    """Reranked chunk with updated score."""
    chunk: RetrievedChunk
    rerank_score: float
    original_score: float


class Reranker:
    """
    Rerank retrieved chunks for better relevance.
    
    Supports:
    - Cohere Rerank API (recommended)
    - Fallback to original scores if no reranker available
    """
    
    def __init__(self, top_k: int = settings.RERANK_TOP_K):
        self.top_k = top_k
        self.cohere_client = None
        
        # Initialize Cohere if API key available
        if settings.COHERE_API_KEY:
            try:
                import cohere
                self.cohere_client = cohere.Client(settings.COHERE_API_KEY)
            except ImportError:
                pass
    
    async def rerank(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_k: Optional[int] = None,
    ) -> List[RerankResult]:
        """
        Rerank chunks based on relevance to query.
        
        Args:
            query: User query
            chunks: Retrieved chunks to rerank
            top_k: Number of top results to return
        
        Returns:
            List of RerankResult sorted by rerank score
        """
        k = top_k or self.top_k
        
        if not chunks:
            return []
        
        if self.cohere_client:
            return await self._cohere_rerank(query, chunks, k)
        else:
            # Fallback: return top chunks by original score
            return self._fallback_rerank(chunks, k)
    
    async def _cohere_rerank(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        top_k: int,
    ) -> List[RerankResult]:
        """Rerank using Cohere API."""
        documents = [chunk.content for chunk in chunks]
        
        try:
            response = self.cohere_client.rerank(
                model="rerank-english-v3.0",
                query=query,
                documents=documents,
                top_n=top_k,
            )
            
            results = []
            for r in response.results:
                chunk = chunks[r.index]
                results.append(RerankResult(
                    chunk=chunk,
                    rerank_score=r.relevance_score,
                    original_score=chunk.score,
                ))
            
            return results
        
        except Exception as e:
            # Fallback on error
            print(f"Cohere rerank error: {e}")
            return self._fallback_rerank(chunks, top_k)
    
    def _fallback_rerank(
        self,
        chunks: List[RetrievedChunk],
        top_k: int,
    ) -> List[RerankResult]:
        """Fallback reranking using original scores."""
        sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)[:top_k]
        
        return [
            RerankResult(
                chunk=chunk,
                rerank_score=chunk.score,
                original_score=chunk.score,
            )
            for chunk in sorted_chunks
        ]
    
    def compute_evidence_quality(self, results: List[RerankResult]) -> dict:
        """
        Compute evidence quality metrics for audit logging.
        
        Returns:
            Dict with quality metrics
        """
        if not results:
            return {
                "evidence_count": 0,
                "avg_score": 0.0,
                "confidence": "low",
                "low_evidence": True,
            }
        
        avg_score = sum(r.rerank_score for r in results) / len(results)
        top_score = results[0].rerank_score if results else 0
        
        # Determine confidence based on evidence
        if len(results) >= 5 and avg_score >= 0.7:
            confidence = "high"
        elif len(results) >= 3 and avg_score >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"
        
        return {
            "evidence_count": len(results),
            "avg_score": avg_score,
            "top_score": top_score,
            "confidence": confidence,
            "low_evidence": len(results) < 3,
        }
