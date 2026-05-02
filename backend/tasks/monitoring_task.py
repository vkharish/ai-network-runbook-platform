"""Celery Beat periodic task — continuous device health monitoring.

Runs every 5 minutes (configurable). For each live-enabled device:
  1. Runs read-only health check commands via DeviceGateway
  2. Parses output for known failure signatures (BGP down, interface down, etc.)
  3. If anomaly found and no open incident exists for that device → auto-creates incident
  4. Triggers AI diagnosis automatically on the new incident

Schedule is registered in celery_worker.py beat_schedule.
"""

import asyncio

from backend.tasks.celery_worker import celery_app
from backend.core.logging import get_logger

log = get_logger(__name__)


@celery_app.task(name="tasks.monitor_device_health")
def monitor_device_health() -> dict:
    """Periodic health check across all live-enabled devices."""
    return asyncio.run(_run_monitoring())


async def _run_monitoring() -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker, selectinload
    from sqlalchemy import select, and_
    from backend.core.config import settings
    from backend.models.device_model import Device
    from backend.models.incident_model import Incident, IncidentStatus

    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    summary = {"devices_checked": 0, "anomalies_found": 0, "incidents_created": 0}

    async with AsyncSessionLocal() as db:
        # Only check live-enabled devices
        result = await db.execute(
            select(Device)
            .options(selectinload(Device.credential))
            .where(Device.live_enabled == True)  # noqa: E712
        )
        devices = result.scalars().all()

        if not devices:
            log.info("monitoring_no_live_devices")
            await engine.dispose()
            return summary

        log.info("monitoring_cycle_start", device_count=len(devices))

        from backend.automation.device_gateway import run_command
        from backend.monitoring.health_monitor import run_health_checks

        # ── Run all device checks in parallel ────────────────────────────────
        async def check_device(device) -> tuple:
            """SSH + parse for one device. Returns (device, anomalies)."""
            try:
                anomalies = await asyncio.to_thread(run_health_checks, device, run_command)
                return device, anomalies
            except Exception as exc:
                log.warning("monitoring_device_failed", device=device.hostname, error=str(exc))
                return device, []

        results = await asyncio.gather(*[check_device(d) for d in devices])

        summary["devices_checked"] = len(devices)

        for device, anomalies in results:
            if not anomalies:
                continue

            summary["anomalies_found"] += len(anomalies)

            for anomaly in anomalies:
                # Check if an open incident already exists for this device+protocol
                existing = await db.execute(
                    select(Incident).where(
                        and_(
                            Incident.affected_device == device.hostname,
                            Incident.affected_protocol == anomaly.protocol,
                            Incident.status.in_([
                                IncidentStatus.OPEN.value,
                                IncidentStatus.DIAGNOSING.value,
                                IncidentStatus.AWAITING_INPUT.value,
                            ]),
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    log.info(
                        "monitoring_incident_already_open",
                        device=device.hostname,
                        protocol=anomaly.protocol,
                    )
                    continue

                # Auto-create incident
                incident = await _create_auto_incident(db, device, anomaly)
                summary["incidents_created"] += 1

                log.info(
                    "monitoring_incident_auto_created",
                    incident_id=str(incident.id),
                    device=device.hostname,
                    protocol=anomaly.protocol,
                    severity=anomaly.severity,
                )

                # Trigger diagnosis
                from backend.tasks.diagnosis_task import run_diagnosis_task
                run_diagnosis_task.delay(str(incident.id))

        await db.commit()

    await engine.dispose()
    log.info("monitoring_cycle_complete", **summary)
    return summary


async def _create_auto_incident(db, device, anomaly) -> "Incident":  # type: ignore
    from sqlalchemy import select, func
    from backend.models.incident_model import Incident, IncidentStatus
    from backend.models.user_model import User

    # Use the first admin account as the auto-creator
    result = await db.execute(select(User).where(User.role == "admin").limit(1))
    admin = result.scalar_one_or_none()
    if not admin:
        result = await db.execute(select(User).limit(1))
        admin = result.scalar_one()

    # Assign next incident number
    max_result = await db.execute(select(func.max(Incident.incident_number)))
    max_num = max_result.scalar() or 0

    incident = Incident(
        incident_number=max_num + 1,
        title=f"[AUTO] {anomaly.description}",
        description=(
            f"Automatically detected by health monitor.\n\n"
            f"Device: {device.hostname}\n"
            f"Protocol: {anomaly.protocol}\n"
            f"Finding: {anomaly.description}\n\n"
            f"Evidence:\n{anomaly.raw_evidence}"
        ),
        status=IncidentStatus.OPEN.value,
        severity=anomaly.severity,
        affected_device=device.hostname,
        affected_protocol=anomaly.protocol,
        created_by=admin.id,
    )
    db.add(incident)
    await db.flush()
    return incident
