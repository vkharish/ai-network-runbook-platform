"""Celery beat task — sync device inventory from NetBox.

Runs on a configurable schedule (default: every 30 minutes).
When NETBOX_ENABLED=false (default), the task exits immediately — no-op.

Sync behavior:
  - Existing device by hostname → update host, vendor, os, display_name
  - New hostname → INSERT with live_enabled=False (safe default)
  - Devices removed from NetBox → NOT deleted (manual cleanup required)
"""

import asyncio

from backend.core.logging import get_logger
from backend.tasks.celery_worker import celery_app

log = get_logger(__name__)


@celery_app.task(name="tasks.netbox_sync_devices", bind=True)
def netbox_sync_devices(self) -> dict:
    """Sync device inventory from NetBox into local Device table."""
    from backend.core.config import settings

    if not settings.netbox_enabled:
        return {"skipped": True, "reason": "NETBOX_ENABLED=false"}

    return asyncio.run(_run_sync())


async def _run_sync() -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select

    from backend.core.config import settings
    from backend.models.device_model import Device
    from backend.integrations.netbox import NetBoxClient

    client = NetBoxClient.from_settings()
    if client is None:
        return {"skipped": True, "reason": "NetBox client not configured"}

    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    summary = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

    try:
        nb_devices = await client.get_all_devices()
    except Exception as exc:
        log.error("netbox_fetch_failed", error=str(exc))
        await engine.dispose()
        return {"error": str(exc)}

    async with AsyncSessionLocal() as db:
        for nb_dev in nb_devices:
            try:
                fields = client.parse_device(nb_dev)
                hostname = fields.get("hostname", "")
                if not hostname:
                    summary["skipped"] += 1
                    continue

                result = await db.execute(
                    select(Device).where(Device.hostname == hostname)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update mutable fields — never overwrite live_enabled or credentials
                    existing.host         = fields["host"] or existing.host
                    existing.vendor       = fields["vendor"]
                    existing.os           = fields["os"]
                    existing.display_name = fields["display_name"]
                    existing.device_type  = fields["device_type"]
                    summary["updated"] += 1
                    log.info("netbox_device_updated", hostname=hostname)
                else:
                    device = Device(**fields)
                    db.add(device)
                    summary["created"] += 1
                    log.info("netbox_device_created", hostname=hostname)

            except Exception as exc:
                log.error("netbox_device_sync_error", hostname=nb_dev.get("name", "?"), error=str(exc))
                summary["errors"] += 1

        await db.commit()

    await engine.dispose()
    log.info("netbox_sync_complete", **summary)
    return summary
