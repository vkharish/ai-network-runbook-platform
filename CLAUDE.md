# AI-Powered Network Runbook Platform — Claude Code Context

## Project Overview
Building an **enterprise-grade AI-powered Network Digital Twin and Autonomous Runbook Assistant** for incident diagnosis using Retrieval-Augmented Generation (RAG).

**Capstone project** for MSAI 699 at University of the Cumberlands.

---

## Core Concept
NOC engineers waste time searching fragmented docs during outages. This system:
1. Ingests network runbooks (PDF/Markdown) into a vector store
2. Uses RAG to retrieve relevant troubleshooting knowledge
3. Combines with a network digital twin (graph model of topology)
4. Uses LLMs to generate structured root cause analysis and troubleshooting steps
5. Supports multi-vendor environments (Cisco IOS-XE + Juniper JunOS)

---

## 5-Week Implementation Plan

| Week | Focus | Status |
|------|-------|--------|
| 1 | Foundation: auth, DB models, schemas, API scaffold, Docker | ✅ COMPLETE |
| 2 | RAG Pipeline: document ingestion, embeddings, ChromaDB, query API | 🔲 TODO |
| 3 | LLM + Multi-Agent: InvestigationAgent, AnalysisAgent, ReportAgent | 🔲 TODO |
| 4 | Digital Twin: topology graph, CLI simulation, failure injection | 🔲 TODO |
| 5 | Enterprise hardening: RBAC, observability, testing, docs | 🔲 TODO |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI 0.115, Python 3.11+ |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 async + Alembic |
| Vector Store | ChromaDB 0.5.12 |
| Task Queue | Celery 5.4 + Redis 7 |
| LLM (agnostic) | OpenAI GPT-4o / Anthropic Claude / Ollama (llama3) |
| Embeddings | OpenAI text-embedding-3-small / sentence-transformers |
| Agent Framework | LangGraph or custom state machine |
| Graph Engine | NetworkX |
| Device Automation | Netmiko |
| Frontend | React + TypeScript + Vite + Tailwind + shadcn/ui |
| Topology Viz | React Flow |
| Containerization | Docker + docker-compose |
| Testing | pytest, pytest-asyncio, httpx |
| Observability | structlog (JSON), Prometheus, Celery Flower |

---

## Project Root
```
ai-network-runbook-platform/
```

---

## Complete Folder Structure

