# Local Development Startup Guide

## Prerequisites
- Docker Desktop running
- Ollama installed (`brew install ollama`)
- Python venv created (`python3 -m venv .venv`)
- Dependencies installed (`pip install -r requirements.txt`)

---

## Terminal 1 — Infrastructure + API

```bash
cd ai-network-runbook-platform
source .venv/bin/activate
make dev
```

This starts Postgres, Redis, ChromaDB (Docker) and the FastAPI server on port 8000.

Verify:
```bash
curl http://localhost:8000/health
```

---

## Terminal 2 — Celery Worker

```bash
cd ai-network-runbook-platform
source .venv/bin/activate
make worker
```

Required for runbook ingestion (upload → parse → embed → index).

---

## Terminal 3 — Ollama LLM

```bash
ollama serve
```

Required for RAG query answers. llama3.2 loads automatically on first query.

Verify:
```bash
curl http://localhost:11434/api/tags
```

---

## Terminal 4 — Get Auth Token

```bash
cd ai-network-runbook-platform

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"engineer@test.com","password":"test1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo $TOKEN
```

---

## Quick Test

```bash
# Health check
curl http://localhost:8000/health

# List runbooks
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runbooks/

# RAG query
curl -X POST http://localhost:8000/api/v1/runbooks/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "BGP session stuck in Active state, what should I check?", "top_k": 3}'
```

---

## Upload a Runbook

```bash
curl -X POST http://localhost:8000/api/v1/runbooks/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@runbooks/bgp_troubleshooting.md" \
  -F "description=BGP troubleshooting guide for Cisco IOS-XE and Juniper JunOS" \
  -F "tags=bgp,cisco,juniper,routing"
```

---

## Service URLs

| Service     | URL                          |
|-------------|------------------------------|
| API         | http://localhost:8000        |
| Swagger UI  | http://localhost:8000/docs   |
| Prometheus  | http://localhost:8000/metrics|
| Flower      | http://localhost:5555        |
| ChromaDB    | http://localhost:8001        |
| Ollama      | http://localhost:11434       |

---

## Stop Everything

```bash
# Stop Docker containers
make down

# Stop API, worker, Ollama: Ctrl+C in each terminal
```

---

## Switching Embedding Model or LLM

### Embedding Models
| Use Case | Provider | Model | Speed |
|----------|----------|-------|-------|
| Development | sentence_transformers | all-MiniLM-L6-v2 | Slow (~6s/batch) |
| Demo / Production | openai | text-embedding-3-small | Fast (~1s/batch) |

### LLM Options
| Use Case | Provider | Model | Speed |
|----------|----------|-------|-------|
| Local / Offline | ollama | llama3.2 | Slow (60-90s first query) |
| Fast / Demo | anthropic | claude-haiku-4-5-20251001 | Fast (2-5s) |
| Best Quality | openai | gpt-4o | Medium (5-10s) |

### How to Switch

1. Update `.env` with new provider/model
2. Restart API (`make dev`) and worker (`make worker`)
3. **Re-embed all runbooks** — vectors are model-specific and must be regenerated:

```bash
# Get all runbook IDs
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runbooks/

# Re-embed each runbook (replace {id} with actual runbook ID)
curl -X POST http://localhost:8000/api/v1/runbooks/{id}/reembed \
  -H "Authorization: Bearer $TOKEN"
```

The original `.md`/`.pdf` files stay on disk — only the ChromaDB vectors are replaced.
No re-upload needed.

---

## Notes
- Uploaded runbooks and ChromaDB vectors persist in Docker volumes across restarts.
- Token expires after 60 minutes — re-run the TOKEN command to refresh.
- On first RAG query, llama3.2 takes 60-90s to load. Subsequent queries are faster.
- If worker crashes on macOS, make worker uses --pool=solo to avoid fork() issues.
- Must re-embed all runbooks when switching embedding models (vectors are model-specific).
