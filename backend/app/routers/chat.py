"""Chat router for RAG-powered conversations."""
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Conversation
from app.graphs.workflow import run_workflow
from app.config import get_settings

settings = get_settings()
router = APIRouter()

# Default tenant/user for demo (no auth)
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    client_id: Optional[str] = None
    doc_types: Optional[List[str]] = None
    company_filter: Optional[str] = None


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


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Process a chat message through the RAG pipeline."""
    conversation_id = request.conversation_id
    
    if not conversation_id:
        conversation = Conversation(
            tenant_id=uuid.UUID(DEFAULT_TENANT_ID),
            user_id=uuid.UUID(DEFAULT_USER_ID),
            client_id=uuid.UUID(request.client_id) if request.client_id else None,
            title=request.message[:100],
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        conversation_id = str(conversation.id)
    
    try:
        state = await run_workflow(
            db=db,
            tenant_id=DEFAULT_TENANT_ID,
            client_id=request.client_id,
            user_id=DEFAULT_USER_ID,
            conversation_id=conversation_id,
            user_query=request.message,
            doc_types=request.doc_types,
            company_filter=request.company_filter,
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
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db), limit: int = 50):
    """List conversations."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.tenant_id == uuid.UUID(DEFAULT_TENANT_ID))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return [
        {"id": str(c.id), "title": c.title, "created_at": c.created_at.isoformat()}
        for c in result.scalars().all()
    ]
