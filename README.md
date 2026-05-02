# AI-Powered Network Runbook Platform

> **Capstone Project — MSAI 699, University of the Cumberlands**
>
> An enterprise-grade AI-powered Network Digital Twin and Autonomous Runbook Assistant for incident diagnosis using Retrieval-Augmented Generation (RAG) and multi-agent LLM orchestration.

---

## Overview

NOC engineers waste 30–90 minutes per incident searching fragmented documentation during outages. This platform cuts that to **under 30 seconds** by:

1. Ingesting network runbooks (PDF/Markdown) into a vector store
2. Connecting to live devices (Cisco IOS-XR, Juniper JunOS, Arista EOS, Cisco NX-OS) via SSH or vendor APIs
3. Running a multi-agent AI pipeline to correlate CLI evidence with runbook knowledge
4. Producing structured root cause analysis with remediation steps and citations
5. Proactively detecting anomalies and predicting incidents before impact occurs

---

## Architecture

```
Incident Created
      │
      ▼
InvestigationAgent ──► RAG (ChromaDB + fastembed + BM25 hybrid search + feedback reranking)
      │                ──► Device CLI (Netmiko SSH / eAPI / NX-API)
      │                ──► Topology context (NetworkX graph)
      │                ──► Incident Correlator (cosine similarity → parent linkage)
      ▼
AnalysisAgent ──► LLM (Anthropic / OpenAI / Ollama / vLLM)
      │
      ├─ confidence < 0.6 ──► SecondOpinionAgent (re-query + re-analyze)
      ├─ protocol == bgp  ──► BGPSpecialistAgent
      ├─ vendor == juniper ──► JunosSpecialistAgent
      │
      ▼
ReportAgent ──► Structured JSON: root_cause, steps, commands, citations
      │
      ├─► PostgreSQL (JSONB ai_report) + React UI
      ├─► ServiceNow (bidirectional sync)
      ├─► Slack (Block Kit alerts + approval buttons)
      ├─► Microsoft Teams (Adaptive Cards)
      └─► Auto-Runbook Generator (LLM drafts runbook from resolved incident)

Celery Beat ──► Anomaly Detector (z-score on device metrics → PREDICTED incidents)
             ──► NetBox Sync (device inventory import)
             ──► Monitoring (parallel device health polling)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI 0.115, Python 3.12+ |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 async + Alembic |
| Vector Store | ChromaDB |
| Embeddings | fastembed (BAAI/bge-small-en-v1.5) |
| Reranker | ms-marco-MiniLM-L-12-v2 + feedback-based score adjustment |
| Task Queue | Celery 5.4 + Redis 7 |
| LLM (agnostic) | Anthropic Claude / OpenAI GPT-4o / Ollama / vLLM (on-prem) |
| Agent Framework | Custom OrchestratorAgent state machine |
| Device Automation | Netmiko SSH + Arista eAPI + Cisco NX-API |
| Graph Engine | NetworkX |
| Secret Management | HashiCorp Vault (optional) + Fernet fallback |
| Frontend | React + TypeScript + Vite + Tailwind + shadcn/ui |
| Topology Viz | React Flow |
| Containerization | Docker + docker-compose + Helm (Kubernetes) |
| Observability | structlog JSON + Prometheus + Celery Flower + OpenTelemetry |
| Testing | pytest, pytest-asyncio, httpx |

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.12+
- Node.js 18+
- Anthropic API key (or OpenAI / local Ollama)

### 1. Configure environment
```bash
cp .env.example .env
# Edit .env — set APP_SECRET_KEY and ANTHROPIC_API_KEY at minimum
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

## API Reference

### Authentication
```
POST   /api/v1/auth/register          Create user account
POST   /api/v1/auth/login             Login → access + refresh tokens
POST   /api/v1/auth/refresh           Refresh access token
GET    /api/v1/auth/me                Get current user profile
GET    /api/v1/auth/oidc/login        SSO redirect (OIDC_ENABLED=true)
GET    /api/v1/auth/oidc/callback     SSO callback (OIDC_ENABLED=true)
```

