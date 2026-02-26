"""SQLAlchemy models for the Wealth Advisor Copilot database."""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Text, DateTime, Integer, Float, Boolean,
    ForeignKey, Index, JSON, ARRAY
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

from app.db.database import Base


class Tenant(Base):
    """Multi-tenant organization."""
    __tablename__ = "tenants"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="tenant")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="tenant")
    conversations: Mapped[List["Conversation"]] = relationship("Conversation", back_populates="tenant")


class User(Base):
    """User accounts."""
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="advisor")  # advisor, admin, compliance
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    conversations: Mapped[List["Conversation"]] = relationship("Conversation", back_populates="user")


class Document(Base):
    """Ingested documents (EDGAR filings, PDFs, etc.)."""
    __tablename__ = "documents"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)  # Mock client grouping
    
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # edgar, pdf, manual, web
    source_url: Mapped[Optional[str]] = mapped_column(String(2000))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # Dedupe
    
    # Metadata
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    cik: Mapped[Optional[str]] = mapped_column(String(20))  # SEC CIK number
    filing_type: Mapped[Optional[str]] = mapped_column(String(20))  # 10-K, 10-Q, 8-K
    filing_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    doc_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="documents")
    chunks: Mapped[List["Chunk"]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_documents_tenant_client", "tenant_id", "client_id"),
        Index("idx_documents_source_type", "source_type"),
    )


class Chunk(Base):
    """Document chunks with embeddings for RAG."""
    __tablename__ = "chunks"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Metadata for citations
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Expected metadata fields:
    # - page: int (for PDFs)
    # - section: str
    # - heading_path: List[str] (e.g., ["Item 1A", "Risk Factors", "Market Risk"])
    # - company: str
    # - filing_date: str
    # - url_fragment: str (for web sources)
    
    # Vector embedding (1536 dimensions for text-embedding-3-small)
    embedding: Mapped[List[float]] = mapped_column(Vector(1536))
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
    
    __table_args__ = (
        Index("idx_chunks_tenant_client", "tenant_id", "client_id"),
        Index("idx_chunks_document", "document_id"),
        # HNSW index for fast vector similarity search
        Index(
            "idx_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"}
        ),
    )


class Conversation(Base):
    """Chat conversations/sessions."""
    __tablename__ = "conversations"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    title: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="conversations")
    user: Mapped["User"] = relationship("User", back_populates="conversations")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="conversation")


class AuditLog(Base):
    """
    Comprehensive audit logging for compliance and debugging.
    This is the "money table" that makes the project enterprise-ready.
    """
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    
    # Query details
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    workflow: Mapped[str] = mapped_column(String(50), nullable=False)  # qa, summary, risk, email
    
    # Retrieval tracking
    retrieved_chunk_ids: Mapped[List[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    retrieval_scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Format: {"chunk_id": {"vector_score": 0.85, "rerank_score": 0.92}}
    
    # Generation details
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Citations for verification
    citations: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Format: [{"chunk_id": "...", "doc_title": "...", "section": "...", "quote": "..."}]
    
    # Performance
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    
    # Compliance flags
    flags: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Possible flags:
    # - low_evidence: bool (fewer than 3 supporting chunks)
    # - possible_hallucination: bool (claims not in sources)
    # - pii_detected: bool (PII found in query or response)
    # - advice_refused: bool (refused to give financial advice)
    # - confidence: str (high/medium/low)
    
    confidence_level: Mapped[str] = mapped_column(String(20), default="medium")  # high, medium, low
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="audit_logs")
    
    __table_args__ = (
        Index("idx_audit_logs_conversation", "conversation_id"),
        Index("idx_audit_logs_workflow", "workflow"),
        Index("idx_audit_logs_created", "created_at"),
        Index("idx_audit_logs_flags", "flags", postgresql_using="gin"),
    )
