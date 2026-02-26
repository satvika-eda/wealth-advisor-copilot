"""Admin router for audit logs."""
import uuid
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import AuditLog, Conversation

router = APIRouter()

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


class AuditLogResponse(BaseModel):
    id: str
    conversation_id: str
    user_query: str
    workflow: str
    model_name: str
    response_text: str
    citations: dict
    latency_ms: int
    confidence_level: str
    flags: dict
    created_at: str


@router.get("/audit-logs")
async def list_audit_logs(
    db: AsyncSession = Depends(get_db),
    page: int = 1,
    per_page: int = 50,
    workflow: Optional[str] = None,
    confidence: Optional[str] = None,
):
    """List audit logs."""
    tenant_id = uuid.UUID(DEFAULT_TENANT_ID)
    
    query = (
        select(AuditLog)
        .join(Conversation)
        .where(Conversation.tenant_id == tenant_id)
    )
    
    if workflow:
        query = query.where(AuditLog.workflow == workflow)
    if confidence:
        query = query.where(AuditLog.confidence_level == confidence)
    
    query = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    count_result = await db.execute(
        select(func.count(AuditLog.id))
        .join(Conversation)
        .where(Conversation.tenant_id == tenant_id)
    )
    total = count_result.scalar() or 0
    
    return {
        "logs": [
            AuditLogResponse(
                id=str(log.id),
                conversation_id=str(log.conversation_id),
                user_query=log.user_query,
                workflow=log.workflow,
                model_name=log.model_name,
                response_text=log.response_text[:500],
                citations=log.citations,
                latency_ms=log.latency_ms,
                confidence_level=log.confidence_level,
                flags=log.flags,
                created_at=log.created_at.isoformat(),
            )
            for log in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), days: int = 7):
    """Get audit statistics."""
    tenant_id = uuid.UUID(DEFAULT_TENANT_ID)
    since = datetime.utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(AuditLog)
        .join(Conversation)
        .where(Conversation.tenant_id == tenant_id, AuditLog.created_at >= since)
    )
    logs = result.scalars().all()
    
    if not logs:
        return {"total_queries": 0, "avg_latency_ms": 0}
    
    return {
        "total_queries": len(logs),
        "avg_latency_ms": sum(l.latency_ms for l in logs) / len(logs),
        "low_evidence_count": sum(1 for l in logs if l.flags.get("low_evidence")),
        "confidence_distribution": {
            "high": sum(1 for l in logs if l.confidence_level == "high"),
            "medium": sum(1 for l in logs if l.confidence_level == "medium"),
            "low": sum(1 for l in logs if l.confidence_level == "low"),
        },
    }


@router.get("/audit-logs/{log_id}")
async def get_audit_log(log_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single audit log."""
    result = await db.execute(select(AuditLog).where(AuditLog.id == uuid.UUID(log_id)))
    log = result.scalar_one_or_none()
    
    if not log:
        return {"error": "Not found"}
    
    return AuditLogResponse(
        id=str(log.id),
        conversation_id=str(log.conversation_id),
        user_query=log.user_query,
        workflow=log.workflow,
        model_name=log.model_name,
        response_text=log.response_text,
        citations=log.citations,
        latency_ms=log.latency_ms,
        confidence_level=log.confidence_level,
        flags=log.flags,
        created_at=log.created_at.isoformat(),
    )
