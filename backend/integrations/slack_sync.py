"""Slack sync helpers — called from routes and services.

Every function returns immediately when SLACK_ENABLED=false.
All errors are caught so Slack outage never breaks incident operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.core.logging import get_logger
from backend.integrations.slack import SlackClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.models.incident_model import Incident

log = get_logger(__name__)


async def on_incident_created(incident: "Incident", db: "AsyncSession") -> None:
    """Post P1/P2 incident alert to Slack."""
    client = SlackClient.from_settings()
    if client is None:
        return
    if incident.severity not in ("P1", "P2"):
        return
    try:
        await client.post_incident_alert(incident)
    except Exception as exc:
        log.warning("slack_alert_failed", incident_id=str(incident.id), error=str(exc))


async def on_diagnosis_complete(incident: "Incident", report: dict, db: "AsyncSession") -> None:
    """Post diagnosis summary to Slack and request remediation approval."""
    client = SlackClient.from_settings()
    if client is None:
        return
    try:
        await client.post_diagnosis_complete(incident, report)

        # If a remediation plan exists, post approval request with buttons
        if incident.remediation_plan:
            plan = incident.remediation_plan
            pending_steps = [
                s for s in plan.steps
                if s.get("approval_status") == "pending"
            ]
            if pending_steps:
                await client.post_remediation_approval_request(
                    incident, str(plan.id), pending_steps
                )
    except Exception as exc:
        log.warning("slack_diagnosis_failed", incident_id=str(incident.id), error=str(exc))


async def on_remediation_update(
    incident: "Incident", action: str, actor: str, db: "AsyncSession"
) -> None:
    """Post remediation approval/rejection notification to Slack."""
    client = SlackClient.from_settings()
    if client is None:
        return
    try:
        await client.post_remediation_update(incident, action, actor)
    except Exception as exc:
        log.warning("slack_remediation_failed", incident_id=str(incident.id), error=str(exc))