### Incidents
```
GET    /api/v1/incidents/             List incidents
POST   /api/v1/incidents/             Create incident
GET    /api/v1/incidents/{id}         Get incident detail
PATCH  /api/v1/incidents/{id}         Update incident
DELETE /api/v1/incidents/{id}         Delete incident
POST   /api/v1/incidents/{id}/diagnose          Trigger AI diagnosis
POST   /api/v1/incidents/{id}/feedback          Submit helpful/not_helpful rating (FEEDBACK_ENABLED)
GET    /api/v1/incidents/{id}/feedback          List feedback for incident (FEEDBACK_ENABLED)
```

### Runbooks
```
POST   /api/v1/runbooks/upload        Upload PDF/Markdown runbook
GET    /api/v1/runbooks/              List ingested runbooks
GET    /api/v1/runbooks/{id}          Get runbook detail
PATCH  /api/v1/runbooks/{id}          Update runbook metadata
DELETE /api/v1/runbooks/{id}          Delete runbook + embeddings
POST   /api/v1/runbooks/{id}/reembed  Re-generate embeddings
POST   /api/v1/runbooks/{id}/approve  Approve auto-generated draft (RUNBOOK_AUTOGEN_ENABLED)
POST   /api/v1/runbooks/query         RAG query with citations
```

### Devices
```
GET    /api/v1/devices/               List devices
POST   /api/v1/devices/               Register device
GET    /api/v1/devices/{id}           Get device
PATCH  /api/v1/devices/{id}           Update device
DELETE /api/v1/devices/{id}           Delete device
POST   /api/v1/devices/{id}/run-command         Execute CLI command
POST   /api/v1/devices/{id}/credentials/rotate  Rotate credentials (VAULT_ENABLED)
```

### Topology & Simulation
```
GET    /api/v1/topology/              Get current topology graph
POST   /api/v1/topology/upload        Upload YAML topology
POST   /api/v1/topology/simulate      Inject failure scenario
GET    /api/v1/topology/{device}/neighbors
POST   /api/v1/simulation/run-command Execute/simulate CLI command
```

### Remediation
```
GET    /api/v1/incidents/{id}/remediation        Get remediation plan
POST   /api/v1/incidents/{id}/remediation        Generate remediation plan
POST   /api/v1/incidents/{id}/remediation/approve    Approve steps (with approver audit trail)
POST   /api/v1/incidents/{id}/remediation/execute    Execute approved steps
POST   /api/v1/incidents/{id}/remediation/rollback   Rollback plan (ADMIN only)
```

### Enterprise (conditionally registered)
```
GET    /api/v1/sites/                 List sites (MULTITENANCY_ENABLED)
POST   /api/v1/sites/                 Create site (MULTITENANCY_ENABLED, ADMIN)
GET    /api/v1/sites/{id}             Get site (MULTITENANCY_ENABLED)
PATCH  /api/v1/sites/{id}             Update site (MULTITENANCY_ENABLED, ADMIN)
DELETE /api/v1/sites/{id}             Delete site (MULTITENANCY_ENABLED, ADMIN)
POST   /api/v1/webhooks/servicenow    Inbound ServiceNow webhook (SNOW_ENABLED)
POST   /api/v1/webhooks/slack         Slack interactive button handler (SLACK_ENABLED)
```

