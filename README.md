# AI-Powered Network Runbook Platform

## Quick Start

```bash
make env       # creates .env from template
make install   # install Python deps
make dev       # start infra (Docker) + API (hot reload)
make migrate   # run DB migrations (first time)
open http://localhost:8000/docs
```

## Services
| Service  | URL                       |
|----------|---------------------------|
| API Docs | http://localhost:8000/docs|
| Flower   | http://localhost:5555     |
| ChromaDB | http://localhost:8001     |

## Commands
```bash
make up      # start all docker services
make down    # stop all
make logs    # tail logs
make test    # run tests with coverage
make lint    # ruff linter
```