```
ai-network-runbook-platform/
│
├── backend/
│   ├── __init__.py
│   ├── main.py                        ✅ FastAPI app factory, lifespan, middleware
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── dependencies.py            ✅ get_current_user, require_role()
│   │   └── api/
│   │       ├── __init__.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           ├── auth_routes.py     ✅ register, login, refresh, /me
│   │           ├── incident_routes.py ✅ CRUD + /diagnose trigger
│   │           ├── runbook_routes.py  🔲 Week 2
│   │           ├── topology_routes.py 🔲 Week 4
│   │           └── simulation_routes.py 🔲 Week 4
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  ✅ Pydantic-settings, LLM-agnostic enums
│   │   ├── security.py                ✅ JWT, bcrypt, Role enum, role_gte()
│   │   └── logging.py                 ✅ structlog JSON, correlation IDs
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user_model.py              ✅ User ORM (email, role, is_active)
│   │   ├── incident_model.py          ✅ Incident ORM (status lifecycle, JSONB ai_report)
│   │   ├── runbook_model.py           ✅ Runbook ORM (file metadata, chunk_count, chroma_ids)
│   │   └── topology_model.py          ✅ Topology ORM (raw_yaml, graph_data JSONB)
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user_schema.py             ✅ UserCreate, UserResponse, TokenResponse, LoginRequest
│   │   ├── incident_schema.py         ✅ IncidentCreate, IncidentUpdate, IncidentResponse
│   │   ├── runbook_schema.py          ✅ RunbookResponse, RunbookQueryRequest/Response
│   │   └── topology_schema.py         ✅ TopologyCreate, TopologyResponse
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── incident_service.py        🔲 Week 3
│   │   ├── runbook_service.py         🔲 Week 2
│   │   ├── topology_service.py        🔲 Week 4
│   │   └── simulation_service.py      🔲 Week 4
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── investigation_agent.py     🔲 Week 3
│   │   ├── analysis_agent.py          🔲 Week 3
│   │   └── report_agent.py            🔲 Week 3
│   │
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── ingest_documents.py        🔲 Week 2
│   │   ├── embedding_engine.py        🔲 Week 2
│   │   ├── vector_store.py            🔲 Week 2
│   │   └── rag_pipeline.py            🔲 Week 2
│   │
│   ├── automation/
│   │   ├── __init__.py
│   │   ├── device_agent.py            🔲 Week 4
│   │   ├── netmiko_client.py          🔲 Week 4
│   │   └── command_executor.py        🔲 Week 4
│   │
│   ├── digital_twin/
│   │   ├── __init__.py
│   │   ├── topology_builder.py        🔲 Week 4
│   │   ├── graph_engine.py            🔲 Week 4
│   │   └── failure_simulator.py       🔲 Week 4
│   │
│   ├── simulation/
│   │   ├── __init__.py
│   │   ├── simulator.py               🔲 Week 4
│   │   └── cli_loader.py              🔲 Week 4
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py                    ✅ AuditBase (id UUID, created_at, updated_at)
│   │   ├── session.py                 ✅ Async engine, get_db() dependency
│   │   └── migrations/
│   │       ├── __init__.py
│   │       └── env.py                 ✅ Alembic async-compatible env
│   │
│   └── tasks/
│       ├── __init__.py
│       ├── celery_worker.py           ✅ Celery app factory
│       ├── document_ingestion.py      🔲 Week 2
│       └── embedding_tasks.py         🔲 Week 2
│
├── frontend/                          🔲 Week 2+ (React + TypeScript + Vite)
│   └── src/
│       ├── components/
│       ├── pages/
│       │   ├── dashboard.tsx
│       │   ├── incidents.tsx
│       │   └── runbook_chat.tsx
│       ├── services/
│       │   └── api_client.ts
│       └── App.tsx
│
├── runbooks/                          📂 Drop PDF/MD runbooks here
│   ├── bgp_troubleshooting.pdf        (to be added)
│   ├── ospf_runbook.pdf               (to be added)
│   └── interface_errors.pdf           (to be added)
│
├── simulator/                         ✅ Simulated CLI outputs
│   ├── r1/
│   │   ├── show_bgp_summary.txt
│   │   ├── show_interface.txt
│   │   └── show_logs.txt
│   └── r2/
│       ├── show_bgp_summary.txt
│       └── show_interface.txt
│
├── topology/
│   └── sample_topology.yaml           ✅ 5-node Cisco+Juniper lab topology
│
├── docker/
│   ├── Dockerfile                     ✅ Multi-stage, non-root user
│   └── docker-compose.yml             ✅ Postgres, Redis, ChromaDB, API, Celery, Flower
│
├── .env.example                       ✅
├── .env                               ✅ (copy of example — fill in keys)
├── alembic.ini                        ✅
├── requirements.txt                   ✅
├── Makefile                           ✅
└── README.md                          ✅
```

---

## Key Design Decisions

### LLM Agnostic Architecture
The system supports OpenAI, Anthropic, and Ollama via `LLMProvider` enum in `config.py`.
When implementing the LLM client in Week 3, create an abstract base class:
```python
# backend/agents/llm_client.py  (to be built Week 3)
class BaseLLMClient(ABC):
    async def complete(self, messages: list[dict], **kwargs) -> str: ...

class OpenAIClient(BaseLLMClient): ...
class AnthropicClient(BaseLLMClient): ...
class OllamaClient(BaseLLMClient): ...

def get_llm_client() -> BaseLLMClient:
    # Factory based on settings.llm_provider
```

### Role-Based Access Control
Three roles with hierarchy: `ADMIN > ENGINEER > VIEWER`
```python
# Usage in routes:
@router.delete("/{id}", dependencies=[Depends(require_role(Role.ADMIN))])
@router.post("/{id}/diagnose", dependencies=[Depends(require_role(Role.ENGINEER))])
@router.get("/", dependencies=[Depends(get_current_user)])  # any authenticated
```

