"""Initial schema — all tables with governance, security, and audit fields.

Revision ID: 001
Revises:
Create Date: 2026-03-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── tenants ──────────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="advisor"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("cik", sa.String(20), nullable=True),
        sa.Column("filing_type", sa.String(20), nullable=True),
        sa.Column("filing_date", sa.DateTime(), nullable=True),
        sa.Column("doc_metadata", postgresql.JSONB(), nullable=True, server_default="{}"),
        # Ingestion status tracking
        sa.Column("ingestion_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("ingestion_error", sa.Text(), nullable=True),
        # Governance
        sa.Column("sensitivity_level", sa.String(20), nullable=False, server_default="internal"),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_client_id", "documents", ["client_id"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.create_index("idx_documents_tenant_client", "documents", ["tenant_id", "client_id"])
    op.create_index("idx_documents_source_type", "documents", ["source_type"])

    # ── chunks ────────────────────────────────────────────────────────────────
    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        # 1536-dim vector (text-embedding-3-small)
        sa.Column("embedding", sa.Text(), nullable=True),   # placeholder; vector type below
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # Drop placeholder and recreate as proper vector column
    op.execute("ALTER TABLE chunks DROP COLUMN embedding")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding vector(1536)")

    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])
    op.create_index("ix_chunks_client_id", "chunks", ["client_id"])
    op.create_index("idx_chunks_tenant_client", "chunks", ["tenant_id", "client_id"])
    op.create_index("idx_chunks_document", "chunks", ["document_id"])
    # HNSW index for cosine similarity
    op.execute(
        "CREATE INDEX idx_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # ── conversations ─────────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_client_id", "conversations", ["client_id"])

    # ── audit_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("workflow", sa.String(50), nullable=False),
        sa.Column("retrieved_chunk_ids",
                  postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("retrieval_scores", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flags", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("confidence_level", sa.String(20), nullable=False, server_default="medium"),
        # Human review path
        sa.Column("flagged_for_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_logs_conversation", "audit_logs", ["conversation_id"])
    op.create_index("idx_audit_logs_user", "audit_logs", ["user_id"])
    op.create_index("idx_audit_logs_workflow", "audit_logs", ["workflow"])
    op.create_index("idx_audit_logs_created", "audit_logs", ["created_at"])
    op.execute(
        "CREATE INDEX idx_audit_logs_flags ON audit_logs USING gin (flags)"
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("conversations")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("users")
    op.drop_table("tenants")
    op.execute("DROP EXTENSION IF EXISTS vector")