### Observability
```
GET    /health                        Health check
GET    /readiness                     Readiness probe
GET    /metrics                       Prometheus metrics
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

## Enterprise Features

All enterprise features are **off by default** and fully backward compatible. Enable via `.env`.

### Phase 1 — Security & Operations

| Feature | Flag | Description |
|---------|------|-------------|
| HashiCorp Vault | `VAULT_ENABLED=true` | Device credentials from Vault KV v2; AppRole or token auth; Fernet fallback when disabled |
| ServiceNow | `SNOW_ENABLED=true` | Bidirectional incident sync; HMAC-signed inbound webhooks; auto status mapping |
| SSO / OIDC | `OIDC_ENABLED=true` | OAuth2 authorization code flow via authlib; group → role mapping; local JWT unchanged |
| Kubernetes | — | Full Helm chart in `helm/`; HPA, ExternalSecret, separate API/Celery/Flower deployments |

### Phase 2 — Integrations & Scale

| Feature | Flag | Description |
|---------|------|-------------|
| NetBox Sync | `NETBOX_ENABLED=true` | Periodic Celery beat task imports devices from NetBox DCIM; never deletes existing |
| Slack | `SLACK_ENABLED=true` | Block Kit incident alerts; interactive approve/reject buttons for remediation; HMAC validation |
| Microsoft Teams | `TEAMS_ENABLED=true` | Adaptive Card alerts for incidents, diagnoses, and remediation updates |
| OpenTelemetry | `OTEL_ENABLED=true` | Distributed tracing across FastAPI + SQLAlchemy + httpx + Celery; OTLP export |
| Arista EOS | automatic | eAPI (HTTPS JSON-RPC) driver; SSH fallback; auto-detected from device OS |
| Cisco NX-OS | automatic | NX-API (HTTP JSON) driver; SSH fallback; auto-detected from device OS |
| Multi-tenancy | `MULTITENANCY_ENABLED=true` | Site isolation for devices, incidents, and users; `apply_site_filter()` on all queries |

### Phase 3 — Intelligence

| Feature | Flag | Description |
|---------|------|-------------|
| vLLM | `LLM_PROVIDER=vllm` | On-prem OpenAI-compatible endpoint; reuses openai SDK; set `VLLM_BASE_URL` |
| Feedback Loop | `FEEDBACK_ENABLED=true` | Helpful/not_helpful ratings on diagnoses; cited chunk IDs adjust future RAG reranking scores (±0.05/rating, capped ±0.20) |
| Incident Correlation | `CORRELATION_ENABLED=true` | Embedding cosine similarity + device/protocol bonuses links related incidents; `parent_incident_id` + `correlation_score` in every response |
| Auto-Runbook Gen | `RUNBOOK_AUTOGEN_ENABLED=true` | LLM drafts Markdown runbook when incident resolves; operator review via `/approve`; then auto-indexed into ChromaDB |
| Predictive Anomaly | `PREDICTIVE_ENABLED=true` | Z-score detection (±3σ, 50-sample window) on device metrics; auto-creates `PREDICTED` incidents before impact |

---

## Demo Workflow

### Incident Diagnosis
1. Create incident: title "BGP neighbor down on R1-CORE", device: R1-CORE, protocol: BGP
2. Click **Run Diagnosis**
3. In ~15–30 seconds: root cause, hypothesis, remediation steps, runbook citations

### Runbook RAG Query
1. Go to **Runbooks** page → upload a BGP/OSPF troubleshooting PDF
2. Ask: *"BGP session stuck in Active state — what are the causes?"*
3. Get a cited answer from your runbooks with source and page references

### Topology Visualization
1. Go to **Topology** page
2. View 5-node multi-vendor lab (Cisco IOS-XE + Juniper vMX)
3. Select a failure scenario and click **Simulate**
4. See affected nodes highlighted with impact radius

### Auto-Runbook Generation (RUNBOOK_AUTOGEN_ENABLED=true)
1. Resolve an incident (`PATCH /incidents/{id}` with `status: resolved`)
2. Celery auto-generates a Markdown runbook draft (`status: pending_review`)
3. Review the draft at `GET /runbooks/` — filter by `auto_generated: true`
4. Approve via `POST /runbooks/{id}/approve` → indexed into ChromaDB

### Incident Correlation (CORRELATION_ENABLED=true)
1. Create two incidents with similar descriptions or same affected device
2. The second incident automatically gets `parent_incident_id` set
3. `correlation_score` (0.0–1.0) shows similarity strength

---

## Environment Variables

### Required
```bash
APP_SECRET_KEY=<32+ char random string>
CREDENTIAL_ENCRYPTION_KEY=<32+ char random string>
DATABASE_URL=postgresql+asyncpg://runbook:runbook@localhost:5432/runbook_db
```

### LLM — pick one
```bash
# Anthropic (recommended — fastest)
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...

# Ollama (local)
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2

