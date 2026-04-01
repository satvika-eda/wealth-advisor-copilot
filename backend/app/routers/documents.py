"""Documents router for ingestion and management."""
import asyncio
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import ROLE_SENSITIVITY_ACCESS
from app.auth.dependencies import get_current_user, require_role
from app.db.database import get_db, AsyncSessionLocal
from app.db.models import Document, Chunk, User
from app.logging_config import get_logger
from app.rate_limit import limiter
from app.rag.parser import DocumentParser
from app.rag.chunker import Chunker, ChunkingStrategy
from app.rag.embedder import Embedder
from app.config import get_settings

settings = get_settings()

logger = get_logger(__name__)

_MAX_INGEST_RETRIES = 3
_RETRY_BACKOFF_SECONDS = [2, 5, 15]  # exponential-ish back-off

router = APIRouter()


def _check_sensitivity_access(user_role: str, sensitivity_level: str) -> bool:
    return sensitivity_level in ROLE_SENSITIVITY_ACCESS.get(user_role, set())


class DocumentCreate(BaseModel):
    title: str
    content: Optional[str] = None
    url: Optional[str] = None
    source_type: str = "manual"
    client_id: Optional[str] = None
    company_name: Optional[str] = None
    filing_type: Optional[str] = None
    sensitivity_level: str = "internal"  # public, internal, confidential, restricted
    expires_at: Optional[datetime] = None


class EdgarIngestRequest(BaseModel):
    cik: str
    filing_type: str = "10-K"
    accession_number: Optional[str] = None
    client_id: Optional[str] = None
    sensitivity_level: str = "internal"


class DocumentResponse(BaseModel):
    id: str
    title: str
    source_type: str
    source_url: Optional[str]
    company_name: Optional[str]
    filing_type: Optional[str]
    sensitivity_level: str
    is_approved: bool
    ingestion_status: str   # pending | processing | completed | failed
    ingestion_error: Optional[str]
    chunk_count: int
    created_at: str


async def ingest_document_async(
    document_id: uuid.UUID,
    content: str,
    sections: list,
    tenant_id: uuid.UUID,
    client_id: Optional[uuid.UUID],
):
    """
    Background task: chunk, embed, and store a document with retry logic.

    Uses its own DB session (not the request session, which closes after the
    response is sent). Updates ingestion_status on the Document so callers
    can poll GET /documents/{id} to see progress.
    """
    for attempt in range(1, _MAX_INGEST_RETRIES + 1):
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(select(Document).where(Document.id == document_id))
                document = result.scalar_one_or_none()
                if not document:
                    logger.error("Ingest: document not found", extra={"document_id": str(document_id)})
                    return

                document.ingestion_status = "processing"
                await db.commit()

                chunker = Chunker(strategy=ChunkingStrategy.SECTION_BASED)
                embedder = Embedder()

                doc_metadata = {
                    "doc_id": str(document.id),
                    "doc_title": document.title,
                    "company": document.company_name,
                    "filing_type": document.filing_type,
                }

                chunks = chunker.chunk_document(content, sections, doc_metadata)
                if not chunks:
                    document.ingestion_status = "completed"
                    await db.commit()
                    logger.warning("Ingest: no chunks produced", extra={"document_id": str(document_id)})
                    return

                embeddings = await embedder.embed_texts([c.content for c in chunks])

                for chunk, embedding in zip(chunks, embeddings):
                    db.add(Chunk(
                        document_id=document.id,
                        tenant_id=tenant_id,
                        client_id=client_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        token_count=chunk.token_count,
                        chunk_metadata=chunk.metadata,
                        embedding=embedding,
                    ))

                document.ingestion_status = "completed"
                document.ingestion_error = None
                await db.commit()

                logger.info(
                    "Ingest completed",
                    extra={"document_id": str(document_id), "chunks": len(chunks)},
                )
                return  # success

            except Exception as exc:
                await db.rollback()
                logger.warning(
                    "Ingest attempt %d/%d failed",
                    attempt,
                    _MAX_INGEST_RETRIES,
                    extra={"document_id": str(document_id), "error": str(exc)},
                    exc_info=True,
                )
                if attempt < _MAX_INGEST_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS[attempt - 1])
                else:
                    # Final failure — record it on the document
                    async with AsyncSessionLocal() as db2:
                        result = await db2.execute(select(Document).where(Document.id == document_id))
                        if doc := result.scalar_one_or_none():
                            doc.ingestion_status = "failed"
                            doc.ingestion_error = str(exc)
                            await db2.commit()
                    logger.error(
                        "Ingest permanently failed after %d attempts",
                        _MAX_INGEST_RETRIES,
                        extra={"document_id": str(document_id)},
                        exc_info=True,
                    )


