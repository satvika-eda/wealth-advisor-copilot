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
    
    # Input context (set at start)
    tenant_id: str
    client_id: Optional[str] = None
    user_id: str
    conversation_id: str
    user_query: str
    
    # Workflow routing
    intent: Literal["qa", "summary", "risk", "email", "unknown"] = "unknown"
    
    # Document filters
    doc_types: Optional[List[str]] = None
    company_filter: Optional[str] = None
    
    # Retrieval results
    retrieved_chunks: List[Dict[str, Any]] = []
    retrieval_scores: Dict[str, Dict[str, float]] = {}
    
    # Evidence assessment
    has_sufficient_evidence: bool = False
    evidence_quality: Dict[str, Any] = {}
    
    # Generation
    draft_response: str = ""
    final_response: str = ""
    citations: List[Citation] = []
    
    # Compliance flags
    flags: Dict[str, Any] = {}
    
    # Audit
    model_name: str = ""
    latency_ms: int = 0
    error: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
