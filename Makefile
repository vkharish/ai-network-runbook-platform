.PHONY: help dev up down logs migrate test lint format install env

help:
	@echo "  dev     Start infra + API with hot reload"
	@echo "  up      Start all Docker services"
	@echo "  down    Stop containers"
	@echo "  migrate Run Alembic migrations"
	@echo "  test    Run pytest"
	@echo "  lint    Run ruff"

up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

logs:
	docker compose -f docker/docker-compose.yml logs -f

dev:
	docker compose -f docker/docker-compose.yml up -d postgres redis chromadb
	uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(msg)"

worker:
	OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES celery -A backend.tasks.celery_worker worker --loglevel=info --pool=solo

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
