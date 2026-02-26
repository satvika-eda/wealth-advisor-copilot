# Wealth Advisor Copilot

Enterprise-grade RAG (Retrieval Augmented Generation) system for wealth advisors with multi-tenant security, audit logging, and compliance guardrails.

## Features

- 🔍 **Intelligent RAG Pipeline** - Vector search with pgvector + Cohere reranking
- 📄 **Multi-format Ingestion** - PDF, HTML, text, and SEC EDGAR filings
- 🏢 **Multi-tenant Security** - Complete tenant and client isolation
- 📊 **Audit Logging** - Every query, retrieval, and response tracked
- 🛡️ **Compliance Guardrails** - No financial advice, PII redaction
- 📈 **Evaluation Harness** - Built-in quality metrics and testing
- 💬 **LangGraph Workflows** - Structured multi-step processing

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI API key
- (Optional) Cohere API key for reranking

### 1. Clone and Configure

```bash
cd wealth-advisor-copilot

# Copy environment template
cp .env.example .env

# Edit .env and add your OpenAI API key
```

### 2. Start Services

```bash
# Start all services (database, backend, frontend)
docker compose up -d

# For development with hot reload:
docker compose --profile dev up -d
```

### 3. Access the Application

- **Frontend**: http://localhost:5173 (dev) or http://localhost:3000 (production)
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### 4. Create an Account

1. Open the frontend
2. Click "Register"
3. Create an account with your organization name

### 5. Ingest Documents

Via the UI:
- Upload PDFs or text files
- Import SEC EDGAR filings by CIK number

Via API:
```bash
# Upload a document
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf"

# Import EDGAR filing (Apple 10-K)
curl -X POST "http://localhost:8000/api/v1/documents/edgar" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cik": "320193", "filing_type": "10-K"}'
```

## Project Structure

```
wealth-advisor-copilot/
├── backend/
│   ├── app/
│   │   ├── routers/         # FastAPI endpoints
│   │   ├── rag/             # RAG pipeline
│   │   ├── graphs/          # LangGraph workflows
│   │   ├── db/              # Database models
│   │   └── eval/            # Evaluation harness
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/components/      # React components
│   ├── package.json
│   └── Dockerfile
├── docs/
│   ├── ARCHITECTURE.md      # System design
│   └── THREAT_MODEL.md      # Security analysis
├── docker-compose.yml
└── .env.example
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.11) |
| Orchestration | LangGraph |
| LLM | OpenAI GPT-4o |
| Embeddings | OpenAI text-embedding-3-small |
| Vector Store | PostgreSQL + pgvector |
| Reranking | Cohere Rerank v3 |
| Frontend | React + TailwindCSS |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and data flow
- [Threat Model](docs/THREAT_MODEL.md) - Security analysis

## License

MIT