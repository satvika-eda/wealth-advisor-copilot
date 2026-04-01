"""LangGraph state definition for the wealth advisor workflow."""
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel


class Citation(BaseModel):
    """A citation reference to a source chunk."""
    chunk_id: str
    doc_title: str
    section: str
    quote: str
    page: Optional[int] = None
    url: Optional[str] = None


class GraphState(BaseModel):
    """
    State object passed through the LangGraph workflow.
    
    This state accumulates data as it flows through nodes:
    IntentRouter → RetrieveEvidence → CheckEvidence → GenerateResponse → CitationFormatter → AuditLogger
    """
    
    tenant_id: str
    client_id: Optional[str] = None
    user_id: str
    user_role: str = "advisor"
    conversation_id: str
    user_query: str
    
    intent: Literal["qa", "summary", "risk", "email", "unknown"] = "unknown"
    
    doc_types: Optional[List[str]] = None
    company_filter: Optional[str] = None
    
    retrieved_chunks: List[Dict[str, Any]] = []
    retrieval_scores: Dict[str, Dict[str, float]] = {}
    
    has_sufficient_evidence: bool = False
    evidence_quality: Dict[str, Any] = {}
    
    draft_response: str = ""
    final_response: str = ""
    citations: List[Citation] = []
    
    flags: Dict[str, Any] = {}

    # Human-readable explanation of why the system refused to answer (if applicable).
    # Populated by build_refusal(); surfaced in the API response so UIs can display
    # a plain-language explanation rather than a raw flag dict.
    refusal_reason: Optional[str] = None
    
    model_name: str = ""
    latency_ms: int = 0
    error: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
