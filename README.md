# Wealth Advisor Copilot

A chat assistant that helps wealth advisors quickly find information in SEC filings and financial documents. Upload a 10-K, ask a question, get an answer with citations.

## What It Does

**The problem:** Wealth advisors spend hours digging through lengthy SEC filings and financial documents to answer client questions.

**The solution:** Upload documents (or pull them directly from SEC EDGAR), then ask questions in plain English. The system finds the relevant sections and gives you a sourced answer.

### Key Features

- **Import SEC filings** — Pull 10-Ks, 10-Qs, and other filings directly from EDGAR by ticker or CIK
- **Upload your own docs** — PDFs, text files, HTML
- **Ask questions naturally** — "What are Apple's main risk factors?" or "How much cash does the company have?"
- **Get cited answers** — Every response includes references to the source documents
- **Multi-tenant** — Each organization's data stays separate

## Getting Started

You'll need:
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- An OpenAI API key ([get one here](https://platform.openai.com/api-keys))
- (Optional) A Cohere API key for better search ranking

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/your-org/wealth-advisor-copilot.git
cd wealth-advisor-copilot

# 2. Create your environment file
cp .env.example .env

# 3. Add your OpenAI key to .env
# Open .env in any editor and set OPENAI_API_KEY=sk-...

# 4. Start everything
docker compose up -d
```

That's it! Give it a minute to start up, then open:
- **App:** http://localhost:3000
- **API Docs:** http://localhost:8000/docs

### Try It Out

1. Open the app and go to the **Documents** tab
2. Import a filing — try Apple's 10-K (CIK: `320193`)
3. Switch to **Chat** and ask: *"What are the main risk factors?"*
4. You'll get an answer with citations pointing to the exact sections

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Upload    │ ──▶ │   Chunk &   │ ──▶ │   Store in  │
│  Document   │     │   Embed     │     │   Postgres  │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
┌─────────────┐     ┌─────────────┐           ▼
│   Return    │ ◀── │  Generate   │ ◀── ┌─────────────┐
│   Answer    │     │   Answer    │     │   Search    │
└─────────────┘     └─────────────┘     │   + Rank    │
                                        └─────────────┘
```

1. **Documents are chunked** into smaller pieces and converted to embeddings
2. **Questions trigger a search** across all your documents using vector similarity
3. **Top results are re-ranked** (with Cohere) for relevance
4. **GPT-4o generates an answer** using only the retrieved context

## Project Layout

```
backend/
  app/
    routers/     → API endpoints (chat, documents, admin)
    rag/         → Document processing & retrieval
    graphs/      → LangGraph workflow for Q&A
    db/          → Database models (Postgres + pgvector)

frontend/
  src/
    components/  → React UI (Chat, Documents, Admin tabs)
```

## Tech Stack

- **Backend:** FastAPI + LangGraph
- **LLM:** OpenAI GPT-4o
- **Embeddings:** OpenAI text-embedding-3-small
- **Vector DB:** PostgreSQL with pgvector (HNSW index)
- **Reranking:** Cohere Rerank v3
- **Frontend:** React + Vite + TailwindCSS

## Learn More

- [Architecture](docs/ARCHITECTURE.md) — How the system is designed
- [Threat Model](docs/THREAT_MODEL.md) — Security considerations

## License

MIT