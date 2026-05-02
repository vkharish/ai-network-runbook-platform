"""Teams sync helpers — called from routes and services.

Every function returns immediately when TEAMS_ENABLED=false.
All errors are caught so Teams outage never breaks incident operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.core.logging import get_logger
from backend.integrations.teams import TeamsClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.models.incident_model import Incident

log = get_logger(__name__)


async def on_incident_created(incident: "Incident", db: "AsyncSession") -> None:
    """Post P1/P2 incident alert to Teams."""
    client = TeamsClient.from_settings()
    if client is None:
        return
    if incident.severity not in ("P1", "P2"):
        return
    try:
        await client.post_incident_alert(incident)
    except Exception as exc:
        log.warning("teams_alert_failed", incident_id=str(incident.id), error=str(exc))


async def on_diagnosis_complete(incident: "Incident", report: dict, db: "AsyncSession") -> None:
    """Post diagnosis summary to Teams after AI analysis completes."""
    client = TeamsClient.from_settings()
    if client is None:
        return
    try:
        await client.post_diagnosis_complete(incident, report)
    except Exception as exc:
        log.warning("teams_diagnosis_failed", incident_id=str(incident.id), error=str(exc))


async def on_remediation_update(
    incident: "Incident", action: str, actor: str, db: "AsyncSession"
) -> None:
    """Post remediation approval/rejection notification to Teams."""
    client = TeamsClient.from_settings()
    if client is None:
        return
    try:
        await client.post_remediation_update(incident, action, actor)
    except Exception as exc:
        log.warning("teams_remediation_failed", incident_id=str(incident.id), error=str(exc))