# vLLM on-prem (Phase 3)
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://your-vllm-host:8080/v1
VLLM_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
```

### Embeddings
```bash
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RERANKER_ENABLED=true
```

### Infrastructure (Docker defaults)
```bash
REDIS_URL=redis://localhost:6379/0
CHROMA_HOST=localhost
CHROMA_PORT=8001
```

### Enterprise flags (all default false)
```bash
# Phase 1
VAULT_ENABLED=false
SNOW_ENABLED=false
OIDC_ENABLED=false

# Phase 2
NETBOX_ENABLED=false
SLACK_ENABLED=false
TEAMS_ENABLED=false
OTEL_ENABLED=false
MULTITENANCY_ENABLED=false

# Phase 3
FEEDBACK_ENABLED=false
CORRELATION_ENABLED=false
RUNBOOK_AUTOGEN_ENABLED=false
PREDICTIVE_ENABLED=false
```

---

## Make Commands

```bash
make dev              # Start Docker infra + FastAPI hot-reload
make up               # Start all services via Docker
make down             # Stop all containers
make worker           # Start Celery worker locally
make migrate          # Run Alembic migrations (alembic upgrade head)
make migration msg="add xyz"  # Create new migration file
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

## RBAC — Role Hierarchy

```
ADMIN > ENGINEER > VIEWER
```

| Action | Minimum Role |
|--------|-------------|
| View incidents, runbooks, devices | VIEWER |
| Create incident, upload runbook | ENGINEER |
| Trigger diagnosis, approve remediation | ENGINEER |
| Delete resources, manage users | ADMIN |
| Create/update sites (multi-tenancy) | ADMIN |
| Rollback remediation plans | ADMIN |
| Approve auto-generated runbooks | ADMIN |

---

## Incident Status Lifecycle

```
OPEN → DIAGNOSING → AWAITING_INPUT → RESOLVED → CLOSED
                                         │
PREDICTED (auto-created by anomaly detector)
```

`PREDICTED` incidents are created proactively by the anomaly detector when device metrics exceed ±3σ from the rolling mean. They can be promoted to `OPEN` and diagnosed normally.

---

## Database Schema

Key tables and their purpose:

| Table | Purpose |
|-------|---------|
| `users` | Accounts with RBAC roles; OIDC sub/provider for SSO |
| `incidents` | Core incident records; `ai_report` JSONB; `parent_incident_id` for correlation |
| `runbooks` | File metadata; ChromaDB chunk IDs; `auto_generated` flag |
| `devices` | Device inventory; multi-vendor; `live_enabled` toggle |
| `remediation_plans` | AI-generated steps; approval audit trail (`approved_by_id`, `approved_at`) |
| `topologies` | NetworkX graph snapshots as JSONB |
| `audit_logs` | Every create/update/delete/diagnose action |
| `sites` | Multi-tenant site isolation (MULTITENANCY_ENABLED) |
| `diagnosis_feedback` | Helpful/not_helpful ratings with cited chunk IDs (FEEDBACK_ENABLED) |
| `anomaly_metrics` | Device metric time series; z-score; anomaly flag (PREDICTIVE_ENABLED) |

All tables use UUID primary keys and inherit `created_at`/`updated_at` from `AuditBase`.

---

## Test Suite

```bash
make test
# or
pytest tests/ -v --cov=backend
```

Coverage: auth, incidents CRUD, diagnosis trigger, RAG pipeline (chunking, BM25, RRF, reranking), multi-agent routing (investigation, analysis, orchestration, second opinion), audit logging.

---

## Kubernetes Deployment

A complete Helm chart is provided in `helm/`:

```bash
# Development
helm install runbook ./helm -f helm/values-dev.yaml

# Production
helm install runbook ./helm -f helm/values-prod.yaml \
  --set api.image.tag=v1.0.0 \
  --set secrets.externalSecrets.enabled=true
```

The chart deploys: API, Celery worker, Flower monitor, and configures HPA for both API and Celery.

---

## Performance Benchmark

See [BENCHMARK.md](BENCHMARK.md) for detailed Ollama vs Anthropic comparison.

**Summary:** Anthropic claude-haiku is **180× faster** with accurate root cause vs "Root cause undetermined" from llama3.2.