### Incident Status Lifecycle
```
OPEN → DIAGNOSING → AWAITING_INPUT → RESOLVED → CLOSED
```
The `/diagnose` endpoint transitions OPEN → DIAGNOSING and triggers the Celery task (Week 3).

### Database
- All models inherit from `AuditBase` (UUID pk, created_at, updated_at)
- JSONB columns for AI-generated fields: `ai_report`, `diagnosis_steps`, `graph_data`
- Async SQLAlchemy 2.0 throughout — always use `await db.execute(select(...))`

### Correlation IDs
Every HTTP request gets a `X-Correlation-ID` header (generated if not provided).
Set via `set_correlation_id()` in middleware, readable anywhere via `get_correlation_id()`.
All log lines include this automatically via structlog processor.

---

## API Endpoints (Week 1 — Implemented)

```
POST   /api/v1/auth/register        Create user account
POST   /api/v1/auth/login           Login → access + refresh tokens
POST   /api/v1/auth/refresh         Refresh access token
GET    /api/v1/auth/me              Get current user

GET    /api/v1/incidents/           List incidents (auth required)
POST   /api/v1/incidents/           Create incident (auth required)
GET    /api/v1/incidents/{id}       Get incident detail
PATCH  /api/v1/incidents/{id}       Update incident (engineer+)
POST   /api/v1/incidents/{id}/diagnose  Trigger AI diagnosis (engineer+)

GET    /health                      Health check
GET    /readiness                   Readiness check
GET    /metrics                     Prometheus metrics
GET    /docs                        Swagger UI (dev only)
```

---

## API Endpoints (To Be Built)

```
# Week 2 — RAG / Runbooks
POST   /api/v1/runbooks/upload      Upload + ingest PDF/MD document
GET    /api/v1/runbooks/            List ingested runbooks
DELETE /api/v1/runbooks/{id}        Remove runbook + vector embeddings
POST   /api/v1/runbooks/query       RAG query with citations

# Week 4 — Topology / Simulation
GET    /api/v1/topology/            Get current topology graph
POST   /api/v1/topology/upload      Upload YAML topology
POST   /api/v1/topology/simulate    Inject failure scenario
GET    /api/v1/topology/{device}/neighbors
POST   /api/v1/simulation/run-command   Execute/simulate CLI command
```

---

## Environment Variables

```bash
# Required — fill these in .env
APP_SECRET_KEY=<min 32 char random string>
DATABASE_URL=postgresql+asyncpg://runbook:runbook@localhost:5432/runbook_db

# LLM — set ONE provider
LLM_PROVIDER=openai        # openai | anthropic | ollama
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
# OR
ANTHROPIC_API_KEY=sk-ant-...
# OR
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# These have working defaults for local Docker setup
REDIS_URL=redis://localhost:6379/0
CHROMA_HOST=localhost
CHROMA_PORT=8001
```

---

## Docker Services

| Container | Port | Purpose |
|-----------|------|---------|
| runbook_postgres | 5432 | Primary database |
| runbook_redis | 6379 | Celery broker + cache |
| runbook_chroma | 8001 | Vector store for embeddings |
| runbook_api | 8000 | FastAPI application |
| runbook_celery | — | Background task worker |
| runbook_flower | 5555 | Celery task monitor UI |

---

## Sample Topology (topology/sample_topology.yaml)

5-node multi-vendor lab network:
- **R1-CORE** (Cisco CSR1000v) — BGP AS 65001, OSPF Area 0
- **R2-DIST** (Cisco CSR1000v) — BGP AS 65002, OSPF Area 0
- **R3-DIST** (Juniper vMX) — OSPF Area 0
- **R4-ACCESS** (Cisco CSR1000v) — BGP AS 65004
- **R5-ACCESS** (Juniper vMX) — OSPF Area 0

Pre-defined failure scenarios: `bgp_peer_down`, `link_down_r2_r4`, `ospf_neighbor_lost`

---

## Week 2 — What to Build Next (RAG Pipeline)

