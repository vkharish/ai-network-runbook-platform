"""Celery task: auto-generate a runbook draft from a resolved incident.

No-op when RUNBOOK_AUTOGEN_ENABLED=false.
"""

import asyncio
import uuid

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.tasks.celery_worker import celery_app

log = get_logger(__name__)


@celery_app.task(name="tasks.generate_runbook_from_incident", bind=True, max_retries=2)
def generate_runbook_from_incident(self, incident_id: str) -> dict:
    if not settings.runbook_autogen_enabled:
        return {"skipped": True, "reason": "RUNBOOK_AUTOGEN_ENABLED=false"}

    async def _run() -> dict:
        from backend.database.session import AsyncSessionLocal
        from backend.intelligence.runbook_generator import generate_runbook_draft

        async with AsyncSessionLocal() as db:
            runbook_id = await generate_runbook_draft(db, uuid.UUID(incident_id))
            if runbook_id:
                return {"runbook_id": str(runbook_id)}
            return {"runbook_id": None, "error": "generation_failed"}

    return asyncio.run(_run())
