"""Documents router for ingestion and management."""
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Document, Chunk
from app.rag.parser import DocumentParser
from app.rag.chunker import Chunker, ChunkingStrategy
from app.rag.embedder import Embedder

router = APIRouter()

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


class DocumentCreate(BaseModel):
    title: str
    content: Optional[str] = None
    url: Optional[str] = None
    source_type: str = "manual"
    client_id: Optional[str] = None
    company_name: Optional[str] = None
    filing_type: Optional[str] = None


class EdgarIngestRequest(BaseModel):
    cik: str
    filing_type: str = "10-K"
    accession_number: Optional[str] = None
    client_id: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    title: str
    source_type: str
    source_url: Optional[str]
    company_name: Optional[str]
    filing_type: Optional[str]
    chunk_count: int
    created_at: str


async def ingest_document_async(
    db: AsyncSession,
    document: Document,
    content: str,
    sections: list,
    tenant_id: uuid.UUID,
    client_id: Optional[uuid.UUID],
):
    """Background task to chunk and embed a document."""
    try:
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
        
        await db.commit()
    except Exception as e:
        print(f"Ingestion error: {e}")
        await db.rollback()


@router.post("/", response_model=DocumentResponse)
async def create_document(
    doc: DocumentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Create and ingest a document."""
    parser = DocumentParser(redact_pii=True)
    tenant_id = uuid.UUID(DEFAULT_TENANT_ID)
    
    if doc.content:
        parsed = parser.parse_text(doc.content, title=doc.title, source_url=doc.url)
    elif doc.url:
        parsed = await parser.parse_web_url(doc.url)
    else:
        raise HTTPException(status_code=400, detail="content or url required")
    
    # Check duplicate
    existing = await db.execute(
        select(Document).where(Document.tenant_id == tenant_id, Document.sha256 == parsed.sha256)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Document already exists")
    
    client_id = uuid.UUID(doc.client_id) if doc.client_id else None
    
    document = Document(
        tenant_id=tenant_id,
        client_id=client_id,
        title=doc.title or parsed.title,
        source_type=doc.source_type,
        source_url=doc.url,
        sha256=parsed.sha256,
        company_name=doc.company_name,
        filing_type=doc.filing_type,
        doc_metadata=parsed.metadata,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    background_tasks.add_task(ingest_document_async, db, document, parsed.content, parsed.sections, tenant_id, client_id)
    
    return DocumentResponse(
        id=str(document.id),
        title=document.title,
        source_type=document.source_type,
        source_url=document.source_url,
        company_name=document.company_name,
        filing_type=document.filing_type,
        chunk_count=0,
        created_at=document.created_at.isoformat(),
    )


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """Upload and ingest a file."""
    import tempfile
    import os
    
    parser = DocumentParser(redact_pii=True)
    tenant_id = uuid.UUID(DEFAULT_TENANT_ID)
    
    # Save temp file
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
    
    client_uuid = uuid.UUID(client_id) if client_id else None
    
    document = Document(
        tenant_id=tenant_id,
        client_id=client_uuid,
        title=title or file.filename,
        source_type="pdf" if suffix.lower() == ".pdf" else "text",
        sha256=parsed.sha256,
        company_name=company_name,
        doc_metadata=parsed.metadata,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    if background_tasks:
        background_tasks.add_task(ingest_document_async, db, document, parsed.content, parsed.sections, tenant_id, client_uuid)
    
    return DocumentResponse(
        id=str(document.id),
        title=document.title,
        source_type=document.source_type,
        source_url=None,
        company_name=document.company_name,
        filing_type=None,
        chunk_count=0,
        created_at=document.created_at.isoformat(),
    )


@router.post("/edgar", response_model=DocumentResponse)
async def ingest_edgar(
    request: EdgarIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Ingest SEC EDGAR filing."""
    parser = DocumentParser(redact_pii=True)
    tenant_id = uuid.UUID(DEFAULT_TENANT_ID)
    
    parsed = await parser.parse_edgar_filing(request.cik, request.filing_type, request.accession_number)
    
    client_uuid = uuid.UUID(request.client_id) if request.client_id else None
    
    document = Document(
        tenant_id=tenant_id,
        client_id=client_uuid,
        title=parsed.title,
        source_type="edgar",
        source_url=parsed.source_url,
        sha256=parsed.sha256,
        company_name=parsed.metadata.get("company_name"),
        cik=request.cik,
        filing_type=request.filing_type,
        doc_metadata=parsed.metadata,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    background_tasks.add_task(ingest_document_async, db, document, parsed.content, parsed.sections, tenant_id, client_uuid)
    
    return DocumentResponse(
        id=str(document.id),
        title=document.title,
        source_type=document.source_type,
        source_url=document.source_url,
        company_name=document.company_name,
        filing_type=document.filing_type,
        chunk_count=0,
        created_at=document.created_at.isoformat(),
    )


@router.get("/")
async def list_documents(db: AsyncSession = Depends(get_db), page: int = 1, per_page: int = 20):
    """List documents."""
    tenant_id = uuid.UUID(DEFAULT_TENANT_ID)
    
    # Get total count
    count_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
    )
    total = count_result.scalar() or 0
    
    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == tenant_id)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    
    docs = []
    for doc in result.scalars().all():
        chunk_count = await db.execute(select(func.count()).where(Chunk.document_id == doc.id))
        docs.append(DocumentResponse(
            id=str(doc.id),
            title=doc.title,
            source_type=doc.source_type,
            source_url=doc.source_url,
            company_name=doc.company_name,
            filing_type=doc.filing_type,
            chunk_count=chunk_count.scalar() or 0,
            created_at=doc.created_at.isoformat(),
        ))
    
    return {"documents": docs, "total": total, "page": page, "per_page": per_page}


@router.delete("/{document_id}")
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a document."""
    result = await db.execute(
        select(Document).where(
            Document.id == uuid.UUID(document_id),
            Document.tenant_id == uuid.UUID(DEFAULT_TENANT_ID),
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}
