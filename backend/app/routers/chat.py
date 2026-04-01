"""Chat router for RAG-powered conversations."""
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import Conversation, AuditLog, User
from app.graphs.workflow import run_workflow
from app.rate_limit import limiter
from app.security.encryption import decrypt_if_enabled
from app.config import get_settings
from app.logging_config import get_logger

settings = get_settings()
logger = get_logger(__name__)
router = APIRouter()

MAX_MESSAGE_LENGTH = 4000

_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard your instructions",
    "you are now",
    "new instructions:",
    "system prompt:",
    "forget everything",
]


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    client_id: Optional[str] = None
    doc_types: Optional[List[str]] = None
    company_filter: Optional[str] = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message cannot be empty")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters")
        lower = v.lower()
        for pattern in _INJECTION_PATTERNS:
            if pattern in lower:
                raise ValueError("message contains disallowed content")
        return v


class CitationResponse(BaseModel):
    chunk_id: str
    doc_title: str
    section: str
    quote: str
    page: Optional[int] = None
    url: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    intent: str
    citations: List[CitationResponse]
    confidence: str
    flags: dict
    latency_ms: int
    # Populated only when the system refuses to answer. Plain-language explanation
    # of why, what sources were searched, and what the user can do — for accessible UX.
    refusal_reason: Optional[str] = None


@router.post("/", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat(
    request: Request,  # required by slowapi for rate limiting
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process a chat message through the RAG pipeline."""
    conversation_id = body.conversation_id

    if not conversation_id:
        client_uuid: Optional[uuid.UUID] = None
        if body.client_id:
            try:
                client_uuid = uuid.UUID(body.client_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="client_id is not a valid UUID")

        conversation = Conversation(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            client_id=client_uuid,
            title=body.message[:100],
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        conversation_id = str(conversation.id)
    else:
        try:
            conv_uuid = uuid.UUID(conversation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="conversation_id is not a valid UUID")

        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conv_uuid,
                Conversation.tenant_id == current_user.tenant_id,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Conversation not found")

    try:
        state = await run_workflow(
            db=db,
            tenant_id=str(current_user.tenant_id),
            client_id=body.client_id,
            user_id=str(current_user.id),
            user_role=current_user.role,
            conversation_id=conversation_id,
            user_query=body.message,
            doc_types=body.doc_types,
            company_filter=body.company_filter,
        )

        return ChatResponse(
            response=state.final_response,
            conversation_id=conversation_id,
            intent=state.intent,
            citations=[
                CitationResponse(
                    chunk_id=c.chunk_id,
                    doc_title=c.doc_title,
                    section=c.section,
                    quote=c.quote,
                    page=c.page,
                    url=c.url,
                )
                for c in state.citations
            ],
            confidence=state.flags.get("confidence", "medium"),
            flags=state.flags,
            latency_ms=state.latency_ms,
            refusal_reason=state.refusal_reason,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "Unhandled workflow error",
            extra={"conversation_id": conversation_id, "user_id": str(current_user.id)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your request. Please try again.",
        )


@router.get("/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 50,
):
    """List conversations for the authenticated user's tenant."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.tenant_id == current_user.tenant_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return [
        {"id": str(c.id), "title": c.title, "created_at": c.created_at.isoformat()}
        for c in result.scalars().all()
    ]


@router.get("/conversations/{conversation_id}/history")
async def get_conversation_history(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the full turn-by-turn audit trail for a conversation.

    Each turn includes the original query, the generated response, all cited
    sources with quotes and page references, confidence level, compliance flags,
    and whether the response was flagged for human review.

    This supports human-centered workflow design: advisors can review the
    complete evidence trail behind any decision, share it with supervisors,
    or flag turns for compliance review — without leaving the application.
    """
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="conversation_id is not a valid UUID")

    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.tenant_id == current_user.tenant_id,
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    log_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.conversation_id == conv_uuid)
        .order_by(AuditLog.created_at.asc())
    )
    logs = log_result.scalars().all()

    return {
        "conversation_id": conversation_id,
        "turns": [
            {
                "turn_id": str(log.id),
                "query": decrypt_if_enabled(log.user_query),
                "response": decrypt_if_enabled(log.response_text),
                "intent": log.workflow,
                "confidence": log.confidence_level,
                "citations": log.citations,
                "flags": log.flags,
                "flagged_for_review": log.flagged_for_review,
                "review_note": log.review_note,
                "latency_ms": log.latency_ms,
                "timestamp": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }
