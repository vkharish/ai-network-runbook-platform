"""DeviceRegistry — resolves device hostnames to Device model instances.

Falls back gracefully: if a device is not in the DB, returns a synthetic
Device object with live_enabled=False so SimulatorDriver is used.
"""

from dataclasses import dataclass, field
from backend.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class SyntheticDevice:
    """Stand-in for devices not yet registered in the DB.
    Always uses SimulatorDriver (live_enabled=False).
    """
    hostname: str
    display_name: str = ""
    vendor: str = "generic"
    os: str = "generic"
    device_type: str = "cisco_ios"
    host: str | None = None
    port: int = 22
    live_enabled: bool = False
    topology_node_id: str | None = None
    credential: None = field(default=None)


async def get_device(db, hostname: str):
    """Fetch Device from DB by hostname. Returns SyntheticDevice if not found."""
    try:
        from sqlalchemy import select
        from backend.models.device_model import Device

        # Normalize: "R4-ACCESS" → try exact first, then prefix match
        result = await db.execute(
            select(Device).where(Device.hostname == hostname)
        )
        device = result.scalar_one_or_none()

        if device is None:
            # Try case-insensitive prefix match ("R4" matches "R4-ACCESS")
            normalized = hostname.upper()
            result = await db.execute(select(Device))
            all_devices = list(result.scalars().all())
            device = next(
                (d for d in all_devices if d.hostname.upper().startswith(normalized)
                 or normalized.startswith(d.hostname.upper().split("-")[0])),
                None,
            )

        if device:
            log.info("device_registry_hit", hostname=hostname, live_enabled=device.live_enabled)
            return device

    except Exception as exc:
        log.warning("device_registry_error", hostname=hostname, error=str(exc))

    # Fallback — synthetic device uses simulator
    log.info("device_registry_miss", hostname=hostname, fallback="simulator")
    return SyntheticDevice(hostname=hostname)


def get_device_sync(hostname: str):
    """Sync DB lookup for use in Celery worker / non-async contexts.

    Uses a short-lived sync SQLAlchemy engine so the Celery worker can
    resolve live_enabled without needing an async event loop.
    Falls back to SyntheticDevice (simulator) on any error.
    """
    try:
        from sqlalchemy import create_engine, select, text
        from sqlalchemy.orm import Session, selectinload
        from backend.core.config import settings
        from backend.models.device_model import Device

        # Convert asyncpg URL → psycopg2 sync URL
        sync_url = settings.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        )

        engine = create_engine(sync_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with Session(engine) as session:
            # Exact match first
            device = session.execute(
                select(Device)
                .options(selectinload(Device.credential))
                .where(Device.hostname == hostname)
            ).scalar_one_or_none()

            if device is None:
                # Prefix match: "xrd-1" matches "xrd-1", "R4" matches "R4-ACCESS"
                normalized = hostname.upper()
                all_devices = session.execute(
                    select(Device).options(selectinload(Device.credential))
                ).scalars().all()
                device = next(
                    (d for d in all_devices
                     if d.hostname.upper().startswith(normalized)
                     or normalized.startswith(d.hostname.upper().split("-")[0])),
                    None,
                )

            engine.dispose()

            if device:
                log.info(
                    "device_registry_sync_hit",
                    hostname=hostname,
                    live_enabled=device.live_enabled,
                )
                return device

    except Exception as exc:
        log.warning("device_registry_sync_error", hostname=hostname, error=str(exc))

    log.info("device_registry_sync_miss", hostname=hostname, fallback="simulator")
    return SyntheticDevice(hostname=hostname)
