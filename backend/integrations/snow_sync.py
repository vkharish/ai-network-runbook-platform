"""ServiceNow sync helpers — called from incident routes.

Every function is wrapped in try/except so a ServiceNow outage
never propagates to the caller and breaks incident operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.core.logging import get_logger
from backend.integrations.servicenow import SNOW_SEVERITY_MAP, SNOW_STATUS_MAP, ServiceNowClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.models.incident_model import Incident

log = get_logger(__name__)


async def on_incident_created(incident: "Incident", db: "AsyncSession") -> None:
    """Create a matching ticket in ServiceNow and store the sys_id."""
    client = ServiceNowClient.from_settings()
    if client is None:
        return

    impact, urgency = SNOW_SEVERITY_MAP.get(incident.severity, ("2", "2"))
    payload = {
        "short_description": incident.title,
        "description": incident.description,
        "state": SNOW_STATUS_MAP.get(incident.status, "1"),
        "impact": impact,
        "urgency": urgency,
        "category": "Network",
        "subcategory": "Incident",
        "u_affected_device": incident.affected_device or "",
        "u_platform_incident_id": str(incident.id),
    }

    try:
        sys_id = await client.create_incident(payload)
        incident.snow_sys_id = sys_id
        await db.flush()
        log.info(
            "snow_incident_synced",
            incident_id=str(incident.id),
            snow_sys_id=sys_id,
        )
    except Exception as exc:
        log.warning(
            "snow_create_failed",
            incident_id=str(incident.id),
            error=str(exc),
        )


async def on_incident_status_changed(incident: "Incident", db: "AsyncSession") -> None:
    """Push status update to ServiceNow if a sys_id exists."""
    if not incident.snow_sys_id:
        return

    client = ServiceNowClient.from_settings()
    if client is None:
        return

    snow_state = SNOW_STATUS_MAP.get(incident.status)
    if snow_state is None:
        return

    payload: dict = {"state": snow_state}
    if incident.root_cause:
        payload["close_notes"] = incident.root_cause
    if incident.status in ("resolved", "closed"):
        payload["close_code"] = "Solved (Permanently)"

    try:
        await client.update_incident(incident.snow_sys_id, payload)
    except Exception as exc:
        log.warning(
            "snow_update_failed",
            incident_id=str(incident.id),
            snow_sys_id=incident.snow_sys_id,
            error=str(exc),
        )
