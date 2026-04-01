"""Hybrid retrieval with vector similarity and filtering."""
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import ROLE_SENSITIVITY_ACCESS
from app.db.models import Chunk, Document
from app.rag.embedder import Embedder
from app.config import get_settings

settings = get_settings()


@dataclass
class RetrievedChunk:
    """A retrieved chunk with relevance score."""
    id: uuid.UUID
    document_id: uuid.UUID
    content: str
    metadata: Dict[str, Any]
    score: float
    doc_title: Optional[str] = None
    source_url: Optional[str] = None


class Retriever:
    """
    Hybrid retriever with:
    - Vector similarity search (pgvector)
    - Tenant/client filtering (security)
    - Optional keyword/BM25 search
    """
    
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        top_k: int = settings.RETRIEVAL_TOP_K,
    ):
        self.embedder = embedder or Embedder()
        self.top_k = top_k
    
    async def retrieve(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: uuid.UUID,
        client_id: Optional[uuid.UUID] = None,
        doc_types: Optional[List[str]] = None,
        company: Optional[str] = None,
        top_k: Optional[int] = None,
        user_role: str = "advisor",
    ) -> List[RetrievedChunk]:
        """
        Retrieve relevant chunks for a query.

        Args:
            db: Database session
            query: User query
            tenant_id: Tenant ID (REQUIRED for security)
            client_id: Optional client filter
            doc_types: Optional filter by document types (edgar, pdf, etc.)
            company: Optional filter by company name
            top_k: Override default top_k
            user_role: Role of authenticated user — restricts sensitivity levels

        Returns:
            List of RetrievedChunk objects sorted by relevance.
            Only approved documents within the user's sensitivity access are returned.
        """
        k = top_k or self.top_k
        query_embedding = await self.embedder.embed_query(query)

        return await self._vector_search(
            db=db,
            query_embedding=query_embedding,
            tenant_id=tenant_id,
            client_id=client_id,
            doc_types=doc_types,
            company=company,
            top_k=k,
            user_role=user_role,
        )
    
    async def _vector_search(
        self,
        db: AsyncSession,
        query_embedding: List[float],
        tenant_id: uuid.UUID,
        client_id: Optional[uuid.UUID],
        doc_types: Optional[List[str]],
        company: Optional[str],
        top_k: int,
        user_role: str = "advisor",
    ) -> List[RetrievedChunk]:
        """Perform vector similarity search with pgvector.

        Only returns chunks from documents that are:
          - approved (is_approved = true)
          - within the sensitivity levels permitted for user_role
          - not past their expiry date
        """
        embedding_str = f"[{','.join(map(str, query_embedding))}]"
        allowed_sensitivity = list(ROLE_SENSITIVITY_ACCESS.get(user_role, frozenset({"public", "internal"})))

        query = f"""
            SELECT
                c.id,
                c.document_id,
                c.content,
                c.chunk_metadata,
                1 - (c.embedding <=> '{embedding_str}'::vector) as score,
                d.title as doc_title,
                d.source_url
            FROM chunks c
            JOIN documents d ON c.document_id = d.id
            WHERE c.tenant_id = :tenant_id
              AND d.is_approved = true
              AND d.sensitivity_level = ANY(:allowed_sensitivity)
              AND (d.expires_at IS NULL OR d.expires_at > NOW())
        """

        params: Dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "allowed_sensitivity": allowed_sensitivity,
        }

        if client_id:
            query += " AND c.client_id = :client_id"
            params["client_id"] = str(client_id)

        if doc_types:
            query += " AND d.source_type = ANY(:doc_types)"
            params["doc_types"] = doc_types

        if company:
            query += " AND d.company_name ILIKE :company"
            params["company"] = f"%{company}%"

        query += f"""
            ORDER BY c.embedding <=> '{embedding_str}'::vector
            LIMIT :top_k
        """
        params["top_k"] = top_k
        
        result = await db.execute(text(query), params)
        rows = result.fetchall()
        
        return [
            RetrievedChunk(
                id=uuid.UUID(str(row.id)),
                document_id=uuid.UUID(str(row.document_id)),
                content=row.content,
                metadata=row.chunk_metadata or {},
                score=float(row.score),
                doc_title=row.doc_title,
                source_url=row.source_url,
            )
            for row in rows
        ]
    
    async def retrieve_by_ids(
        self,
        db: AsyncSession,
        chunk_ids: List[uuid.UUID],
        tenant_id: uuid.UUID,
    ) -> List[RetrievedChunk]:
        """Retrieve specific chunks by ID (for audit/debugging)."""
        
        query = select(
            Chunk.id,
            Chunk.document_id,
            Chunk.content,
            Chunk.chunk_metadata,
            Document.title.label("doc_title"),
            Document.source_url,
        ).join(
            Document, Chunk.document_id == Document.id
        ).where(
            Chunk.id.in_(chunk_ids),
            Chunk.tenant_id == tenant_id,
        )
        
        result = await db.execute(query)
        rows = result.fetchall()
        
        return [
            RetrievedChunk(
                id=row.id,
                document_id=row.document_id,
                content=row.content,
                metadata=row.chunk_metadata or {},
                score=1.0,  # No score for direct retrieval
                doc_title=row.doc_title,
                source_url=row.source_url,
            )
            for row in rows
        ]
    
    def merge_and_dedupe(
        self,
        vector_results: List[RetrievedChunk],
        keyword_results: List[RetrievedChunk],
    ) -> List[RetrievedChunk]:
        """Merge and deduplicate results from vector and keyword search."""
        seen_ids = set()
        merged = []
        
        # Interleave results, prioritizing vector search
        for v_chunk, k_chunk in zip(vector_results, keyword_results):
            if v_chunk.id not in seen_ids:
                merged.append(v_chunk)
                seen_ids.add(v_chunk.id)
            
            if k_chunk.id not in seen_ids:
                merged.append(k_chunk)
                seen_ids.add(k_chunk.id)
        
        remaining_vector = [c for c in vector_results if c.id not in seen_ids]
        remaining_keyword = [c for c in keyword_results if c.id not in seen_ids]
        
        merged.extend(remaining_vector)
        merged.extend(remaining_keyword)
        
        return merged
