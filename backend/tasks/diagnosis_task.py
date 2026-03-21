"""Celery task: run the full AI diagnosis pipeline for an incident.

Follows the same pattern as document_ingestion.py:
  - Creates a fresh async engine inside asyncio.run() to avoid event-loop issues on macOS.
  - Calls incident_service.run_diagnosis with a locally-scoped AsyncSession.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger
from backend.services.incident_service import run_diagnosis
from backend.tasks.celery_worker import celery_app

configure_logging()
log = get_logger(__name__)


def _make_session_factory():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    return engine, factory


async def _run_async(incident_id: str) -> dict:
    engine, SessionLocal = _make_session_factory()
    try:
        async with SessionLocal() as db:
            return await run_diagnosis(incident_id, db)
    finally:
        await engine.dispose()


@celery_app.task(
    name="tasks.run_diagnosis",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    acks_late=True,
)
def run_diagnosis_task(self, incident_id: str) -> dict:
    log.info("diagnosis_task_started", incident_id=incident_id)
    try:
        result = asyncio.run(_run_async(incident_id))
        log.info("diagnosis_task_complete", incident_id=incident_id)
        return result
    except Exception as exc:
        log.error("diagnosis_task_failed", incident_id=incident_id, error=str(exc))
        raise self.retry(exc=exc)
