"""Admin router for audit logs. Requires admin or compliance role."""
import uuid
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.db.database import get_db
from app.db.models import AuditLog, Conversation, User
from app.rate_limit import limiter
from app.security.encryption import decrypt_if_enabled
from app.config import get_settings

settings = get_settings()
router = APIRouter()

class AuditLogResponse(BaseModel):
    id: str
    conversation_id: str
    user_id: Optional[str]
    user_query: str
    workflow: str
    model_name: str
    response_text: str
    citations: dict
    latency_ms: int
    confidence_level: str
    flags: dict
    flagged_for_review: bool
    review_note: Optional[str]
    created_at: str

class FlagRequest(BaseModel):
    note: Optional[str] = None  # Optional reviewer note explaining why it was flagged

@router.get("/audit-logs")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_audit_logs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "compliance")),
    page: int = 1,
    per_page: int = 50,
    workflow: Optional[str] = None,
    confidence: Optional[str] = None,
):
    """List audit logs. Requires admin or compliance role."""
    base = (
        select(AuditLog)
        .join(Conversation)
        .where(Conversation.tenant_id == current_user.tenant_id)
    )

    if workflow:
        base = base.where(AuditLog.workflow == workflow)
    if confidence:
        base = base.where(AuditLog.confidence_level == confidence)

    query = base.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    logs = result.scalars().all()

    count_result = await db.execute(
        select(func.count(AuditLog.id))
        .join(Conversation)
        .where(Conversation.tenant_id == current_user.tenant_id)
    )
    total = count_result.scalar() or 0

    return {
        "logs": [_log_response(log, truncate=True) for log in logs],
        "total": total,
        "page": page,
        "per_page": per_page,
    }

@router.get("/stats")
@limiter.limit("10/minute")  # Tighter limit — this query aggregates DB data
async def get_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "compliance")),
    days: int = 7,
):
    """Dashboard statistics using DB aggregation. Requires admin or compliance role."""
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365")

    since = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)

    # Single query — aggregate in the database, not Python
    row = await db.execute(
        select(
            func.count(AuditLog.id).label("total"),
            func.avg(AuditLog.latency_ms).label("avg_latency"),
            func.sum(
                case((AuditLog.flags["low_evidence"].as_boolean(), 1), else_=0)
            ).label("low_evidence_count"),
            func.sum(
                case((AuditLog.flags["pii_detected"].as_boolean(), 1), else_=0)
            ).label("pii_detected_count"),
            func.sum(
                case((AuditLog.flags["possible_hallucination"].as_boolean(), 1), else_=0)
            ).label("hallucination_flag_count"),
            func.sum(
                case((AuditLog.flags["advice_refused"].as_boolean(), 1), else_=0)
            ).label("advice_refused_count"),
            func.sum(
                case((AuditLog.confidence_level == "high", 1), else_=0)
            ).label("conf_high"),
            func.sum(
                case((AuditLog.confidence_level == "medium", 1), else_=0)
            ).label("conf_medium"),
            func.sum(
                case((AuditLog.confidence_level == "low", 1), else_=0)
            ).label("conf_low"),
        )
        .join(Conversation)
        .where(
            Conversation.tenant_id == current_user.tenant_id,
            AuditLog.created_at >= since,
        )
    )
    r = row.one()

    total = r.total or 0
    return {
        "total_queries": total,
        "avg_latency_ms": round(float(r.avg_latency or 0), 1),
        "low_evidence_count": int(r.low_evidence_count or 0),
        "pii_detected_count": int(r.pii_detected_count or 0),
        "hallucination_flag_count": int(r.hallucination_flag_count or 0),
        "advice_refused_count": int(r.advice_refused_count or 0),
        "confidence_distribution": {
            "high": int(r.conf_high or 0),
            "medium": int(r.conf_medium or 0),
            "low": int(r.conf_low or 0),
        },
    }

@router.get("/audit-logs/flagged")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_flagged(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "compliance")),
    page: int = 1,
    per_page: int = 50,
):
    """List all responses flagged for human review."""
    query = (
        select(AuditLog)
        .join(Conversation)
        .where(
            Conversation.tenant_id == current_user.tenant_id,
            AuditLog.flagged_for_review == True,  # noqa: E712
        )
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    logs = result.scalars().all()
    return {"flagged": [_log_response(log, truncate=True) for log in logs]}

@router.get("/audit-logs/{log_id}")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_audit_log(
    request: Request,
    log_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "compliance")),
):
    """Get a single audit log. Requires admin or compliance role."""
    try:
        log_uuid = uuid.UUID(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="log_id is not a valid UUID") from exc

    result = await db.execute(
        select(AuditLog)
        .join(Conversation)
        .where(
            AuditLog.id == log_uuid,
            Conversation.tenant_id == current_user.tenant_id,
        )
    )
    if not (log := result.scalar_one_or_none()):
        raise HTTPException(status_code=404, detail="Audit log not found")
    return _log_response(log, truncate=False)

@router.post("/audit-logs/{log_id}/flag")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def flag_for_review(
    request: Request,
    log_id: str,
    body: FlagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "compliance")),
):
    """
    Flag a response for human review.

    Marks the audit log entry so a compliance officer or admin can manually
    inspect the query, retrieved sources, and generated response. Supports
    the human-in-the-loop review path for sensitive or low-confidence outputs.
    """
    try:
        log_uuid = uuid.UUID(log_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="log_id is not a valid UUID") from exc

    result = await db.execute(
        select(AuditLog)
        .join(Conversation)
        .where(
            AuditLog.id == log_uuid,
            Conversation.tenant_id == current_user.tenant_id,
        )
    )
    if not (log := result.scalar_one_or_none()):
        raise HTTPException(status_code=404, detail="Audit log not found")

    log.flagged_for_review = True
    log.review_note = body.note
    await db.commit()

    return {"status": "flagged", "log_id": log_id, "review_note": body.note}

def _log_response(log: AuditLog, truncate: bool) -> AuditLogResponse:
    query = decrypt_if_enabled(log.user_query)
    response = decrypt_if_enabled(log.response_text)
    text = response[:500] if truncate else response
    return AuditLogResponse(
        id=str(log.id),
        conversation_id=str(log.conversation_id),
        user_id=str(log.user_id) if log.user_id else None,
        user_query=query,
        workflow=log.workflow,
        model_name=log.model_name,
        response_text=text,
        citations=log.citations,
        latency_ms=log.latency_ms,
        confidence_level=log.confidence_level,
        flags=log.flags,
        flagged_for_review=log.flagged_for_review,
        review_note=log.review_note,
        created_at=log.created_at.isoformat(),
    )
