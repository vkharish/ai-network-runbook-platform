.PHONY: help dev up down logs migrate migration worker test lint format install env \
        status start-api stop-api restart-api start-worker stop-worker restart-worker \
        start-frontend stop-frontend debug-db debug-incidents reset-incident

# ── Help ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "AI Runbook Platform — Make targets"
	@echo ""
	@echo "  DEVELOPMENT"
	@echo "  dev              Start infra (postgres/redis/chromadb) + API with hot reload"
	@echo "  worker           Start Celery worker in foreground (with logs)"
	@echo "  up               Start ALL services via Docker"
	@echo "  down             Stop all Docker containers"
	@echo ""
	@echo "  MODULE CONTROL (background, logs go to /tmp/runbook_*.log)"
	@echo "  start-api        Start API in background"
	@echo "  stop-api         Stop API"
	@echo "  restart-api      Restart API"
	@echo "  start-worker     Start Celery worker in background"
	@echo "  stop-worker      Stop Celery worker"
	@echo "  restart-worker   Restart Celery worker"
	@echo "  start-frontend   Start Vite dev server in background"
	@echo "  stop-frontend    Stop Vite dev server"
	@echo ""
	@echo "  STATUS & DEBUG"
	@echo "  status           Show status of all modules"
	@echo "  debug-db         Show DB connections and clear any locks"
	@echo "  debug-incidents  Show all incidents with status"
	@echo "  debug-queue      Show Celery Redis queue depth"
	@echo "  reset-incident n=<num>  Reset stuck incident to 'open' (e.g. make reset-incident n=7)"
	@echo ""
	@echo "  LOGS (use Ctrl+C to stop)"
	@echo "  logs-api         Tail API logs"
	@echo "  logs-worker      Tail worker logs"
	@echo "  logs-frontend    Tail frontend logs"
	@echo "  logs             Tail all Docker container logs"
	@echo ""
	@echo "  DATABASE"
	@echo "  migrate          Run pending Alembic migrations"
	@echo "  migration msg=   Create new Alembic migration"
	@echo ""
	@echo "  QUALITY"
	@echo "  test             Run pytest with coverage"
	@echo "  lint             Run ruff linter"
	@echo "  format           Run ruff formatter"

# ── Infrastructure ─────────────────────────────────────────────────────────
up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

logs:
	docker compose -f docker/docker-compose.yml logs -f

# ── Dev (foreground — shows logs directly in terminal) ─────────────────────
dev:
	docker compose -f docker/docker-compose.yml up -d postgres redis chromadb
	uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

worker:
	unset http_proxy HTTP_PROXY https_proxy HTTPS_PROXY; \
	OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES celery -A backend.tasks.celery_worker worker --loglevel=info --pool=solo

# ── Module control (background) ────────────────────────────────────────────
start-api:
	./scripts/manage.sh start api

stop-api:
	./scripts/manage.sh stop api

restart-api:
	./scripts/manage.sh restart api

start-worker:
	./scripts/manage.sh start worker

stop-worker:
	./scripts/manage.sh stop worker

restart-worker:
	./scripts/manage.sh restart worker

start-frontend:
	./scripts/manage.sh start frontend

stop-frontend:
	./scripts/manage.sh stop frontend

# ── Status & debug ─────────────────────────────────────────────────────────
status:
	./scripts/manage.sh status

debug-db:
	./scripts/manage.sh debug db

debug-incidents:
	./scripts/manage.sh debug incidents

debug-queue:
	./scripts/manage.sh debug queue

reset-incident:
	./scripts/manage.sh reset-incident $(n)

# ── Logs ───────────────────────────────────────────────────────────────────
logs-api:
	./scripts/manage.sh logs api

logs-worker:
	./scripts/manage.sh logs worker

logs-frontend:
	./scripts/manage.sh logs frontend

# ── Database ───────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(msg)"

# ── Quality ────────────────────────────────────────────────────────────────
test:
	pytest --cov=backend --cov-report=term-missing -v

lint:
	ruff check backend/

format:
	ruff format backend/

install:
	pip install -r requirements.txt

env:
	cp .env.example .env
