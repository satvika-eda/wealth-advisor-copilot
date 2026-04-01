# Wealth Advisor Copilot

A RAG-powered assistant that lets wealth advisors query SEC filings in plain English and get cited, sourced answers.

![Architecture](docs/architecture.png)

## What it does

Upload a 10-K or pull filings directly from SEC EDGAR, then ask questions like *"What are Apple's main risk factors?"* — the system finds the relevant sections and returns a grounded answer with citations.

## Stack

- **FastAPI** — async REST API with JWT auth and rate limiting
- **LangGraph** — 7-node workflow (intent routing → policy check → retrieval → evidence check → generation → citations → audit)
- **GPT-4o** — answer generation, grounded to retrieved context only
- **PostgreSQL + pgvector** — HNSW vector search over document chunks
- **Cohere Rerank v3** — cross-encoder reranking before generation
- **React + Vite** — chat interface, document manager, admin dashboard
- **Azure OpenAI** — drop-in alternative; just set env vars, no code changes

## Quick start

**Requires:** Docker Desktop + an OpenAI API key

```bash
git clone https://github.com/satvika-eda/wealth-advisor-copilot.git
cd wealth-advisor-copilot

cp .env.example .env
# Set OPENAI_API_KEY and JWT_SECRET_KEY in .env

docker compose up -d
```

App: http://localhost:3000 · API docs: http://localhost:8000/docs

## Import SEC filings

```bash
# Get a token first
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=admin@wealthadvisor.local&password=yourpassword" | jq -r .access_token)

# Import Apple's latest 10-K
curl -X POST http://localhost:8000/api/v1/documents/edgar \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "form_type": "10-K", "limit": 1}'
```

## Running tests

```bash
psql -U postgres -c "CREATE DATABASE wealth_advisor_test;"
psql -U postgres -d wealth_advisor_test -c "CREATE EXTENSION IF NOT EXISTS vector;"

cd backend
python -m pytest tests/ -v
```

## Azure OpenAI

Uncomment in `.env` to switch from OpenAI direct to Azure — no code changes needed:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-azure-key
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

## Project layout

```
backend/
  app/
    routers/     auth, chat, documents, admin
    graphs/      LangGraph nodes and workflow
    rag/         parser, chunker, embedder, retriever, reranker
    db/          SQLAlchemy models
    auth/        JWT + RBAC
    security/    field-level encryption (Fernet)
  tests/         26 pytest tests (PostgreSQL)

frontend/
  src/
    components/  Chat, Documents, Admin, Login, Register
    context/     AuthContext, axios interceptors
```

## Why security and data governance matter here

Wealth advisors handle material non-public information, client portfolios, and regulatory filings. An AI assistant in this context has to meet a higher bar than a general-purpose chatbot.

**Grounded responses only.** The LLM is never asked to answer from memory. Every response is generated strictly from retrieved document chunks. If the retrieval pipeline doesn't find sufficient evidence, the system refuses to answer rather than hallucinate. This is enforced at the Evidence Check node — not as a prompt suggestion, but as a hard gate in the workflow.

**Data governance by design.** Documents are tagged with sensitivity levels. The Policy Check node enforces role-based access before retrieval even runs — an advisor role cannot retrieve compliance-restricted documents regardless of how the question is phrased. Every query and response is written to an audit log, giving compliance teams a complete record of what was asked, what was retrieved, and what was said.

**Multi-tenant isolation.** Each organization's documents, users, and conversations are scoped to a tenant. There is no cross-tenant data access — enforced at the database query level, not the application layer.

**Prompt injection protection.** User input is validated against known injection patterns before it reaches the LLM. This prevents adversarial inputs from hijacking the system prompt or extracting document content outside the intended workflow.

**Encryption at rest.** Audit log entries (which contain user queries and model responses) can be encrypted at the field level using Fernet symmetric encryption, so sensitive conversation content is protected even if the database is compromised.
