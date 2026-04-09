# AI-Powered Network Runbook Platform

> **Capstone Project — MSAI 699, University of the Cumberlands**
>
> An enterprise-grade AI-powered Network Digital Twin and Autonomous Runbook Assistant for incident diagnosis using Retrieval-Augmented Generation (RAG) and multi-agent LLM orchestration.

---

## Overview

NOC engineers waste 30–90 minutes per incident searching fragmented documentation during outages. This platform cuts that to **under 30 seconds** by:

1. Ingesting network runbooks (PDF/Markdown) into a vector store
2. Connecting to live devices (Cisco IOS-XR, Juniper JunOS) via SSH
3. Running a multi-agent AI pipeline to correlate CLI evidence with runbook knowledge
4. Producing structured root cause analysis with remediation steps and citations

---

## Architecture

```
Incident Created
      │
      ▼
InvestigationAgent ──► RAG (ChromaDB + fastembed + BM25 hybrid search)
      │                ──► Device CLI (Netmiko SSH → xrd-1)
      │                ──► Topology context (NetworkX graph)
      ▼
AnalysisAgent ──► LLM (Anthropic claude-haiku-4-5-20251001)
      │
      ├─ confidence < 0.6 ──► SecondOpinionAgent (re-query + re-analyze)
      ├─ protocol == bgp  ──► BGPSpecialistAgent
      ├─ vendor == juniper ──► JunosSpecialistAgent
      │
      ▼
ReportAgent ──► Structured JSON: root_cause, steps, commands, citations
      │
      ▼
PostgreSQL (JSONB ai_report) + React UI
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI 0.115, Python 3.12 |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 async + Alembic |
| Vector Store | ChromaDB 1.5.5 |
| Embeddings | fastembed (BAAI/bge-small-en-v1.5) |
| Reranker | ms-marco-MiniLM-L-12-v2 |
| Task Queue | Celery 5.4 + Redis 7 |
| LLM | Anthropic claude-haiku-4-5-20251001 |
| Agent Framework | Custom state-machine (OrchestratorAgent) |
| Device Automation | Netmiko SSH |
| Graph Engine | NetworkX |
| Frontend | React + TypeScript + Vite + Tailwind + shadcn/ui |
| Topology Viz | React Flow |
| Containerization | Docker + docker-compose |
| Testing | pytest, pytest-asyncio, httpx |
| Observability | structlog (JSON), Prometheus, Celery Flower |

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.12
- Node.js 18+
- Anthropic API key (console.anthropic.com)

### 1. Configure environment
```bash
cp .env.example .env
# Edit .env — set APP_SECRET_KEY and ANTHROPIC_API_KEY
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 3. Start infrastructure
```bash
make dev          # starts PostgreSQL, Redis, ChromaDB via Docker + FastAPI on :8000
```

### 4. Run migrations
```bash
make migrate
```

### 5. Start worker (new terminal)
```bash
unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY   # required if behind corporate proxy
make worker
```

### 6. Start frontend (new terminal)
```bash
cd frontend && npm run dev    # http://localhost:5173
```

---

## Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:5173 | React UI |
| API | http://localhost:8000 | FastAPI backend |
| Swagger | http://localhost:8000/docs | Interactive API docs |
| Flower | http://localhost:5555 | Celery task monitor |
| ChromaDB | http://localhost:8001 | Vector store |

---

## Demo Workflow

### Incident Diagnosis
1. Create incident: title "BGP neighbor down on xrd-1", device: xrd-1, protocol: BGP
2. Click **Run Diagnosis**
3. In ~30 seconds: root cause, hypothesis, remediation steps, runbook citations

### Runbook RAG Chat
1. Go to **Runbooks** page
2. Upload a BGP/OSPF troubleshooting PDF
3. Ask: *"BGP session stuck in Active state — what are the causes?"*
4. Get cited answer from your runbooks

### Topology Visualization
1. Go to **Topology** page
2. View 5-node multi-vendor lab (Cisco + Juniper)
3. Select a failure scenario and click **Simulate**
4. See affected nodes highlighted and impact analysis

---

## Make Commands

```bash
make dev              # Start Docker infra + FastAPI hot-reload
make up               # Start all services via Docker
make down             # Stop all containers
make worker           # Start Celery worker locally
make migrate          # Run Alembic migrations
make migration msg="add xyz"  # Create new migration
make test             # Run pytest with coverage
make lint             # ruff linter
make format           # ruff formatter
make status           # Show running service status
make restart-worker   # Restart Celery worker
make debug-db         # Show/clear DB locks
make debug-incidents  # Show recent incidents
make debug-queue      # Show Redis queue depth
```

---

## Environment Variables

```bash
# Required
APP_SECRET_KEY=<32+ char random string>
DATABASE_URL=postgresql+asyncpg://runbook:runbook@localhost:5432/runbook_db
ANTHROPIC_API_KEY=sk-ant-...

# LLM
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001

# Embeddings
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

# Infrastructure (Docker defaults)
REDIS_URL=redis://localhost:6379/0
CHROMA_HOST=localhost
CHROMA_PORT=8001
```

---

## Multi-Agent Pipeline

The `OrchestratorAgent` dynamically routes through specialist agents based on confidence and incident context:

```
MAX_ITERATIONS = 3

confidence < 0.6  → SecondOpinionAgent (re-investigates with refined queries)
protocol == bgp   → BGPSpecialistAgent (BGP-specific prompt + runbook focus)
vendor == juniper → JunosSpecialistAgent (JunOS CLI interpretation)
always            → ReportAgent (structured output with citations)
```

Each agent logs `inc_ref=INC-XXXX` for full traceability across the pipeline.

---

## Test Suite

```bash
make test
# or
pytest tests/ -v
```

Coverage: auth, incidents CRUD, diagnosis trigger, RAG pipeline (chunking, BM25, RRF, reranking), multi-agent routing (investigation, analysis, orchestration, second opinion).

---

## Performance Benchmark

See [BENCHMARK.md](BENCHMARK.md) for detailed Ollama vs Anthropic comparison.

**Summary:** Anthropic claude-haiku is **180× faster** with accurate root cause vs "Root cause undetermined" from llama3.2.
