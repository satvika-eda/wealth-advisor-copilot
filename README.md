# Wealth Advisor Copilot

A production-grade RAG assistant for wealth advisors. Ask questions about SEC filings in plain English — get cited, sourced answers backed by real regulatory documents.

## Features

- **Live SEC EDGAR integration** — import 10-Ks, 10-Qs, and 8-Ks directly by ticker symbol
- **Upload your own documents** — PDFs, HTML, plain text
- **LangGraph RAG pipeline** — intent routing → policy check → vector retrieval → cross-encoder reranking → GPT-4o generation → citation formatting
- **Full RBAC** — advisor / compliance / admin roles; sensitive documents restricted by role
- **Multi-tenant** — each organization's data stays isolated
- **Azure OpenAI support** — zero-code swap; just set env vars
- **Audit log** — every query/response stored for compliance review
- **Field-level encryption** — audit log entries encrypted at rest with Fernet

## Architecture

```
User question
    │
    ▼
[Intent Router]          (LangGraph node — classifies: qa / out_of_scope)
    │
    ▼
[Policy Check]           (role × document sensitivity gate)
    │
    ▼
[Vector Retrieval]       (pgvector HNSW index, top-30 candidates)
    │
    ▼
[Cross-Encoder Rerank]   (Cohere Rerank v3, selects top-10)
    │
    ▼
[Evidence Check]         (refuses if insufficient grounding)
    │
    ▼
[GPT-4o Generation]      (context-only, citation-anchored prompt)
    │
    ▼
[Format Citations]  →  [Audit Logger]
```

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI (async) |
| Workflow | LangGraph |
| LLM | OpenAI GPT-4o / Azure OpenAI |
| Embeddings | text-embedding-3-small |
| Vector store | PostgreSQL + pgvector (HNSW) |
| Reranking | Cohere Rerank v3 |
| Database | PostgreSQL 16 via SQLAlchemy async + asyncpg |
| Auth | JWT (HS256), bcrypt password hashing |
| Frontend | React + Vite + TailwindCSS |

## Quick Start (Docker)

**Prerequisites:** Docker Desktop, OpenAI API key

```bash
git clone https://github.com/your-org/wealth-advisor-copilot.git
cd wealth-advisor-copilot

cp .env.example .env
# Edit .env — set OPENAI_API_KEY and JWT_SECRET_KEY

docker compose up -d
```

Open **http://localhost:3000** — the app is running.

Default admin account (if `ADMIN_SEED_PASSWORD` is set in `.env`):
- Email: `admin@wealthadvisor.local`
- Password: value of `ADMIN_SEED_PASSWORD`

Or register a new advisor account from the login page.

## Local Development (without Docker)

**Prerequisites:** Python 3.11+, Node 20+, PostgreSQL 16 with pgvector

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in your keys
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Backend: http://localhost:8000
Frontend: http://localhost:5173
API docs: http://localhost:8000/docs

## Azure OpenAI

To use Azure instead of OpenAI direct, uncomment and fill in `.env`:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-azure-key
AZURE_OPENAI_API_VERSION=2024-08-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

No code changes needed — the app detects these vars and switches clients automatically.

## Import SEC Filings

```bash
# Import Apple's latest 10-K via EDGAR API
curl -X POST http://localhost:8000/api/v1/documents/edgar \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "form_type": "10-K", "limit": 1}'
```

## Running Tests

Requires PostgreSQL with a `wealth_advisor_test` database:

```bash
psql -U postgres -c "CREATE DATABASE wealth_advisor_test;"
psql -U postgres -d wealth_advisor_test -c "CREATE EXTENSION IF NOT EXISTS vector;"

cd backend
python -m pytest tests/ -v
```

26 tests covering auth, chat input validation, document endpoints, and RBAC.

## Security Notes

- Prompt injection patterns blocked at the API layer
- Rate limiting on all endpoints (slowapi)
- HTTPS redirect enforced in production (`DEBUG=false`)
- Docs (`/docs`, `/redoc`) hidden in production
- Startup validation fails fast if `JWT_SECRET_KEY` is the default placeholder
- Field-level encryption available for audit log PII

## Project Layout

```
backend/
  app/
    routers/      auth, chat, documents, admin
    graphs/       LangGraph nodes and workflow
    rag/          chunker, embedder, retriever, reranker, parser
    db/           SQLAlchemy models (User, Document, Chunk, AuditLog, …)
    auth/         JWT creation/validation, RBAC dependencies
    security/     Fernet field encryption
  tests/          pytest suite (26 tests, PostgreSQL)
  alembic/        database migrations

frontend/
  src/
    components/   Chat, Documents, Admin, Login, Register
    context/      AuthContext (JWT storage, axios interceptors)
```

## Learn More

- [Architecture](docs/ARCHITECTURE.md)
- [Threat Model](docs/THREAT_MODEL.md)
