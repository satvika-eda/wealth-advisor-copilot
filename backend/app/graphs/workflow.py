"""LangGraph workflow definition for the wealth advisor assistant."""
import uuid
from datetime import datetime
from typing import Optional
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from app.graphs.state import GraphState
from app.graphs.nodes import WorkflowNodes
from app.db.models import AuditLog
from app.config import get_settings

settings = get_settings()


def create_workflow(db: AsyncSession) -> StateGraph:
    """
    Create the LangGraph workflow for wealth advisor queries.
    
    Flow:
    start → intent_router → retrieve_evidence → check_evidence 
          → generate_response → format_citations → audit_logger → end
    """
    nodes = WorkflowNodes(db)
    
    # Create the graph
    workflow = StateGraph(GraphState)
    
    # Add nodes
    workflow.add_node("intent_router", nodes.intent_router)
    workflow.add_node("retrieve_evidence", nodes.retrieve_evidence)
    workflow.add_node("check_evidence", nodes.check_evidence)
    workflow.add_node("generate_response", nodes.generate_response)
    workflow.add_node("format_citations", nodes.format_citations)
    workflow.add_node("audit_logger", create_audit_logger(db))
    
    # Define edges
    workflow.set_entry_point("intent_router")
    workflow.add_edge("intent_router", "retrieve_evidence")
    workflow.add_edge("retrieve_evidence", "check_evidence")
    workflow.add_edge("check_evidence", "generate_response")
    workflow.add_edge("generate_response", "format_citations")
    workflow.add_edge("format_citations", "audit_logger")
    workflow.add_edge("audit_logger", END)
    
    return workflow.compile()


def create_audit_logger(db: AsyncSession):
    """Create audit logger node that persists to database."""
    
    async def audit_logger(state: GraphState) -> GraphState:
        """Log the complete interaction for compliance and debugging."""
        try:
            audit_log = AuditLog(
                conversation_id=uuid.UUID(state.conversation_id),
                user_query=state.user_query,
                workflow=state.intent,
                retrieved_chunk_ids=[uuid.UUID(c["id"]) for c in state.retrieved_chunks],
                retrieval_scores=state.retrieval_scores,
                model_name=state.model_name or settings.OPENAI_CHAT_MODEL,
                response_text=state.final_response,
                citations=[c.model_dump() for c in state.citations],
                latency_ms=state.latency_ms,
                flags=state.flags,
                confidence_level=state.flags.get("confidence", "medium"),
            )
            
            db.add(audit_log)
            await db.commit()
            
        except Exception as e:
            # Don't fail the workflow on audit errors, just log
            print(f"Audit logging error: {e}")
            await db.rollback()
        
        return state
    
    return audit_logger


async def run_workflow(
    db: AsyncSession,
    tenant_id: str,
    client_id: Optional[str],
    user_id: str,
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
        conversation_id: Conversation UUID string
        user_query: The user's question
        doc_types: Optional filter for document types
        company_filter: Optional company name filter
    
    Returns:
        Final GraphState with response and metadata
    """
    # Initialize state
    initial_state = GraphState(
        tenant_id=tenant_id,
        client_id=client_id,
        user_id=user_id,
        conversation_id=conversation_id,
        user_query=user_query,
        doc_types=doc_types,
        company_filter=company_filter,
    )
    
    # Create and run workflow
    workflow = create_workflow(db)
    result = await workflow.ainvoke(initial_state)
    
    # LangGraph returns a dict-like object, convert to GraphState
    if isinstance(result, dict):
        return GraphState(**result)
    return result