### Files to create:
```
backend/rag/ingest_documents.py     # PDF/MD → text chunks
backend/rag/embedding_engine.py     # OpenAI or sentence-transformers
backend/rag/vector_store.py         # ChromaDB client wrapper
backend/rag/rag_pipeline.py         # query → embed → search → LLM answer
backend/services/runbook_service.py # business logic
backend/app/api/routes/runbook_routes.py
backend/tasks/document_ingestion.py # Celery async task
backend/tasks/embedding_tasks.py    # Celery embedding task
```

### Key implementation notes for Week 2:
- Use `pypdf` for PDF parsing, `markdown` lib for MD
- Chunk strategy: recursive character splitter, chunk_size=1000, overlap=200
- Store chunks in ChromaDB with metadata: `{source, page, runbook_id, tags}`
- RAG answer must include source citations: `{text, source, score, chunk_id}`
- Celery task: `ingest_runbook.delay(runbook_id, file_path)` → update DB status
- Runbook upload flow: save file → create DB record → kick Celery task → return immediately
- ChromaDB collection name from `settings.chroma_collection_name`

---

## Week 3 — What to Build (Agents)

```
backend/agents/llm_client.py        # Abstract LLM client + provider factory
backend/agents/investigation_agent.py  # Gather context, query RAG, call tools
backend/agents/analysis_agent.py    # Interpret CLI output, hypothesize root cause
backend/agents/report_agent.py      # Generate structured markdown report
backend/services/incident_service.py   # Orchestrate agent pipeline
```

Agent pipeline triggered by `POST /incidents/{id}/diagnose`:
1. `InvestigationAgent` — fetch incident, query RAG for relevant runbook steps
2. `AnalysisAgent` — analyze simulated CLI outputs against runbook guidance
3. `ReportAgent` — produce structured JSON report stored in `incident.ai_report`

---

## Week 4 — What to Build (Digital Twin)

```
backend/digital_twin/topology_builder.py  # Parse YAML → NetworkX graph
backend/digital_twin/graph_engine.py      # Shortest path, neighbor lookup, impact analysis
backend/digital_twin/failure_simulator.py # Inject failures, propagate effects
backend/simulation/cli_loader.py          # Load simulator/*.txt files
backend/simulation/simulator.py           # Map show commands → simulated responses
backend/automation/command_executor.py    # Allow-listed command execution
```

---

## Make Commands

```bash
make dev        # Start Postgres+Redis+ChromaDB via Docker, run API with hot reload
make up         # Start ALL services via Docker
make down       # Stop all containers
make logs       # Tail container logs
make migrate    # Run Alembic: alembic upgrade head
make migration msg="add xyz"  # Create new migration
make worker     # Start Celery worker locally
make test       # pytest with coverage
make lint       # ruff check
make format     # ruff format
```

---

## Running Locally (Quick Start)

```bash
cd ai-network-runbook-platform

# 1. Fill in your .env
nano .env   # Set APP_SECRET_KEY and LLM API key

# 2. Install deps
pip install -r requirements.txt

# 3. Start infrastructure
make dev

# 4. First time: run migrations
make migrate

# 5. Verify
curl http://localhost:8000/health
open http://localhost:8000/docs
```

---

## Important Conventions

1. **Always use async** — all DB calls use `await db.execute(select(...))`, never sync SQLAlchemy
2. **Log with structlog** — `log = get_logger(__name__)` then `log.info("event_name", key=val)`
3. **Schemas separate from models** — never return ORM objects directly from routes, use `response_model=`
4. **Pydantic v2** — use `model_dump()` not `.dict()`, `model_config = ConfigDict(from_attributes=True)`
5. **UUIDs everywhere** — all primary keys are UUID4, not integers
6. **JSONB for AI data** — `ai_report`, `diagnosis_steps`, `graph_data` stored as PostgreSQL JSONB
7. **Role checks via dependency** — `Depends(require_role(Role.ENGINEER))` not inline checks
8. **Celery for long tasks** — document ingestion and AI diagnosis run as Celery tasks, not inline
9. **Settings singleton** — always import `from backend.core.config import settings`, never re-instantiate
10. **Correlation ID** — set in middleware, included in every log line automatically