@router.post("/", response_model=DocumentResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_INGEST)
async def create_document(
    request: Request,
    doc: DocumentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create and ingest a document. Advisors can only create internal/public documents."""
    if not _check_sensitivity_access(current_user.role, doc.sensitivity_level):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_user.role}' cannot create '{doc.sensitivity_level}' documents",
        )

    parser = DocumentParser(redact_pii=True)

    if doc.content:
        parsed = parser.parse_text(doc.content, title=doc.title, source_url=doc.url)
    elif doc.url:
        parsed = await parser.parse_web_url(doc.url)
    else:
        raise HTTPException(status_code=400, detail="content or url required")

    existing = await db.execute(
        select(Document).where(
            Document.tenant_id == current_user.tenant_id,
            Document.sha256 == parsed.sha256,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Document already exists")

    if doc.client_id:
        try:
            client_id: Optional[uuid.UUID] = uuid.UUID(doc.client_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="client_id is not a valid UUID") from exc
    else:
        client_id = None

    document = Document(
        tenant_id=current_user.tenant_id,
        client_id=client_id,
        title=doc.title or parsed.title,
        source_type=doc.source_type,
        source_url=doc.url,
        sha256=parsed.sha256,
        company_name=doc.company_name,
        filing_type=doc.filing_type,
        doc_metadata=parsed.metadata,
        sensitivity_level=doc.sensitivity_level,
        is_approved=False,  # Requires explicit approval
        expires_at=doc.expires_at,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    background_tasks.add_task(
        ingest_document_async, document.id, parsed.content, parsed.sections,
        current_user.tenant_id, client_id,
    )

    return _doc_response(document, chunk_count=0)


@router.post("/upload", response_model=DocumentResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_INGEST)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
    sensitivity_level: str = Form("internal"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload and ingest a file."""
    import tempfile
    import os

    if not _check_sensitivity_access(current_user.role, sensitivity_level):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_user.role}' cannot create '{sensitivity_level}' documents",
        )

    parser = DocumentParser(redact_pii=True)

    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if suffix.lower() == ".pdf":
            parsed = parser.parse_pdf(tmp_path, title=title or file.filename)
        else:
            text = content.decode("utf-8", errors="ignore")
            parsed = parser.parse_text(text, title=title or file.filename)
    finally:
        os.unlink(tmp_path)

    if client_id:
        try:
            client_uuid: Optional[uuid.UUID] = uuid.UUID(client_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="client_id is not a valid UUID") from exc
    else:
        client_uuid = None

    document = Document(
        tenant_id=current_user.tenant_id,
        client_id=client_uuid,
        title=title or file.filename,
        source_type="pdf" if suffix.lower() == ".pdf" else "text",
        sha256=parsed.sha256,
        company_name=company_name,
        doc_metadata=parsed.metadata,
        sensitivity_level=sensitivity_level,
        is_approved=False,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    if background_tasks:
        background_tasks.add_task(
            ingest_document_async, document.id, parsed.content, parsed.sections,
            current_user.tenant_id, client_uuid,
        )

    return _doc_response(document, chunk_count=0)


@router.post("/edgar", response_model=DocumentResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_INGEST)
async def ingest_edgar(
    request: Request,
    body: EdgarIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ingest SEC EDGAR filing."""
    parser = DocumentParser(redact_pii=True)

    parsed = await parser.parse_edgar_filing(body.cik, body.filing_type, body.accession_number)

    if body.client_id:
        try:
            client_uuid: Optional[uuid.UUID] = uuid.UUID(body.client_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="client_id is not a valid UUID") from exc
    else:
        client_uuid = None

    document = Document(
        tenant_id=current_user.tenant_id,
        client_id=client_uuid,
        title=parsed.title,
        source_type="edgar",
        source_url=parsed.source_url,
        sha256=parsed.sha256,
        company_name=parsed.metadata.get("company_name"),
        cik=body.cik,
        filing_type=body.filing_type,
        doc_metadata=parsed.metadata,
        sensitivity_level=body.sensitivity_level,
        is_approved=False,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    background_tasks.add_task(
        ingest_document_async, document.id, parsed.content, parsed.sections,
        current_user.tenant_id, client_uuid,
    )

    return _doc_response(document, chunk_count=0)


@router.post("/{document_id}/approve", response_model=DocumentResponse)
async def approve_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "compliance")),
):
    """Approve a document for RAG retrieval. Requires admin or compliance role."""
    doc = await _get_tenant_doc(db, document_id, current_user.tenant_id)
    doc.is_approved = True
    await db.commit()
    await db.refresh(doc)

    chunk_count = await db.execute(select(func.count()).where(Chunk.document_id == doc.id))
    return _doc_response(doc, chunk_count=chunk_count.scalar() or 0)


@router.get("/")
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = 1,
    per_page: int = 20,
):
    """List documents accessible to the current user's role."""
    accessible = ROLE_SENSITIVITY_ACCESS.get(current_user.role, set())

    count_result = await db.execute(
        select(func.count()).select_from(Document).where(
            Document.tenant_id == current_user.tenant_id,
            Document.sensitivity_level.in_(accessible),
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Document)
        .where(
            Document.tenant_id == current_user.tenant_id,
            Document.sensitivity_level.in_(accessible),
        )
        .order_by(Document.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    docs = []
    for doc in result.scalars().all():
        chunk_count = await db.execute(select(func.count()).where(Chunk.document_id == doc.id))
        docs.append(_doc_response(doc, chunk_count=chunk_count.scalar() or 0))

    return {"documents": docs, "total": total, "page": page, "per_page": per_page}


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin", "compliance")),
):
    """Delete a document. Requires admin or compliance role."""
    doc = await _get_tenant_doc(db, document_id, current_user.tenant_id)
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted", "document_id": document_id}



async def _get_tenant_doc(db: AsyncSession, document_id: str, tenant_id: uuid.UUID) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(document_id),
            Document.tenant_id == tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _doc_response(doc: Document, chunk_count: int) -> DocumentResponse:
    return DocumentResponse(
        id=str(doc.id),
        title=doc.title,
        source_type=doc.source_type,
        source_url=doc.source_url,
        company_name=doc.company_name,
        filing_type=doc.filing_type,
        sensitivity_level=doc.sensitivity_level,
        is_approved=doc.is_approved,
        ingestion_status=doc.ingestion_status,
        ingestion_error=doc.ingestion_error,
        chunk_count=chunk_count,
        created_at=doc.created_at.isoformat(),
    )
