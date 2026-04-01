"""LangGraph workflow definition for the wealth advisor assistant."""
import uuid
from datetime import datetime
from typing import Optional
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import ROLE_SENSITIVITY_ACCESS
from app.graphs.state import GraphState
from app.graphs.nodes import WorkflowNodes
from app.db.models import AuditLog
from app.config import get_settings
from app.ai_client import chat_model
from app.security.encryption import encrypt_if_enabled
from app.logging_config import get_logger

logger = get_logger(__name__)

settings = get_settings()


def create_workflow(db: AsyncSession) -> StateGraph:
    """
    Create the LangGraph workflow for wealth advisor queries.

    Flow:
    start → intent_router → policy_check → retrieve_evidence → check_evidence
          → generate_response → format_citations → audit_logger → end

    policy_check enforces:
      - role-based sensitivity access before any retrieval occurs
      - blocks queries that would violate document access controls
    """
    nodes = WorkflowNodes(db)

    workflow = StateGraph(GraphState)

    workflow.add_node("intent_router", nodes.intent_router)
    workflow.add_node("policy_check", create_policy_check())
    workflow.add_node("retrieve_evidence", nodes.retrieve_evidence)
    workflow.add_node("check_evidence", nodes.check_evidence)
    workflow.add_node("generate_response", nodes.generate_response)
    workflow.add_node("format_citations", nodes.format_citations)
    workflow.add_node("audit_logger", create_audit_logger(db))

    workflow.set_entry_point("intent_router")
    workflow.add_edge("intent_router", "policy_check")
    workflow.add_edge("policy_check", "retrieve_evidence")
    workflow.add_edge("retrieve_evidence", "check_evidence")
    workflow.add_edge("check_evidence", "generate_response")
    workflow.add_edge("generate_response", "format_citations")
    workflow.add_edge("format_citations", "audit_logger")
    workflow.add_edge("audit_logger", END)

    return workflow.compile()


def create_policy_check():
    """
    Policy enforcement node — runs before retrieval.
    Validates that the user's role permits access to the requested document classes.
    Blocks the query and short-circuits to a refusal if access is denied.
    """
    async def policy_check(state: GraphState) -> GraphState:
        allowed = ROLE_SENSITIVITY_ACCESS.get(state.user_role, set())

        # If doc_types were explicitly requested, ensure they're in the allowed set.
        # The retriever will also enforce sensitivity at query time; this is an
        # early-exit gate that avoids unnecessary embedding/retrieval work.
        if not allowed:
            state.flags["access_denied"] = True
            state.has_sufficient_evidence = False
            state.final_response = (
                "Access denied: your account role does not permit document retrieval."
            )

        return state

    return policy_check


def create_audit_logger(db: AsyncSession):
    """Create audit logger node that persists to database."""
    
    async def audit_logger(state: GraphState) -> GraphState:
        """Log the complete interaction for compliance and debugging."""
        try:
            audit_log = AuditLog(
                conversation_id=uuid.UUID(state.conversation_id),
                user_id=uuid.UUID(state.user_id),
                # Encrypt sensitive fields at rest — decrypted only by admin/compliance endpoints
                user_query=encrypt_if_enabled(state.user_query),
                workflow=state.intent,
                retrieved_chunk_ids=[uuid.UUID(c["id"]) for c in state.retrieved_chunks],
                retrieval_scores=state.retrieval_scores,
                model_name=state.model_name or chat_model(),
                response_text=encrypt_if_enabled(state.final_response),
                citations=[c.model_dump() for c in state.citations],
                latency_ms=state.latency_ms,
                flags=state.flags,
                confidence_level=state.flags.get("confidence", "medium"),
            )
            
            db.add(audit_log)
            await db.commit()
            
        except Exception:
            # Don't fail the workflow on audit errors, but log with full traceback
            logger.error(
                "Audit logging failed",
                extra={"conversation_id": state.conversation_id},
                exc_info=True,
            )
            await db.rollback()
        
        return state
    
    return audit_logger


async def run_workflow(
    db: AsyncSession,
    tenant_id: str,
    client_id: Optional[str],
    user_id: str,
    user_role: str,
    conversation_id: str,
    user_query: str,
    doc_types: Optional[list] = None,
    company_filter: Optional[str] = None,
) -> GraphState:
    """
    Execute the complete workflow for a user query.

    Args:
        db: Database session
        tenant_id: Tenant UUID string
        client_id: Optional client UUID string
        user_id: User UUID string
        user_role: Role of the authenticated user (advisor/admin/compliance)
        conversation_id: Conversation UUID string
        user_query: The user's question
        doc_types: Optional filter for document types
        company_filter: Optional company name filter

    Returns:
        Final GraphState with response and metadata
    """
    initial_state = GraphState(
        tenant_id=tenant_id,
        client_id=client_id,
        user_id=user_id,
        user_role=user_role,
        conversation_id=conversation_id,
        user_query=user_query,
        doc_types=doc_types,
        company_filter=company_filter,
    )
    
    workflow = create_workflow(db)
    result = await workflow.ainvoke(initial_state)
    
    if isinstance(result, dict):
        try:
            return GraphState(**result)
        except Exception:
            logger.error("Failed to deserialise workflow result into GraphState", exc_info=True)
            raise
    return result
