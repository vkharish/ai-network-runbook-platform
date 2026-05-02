"""Celery task: correlate a newly created incident against existing open incidents.

No-op when CORRELATION_ENABLED=false.
"""

import asyncio
import uuid

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.tasks.celery_worker import celery_app

log = get_logger(__name__)


@celery_app.task(name="tasks.correlate_incident", bind=True, max_retries=2)
def correlate_incident(self, incident_id: str) -> dict:
    if not settings.correlation_enabled:
        return {"skipped": True, "reason": "CORRELATION_ENABLED=false"}

    async def _run() -> dict:
        from sqlalchemy import select
        from backend.database.session import AsyncSessionLocal
        from backend.models.incident_model import Incident
        from backend.intelligence.correlator import find_parent_incident

        async with AsyncSessionLocal() as db:
            iid = uuid.UUID(incident_id)
            result = await db.execute(select(Incident).where(Incident.id == iid))
            incident = result.scalar_one_or_none()
            if not incident:
                return {"error": "incident_not_found"}

            parent_id, score = await find_parent_incident(
                db=db,
                incident_id=iid,
                title=incident.title,
                description=incident.description,
                affected_device=incident.affected_device,
                affected_protocol=incident.affected_protocol,
            )

            if parent_id:
                incident.parent_incident_id = parent_id
                incident.correlation_score = score
                await db.commit()
                log.info("correlation_task_linked", incident_id=incident_id, parent_id=str(parent_id), score=score)
                return {"parent_id": str(parent_id), "score": score}

            return {"parent_id": None, "score": 0.0}

    return asyncio.run(_run())
