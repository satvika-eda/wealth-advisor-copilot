# Wealth Advisor Copilot Architecture

## System Overview

Enterprise-grade RAG (Retrieval Augmented Generation) system for wealth advisors, featuring multi-tenant security, audit logging, and compliance guardrails.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                                │
│  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────────────────┐ │
│  │   Chat UI    │  │   Documents UI   │  │      Admin/Audit Panel         │ │
│  │  + Citations │  │   + EDGAR Import │  │  + Stats  + Flagged Queries    │ │
│  └──────────────┘  └──────────────────┘  └────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ REST API (JWT Auth)
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          BACKEND (FastAPI)                                    │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                      LangGraph Workflow                                 │  │
│  │  ┌──────────┐  ┌───────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐ │  │
│  │  │ Intent   │→ │ Retrieve  │→ │ Check   │→ │ Generate │→ │ Format   │ │  │
│  │  │ Router   │  │ Evidence  │  │Evidence │  │ Response │  │Citations │ │  │
│  │  └──────────┘  └───────────┘  └─────────┘  └──────────┘  └──────────┘ │  │
│  │       │              │                            │             │      │  │
│  │       ▼              ▼                            ▼             ▼      │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │  │
│  │  │                      AUDIT LOGGER                                 │ │  │
│  │  │  query | chunks | scores | response | citations | flags | latency│ │  │
│  │  └──────────────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────┐  ┌──────────────────────────────────────────┐ │
│  │     RAG Pipeline         │  │          Document Ingestion              │ │
│  │  ┌────────┐ ┌─────────┐  │  │  ┌────────┐ ┌────────┐ ┌─────────────┐  │ │
│  │  │Embedder│ │Retriever│  │  │  │ Parser │ │Chunker │ │ PII Redactor│  │ │
│  │  │(OpenAI)│ │(pgvector)│ │  │  │PDF/HTML│ │Semantic│ │             │  │ │
│  │  └────────┘ └─────────┘  │  │  └────────┘ └────────┘ └─────────────┘  │ │
│  │  ┌─────────────────────┐ │  └──────────────────────────────────────────┘ │
│  │  │ Reranker (Cohere)   │ │                                                │
│  │  └─────────────────────┘ │                                                │
│  └──────────────────────────┘                                                │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       PostgreSQL + pgvector                                   │
│  ┌──────────────┐ ┌─────────────┐ ┌───────────────┐ ┌─────────────────────┐  │
│  │   tenants    │ │   users     │ │   documents   │ │      chunks         │  │
│  │   - id       │ │   - id      │ │   - id        │ │   - id              │  │
│  │   - name     │ │   - tenant  │ │   - tenant_id │ │   - document_id     │  │
│  └──────────────┘ │   - email   │ │   - client_id │ │   - embedding (1536)│  │
│                   │   - role    │ │   - sha256    │ │   - metadata        │  │
│                   └─────────────┘ │   - source    │ └─────────────────────┘  │
│                                   └───────────────┘                          │
│  ┌───────────────────┐ ┌─────────────────────────────────────────────────┐  │
│  │   conversations   │ │              audit_logs (THE MONEY TABLE)       │  │
│  │   - id            │ │   - id             - retrieved_chunk_ids        │  │
│  │   - tenant_id     │ │   - conversation   - retrieval_scores           │  │
│  │   - user_id       │ │   - user_query     - model_name                 │  │
│  │   - title         │ │   - workflow       - response_text              │  │
│  └───────────────────┘ │   - citations      - flags (low_evidence, etc.) │  │
│                        │   - latency_ms     - confidence_level           │  │
│                        └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Document Ingestion
```
Document (PDF/HTML/EDGAR)
    ↓
Parser (extract text, sections)
    ↓
PII Redactor (email, phone, SSN patterns)
    ↓
Chunker (800-1200 tokens, preserve headings)
    ↓
Embedder (OpenAI text-embedding-3-small)
    ↓
Store in chunks table with metadata
```

### 2. Query Processing
```
User Query
    ↓
Intent Classification (qa/summary/risk/email)
    ↓
Vector Retrieval (top 30, filtered by tenant_id + client_id)
    ↓
Reranking (Cohere, top 10)
    ↓
Evidence Check (sufficient? → refuse if not)
    ↓
Response Generation (GPT-4o with strict grounding)
    ↓
Citation Formatting
    ↓
Audit Logging (everything tracked)
    ↓
Return response + citations + metadata
```

## Security Layers

| Layer | Implementation |
|-------|---------------|
| **Authentication** | JWT tokens with tenant_id claim |
| **Multi-tenancy** | Every query filtered by tenant_id |
| **Client Isolation** | Optional client_id filter |
| **PII Protection** | Regex redaction before indexing |
| **Advice Guardrails** | Refusal patterns for investment advice |
| **Audit Trail** | Complete logging of all interactions |

## Key Differentiators

1. **audit_logs table** - Enterprise-grade compliance tracking
2. **Multi-tenant isolation** - Every query scoped to tenant
3. **Confidence scoring** - High/Medium/Low with evidence count
4. **Compliance flags** - Automatic detection of risky responses
5. **Citation precision** - Every claim linked to source
6. **Evaluation harness** - Built-in quality metrics

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.11) |
| Orchestration | LangGraph |
| LLM | OpenAI GPT-4o |
| Embeddings | OpenAI text-embedding-3-small |
| Vector Store | PostgreSQL + pgvector (HNSW index) |
| Reranking | Cohere Rerank v3 |
| Frontend | React + TailwindCSS |
| Auth | JWT + bcrypt |
| Deployment | Docker Compose |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/token` | POST | Login, get JWT |
| `/api/v1/auth/register` | POST | Create account |
| `/api/v1/chat/` | POST | Send message, get response |
| `/api/v1/documents/` | GET/POST | List/create documents |
| `/api/v1/documents/upload` | POST | Upload PDF/text |
| `/api/v1/documents/edgar` | POST | Import SEC filing |
| `/api/v1/admin/audit-logs` | GET | List audit logs |
| `/api/v1/admin/stats` | GET | Dashboard statistics |
| `/api/v1/admin/flagged-responses` | GET | Compliance review queue |

## Evaluation Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Behavior Accuracy | Correct action (answer vs refuse) | >90% |
| Groundedness | Claims supported by chunks | >80% |
| Citation Precision | Answers with proper citations | >85% |
| Abstention Accuracy | Refuse when no evidence | >95% |
| Avg Latency | Response time | <3000ms |
