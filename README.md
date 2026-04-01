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

## Security and data governance

Wealth advisors work with sensitive regulatory filings and client data — this shapes several design decisions:

- **Grounded responses** — the LLM only sees retrieved document chunks. If evidence is insufficient, the system refuses rather than guesses. Enforced as a hard gate in the workflow, not a prompt instruction.
- **Policy check before retrieval** — role-based access (advisor / compliance / admin) is enforced before any document is retrieved. Sensitive documents can't be reached by lower-privileged roles regardless of how a question is phrased.
- **Audit log** — every query and response is persisted, giving compliance teams a full record of what was asked and answered.
- **Multi-tenant isolation** — data is scoped per organization at the database query level.
- **Prompt injection blocking** — user input is validated against injection patterns before reaching the LLM.
- **Field-level encryption** — audit log entries can be encrypted at rest with Fernet.
