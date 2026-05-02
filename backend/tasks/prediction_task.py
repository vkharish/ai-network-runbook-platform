"""Celery beat task: run anomaly detection across all devices and metrics.

No-op when PREDICTIVE_ENABLED=false.
Scheduled every 5 minutes by the beat scheduler.
"""

import asyncio

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.tasks.celery_worker import celery_app

log = get_logger(__name__)


@celery_app.task(name="tasks.run_anomaly_detection", bind=True)
def run_anomaly_detection(self) -> dict:
    if not settings.predictive_enabled:
        return {"skipped": True, "reason": "PREDICTIVE_ENABLED=false"}

    async def _run() -> dict:
        from sqlalchemy import select, func
        from backend.database.session import AsyncSessionLocal
        from backend.models.anomaly_model import AnomalyMetric
        from backend.intelligence.anomaly_detector import run_detection

        anomalies_found = 0
        incidents_created = 0

        async with AsyncSessionLocal() as db:
            # Get distinct (device_id, metric_name) pairs that have at least 2 samples
            result = await db.execute(
                select(AnomalyMetric.device_id, AnomalyMetric.metric_name)
                .group_by(AnomalyMetric.device_id, AnomalyMetric.metric_name)
                .having(func.count(AnomalyMetric.id) >= 2)
            )
            pairs = result.all()

        for device_id, metric_name in pairs:
            try:
                async with AsyncSessionLocal() as db:
                    detection = await run_detection(db, device_id, metric_name)
                if detection["is_anomaly"]:
                    anomalies_found += 1
                    if detection["incident_id"]:
                        incidents_created += 1
            except Exception as exc:
                log.warning(
                    "anomaly_detection_pair_failed",
                    device_id=str(device_id),
                    metric=metric_name,
                    error=str(exc),
                )

        log.info(
            "anomaly_detection_complete",
            pairs_checked=len(pairs),
            anomalies_found=anomalies_found,
            incidents_created=incidents_created,
        )
        return {
            "pairs_checked": len(pairs),
            "anomalies_found": anomalies_found,
            "incidents_created": incidents_created,
        }

    return asyncio.run(_run())
