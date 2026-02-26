"""LangGraph node implementations for the wealth advisor workflow."""
import re
import time
import uuid
from typing import List, Dict, Any
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.graphs.state import GraphState, Citation
from app.rag.retriever import Retriever
from app.rag.reranker import Reranker
from app.rag.embedder import Embedder
from app.config import get_settings

settings = get_settings()

# Prompts
SYSTEM_PROMPT = """You are a wealth advisor assistant helping financial advisors research regulatory filings and client documents.

RULES:
1. Use ONLY the provided sources. Never make up information.
2. If insufficient evidence, say "I don't have enough information to answer this."
3. Always cite sources using [1], [2], etc.
4. Never provide personalized investment advice.
5. End with confidence level (High/Medium/Low)."""

PROMPTS = {
    "qa": "Answer this question based on the sources:\n\nSOURCES:\n{sources}\n\nQUESTION: {query}",
    "summary": "Summarize based on these sources:\n\nSOURCES:\n{sources}\n\nSUMMARIZE: {query}",
    "risk": "Analyze risks from these sources:\n\nSOURCES:\n{sources}\n\nANALYSIS: {query}",
    "email": "Draft a client email based on:\n\nSOURCES:\n{sources}\n\nREQUEST: {query}\n\nInclude disclaimer about educational purposes.",
}

REFUSAL = """I don't have enough information to answer this question.

Please specify which document or filing to reference, or provide more context about what you're looking for."""


class WorkflowNodes:
    """Node implementations for the LangGraph workflow."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.embedder = Embedder()
        self.retriever = Retriever(embedder=self.embedder)
        self.reranker = Reranker()
    
    async def intent_router(self, state: GraphState) -> GraphState:
        """Classify user intent."""
        prompt = f"Classify intent as qa/summary/risk/email:\n{state.user_query}\nRespond with one word."
        
        try:
            resp = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0,
            )
            intent = resp.choices[0].message.content.strip().lower()
            state.intent = intent if intent in PROMPTS else "qa"
        except Exception:
            state.intent = "qa"
        
        return state
    
    async def retrieve_evidence(self, state: GraphState) -> GraphState:
        """Retrieve and rerank relevant chunks."""
        start = time.time()
        
        try:
            chunks = await self.retriever.retrieve(
                db=self.db,
                query=state.user_query,
                tenant_id=uuid.UUID(state.tenant_id),
                client_id=uuid.UUID(state.client_id) if state.client_id else None,
                doc_types=state.doc_types,
                company=state.company_filter,
                top_k=30,
            )
            
            reranked = await self.reranker.rerank(state.user_query, chunks, top_k=10)
            
            state.retrieved_chunks = [
                {
                    "id": str(r.chunk.id),
                    "document_id": str(r.chunk.document_id),
                    "content": r.chunk.content,
                    "chunk_metadata": r.chunk.metadata,
                    "doc_title": r.chunk.doc_title,
                    "source_url": r.chunk.source_url,
                    "rerank_score": r.rerank_score,
                }
                for r in reranked
            ]
            
            state.retrieval_scores = {
                str(r.chunk.id): {"vector": r.original_score, "rerank": r.rerank_score}
                for r in reranked
            }
            
            state.evidence_quality = self.reranker.compute_evidence_quality(reranked)
            
        except Exception as e:
            state.error = str(e)
            state.retrieved_chunks = []
        
        state.latency_ms = int((time.time() - start) * 1000)
        return state
    
    async def check_evidence(self, state: GraphState) -> GraphState:
        """Check if evidence is sufficient."""
        count = len(state.retrieved_chunks)
        conf = state.evidence_quality.get("confidence", "low")
        
        state.has_sufficient_evidence = (count >= 3 and conf in ["high", "medium"]) or (count >= 1 and conf == "high")
        
        if not state.has_sufficient_evidence:
            state.flags["low_evidence"] = True
        state.flags["confidence"] = conf
        
        return state
    
    async def generate_response(self, state: GraphState) -> GraphState:
        """Generate response using LLM."""
        start = time.time()
        
        if not state.has_sufficient_evidence:
            state.draft_response = REFUSAL
            state.flags["advice_refused"] = True
            return state
        
        try:
            sources = self._format_sources(state.retrieved_chunks)
            user_prompt = PROMPTS.get(state.intent, PROMPTS["qa"]).format(sources=sources, query=state.user_query)
            
            resp = await self.client.chat.completions.create(
                model=settings.OPENAI_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2000,
                temperature=0.3,
            )
            
            state.draft_response = resp.choices[0].message.content
            state.model_name = settings.OPENAI_CHAT_MODEL
            
        except Exception as e:
            state.draft_response = f"Error generating response: {e}"
            state.error = str(e)
        
        state.latency_ms += int((time.time() - start) * 1000)
        return state
    
    async def format_citations(self, state: GraphState) -> GraphState:
        """Extract citations from response."""
        used = set(int(m) for m in re.findall(r'\[(\d+)\]', state.draft_response))
        
        state.citations = [
            Citation(
                chunk_id=chunk["id"],
                doc_title=chunk.get("doc_title", "Unknown"),
                section=chunk.get("metadata", {}).get("section", ""),
                quote=chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"],
                page=chunk.get("metadata", {}).get("page"),
                url=chunk.get("source_url"),
            )
            for i, chunk in enumerate(state.retrieved_chunks, 1) if i in used
        ]
        
        state.final_response = state.draft_response
        
        # Check for uncited claims
        sentences = re.split(r'[.!?]', state.draft_response)
        uncited = sum(1 for s in sentences if len(s) > 50 and not re.search(r'\[\d+\]', s))
        if uncited > 3:
            state.flags["possible_hallucination"] = True
        
        return state
    
    def _format_sources(self, chunks: List[Dict[str, Any]]) -> str:
        """Format chunks as numbered sources."""
        parts = []
        for i, c in enumerate(chunks, 1):
            meta = c.get("metadata", {})
            header = f"[{i}] {c.get('doc_title', 'Document')}"
            if meta.get("section"):
                header += f" - {meta['section']}"
            if meta.get("page"):
                header += f" (p.{meta['page']})"
            parts.append(f"{header}\n{c['content']}")
        return "\n\n---\n\n".join(parts)
