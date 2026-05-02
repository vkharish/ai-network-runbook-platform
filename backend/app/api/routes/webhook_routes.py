"""Inbound webhook routes — receive events from external systems.

POST /webhooks/servicenow  — ServiceNow state-change notification
POST /webhooks/slack        — Slack interactive button payloads (approve/reject remediation)
"""

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.database.session import get_db
from backend.integrations.servicenow import SNOW_STATUS_MAP, verify_snow_webhook_signature
from backend.models.incident_model import Incident

log = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# Reverse mapping: SNOW state value → platform status
_SNOW_TO_PLATFORM: dict[str, str] = {v: k for k, v in SNOW_STATUS_MAP.items()}


@router.post("/servicenow", status_code=status.HTTP_200_OK)
async def servicenow_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_servicenow_signature: str = Header(default=""),
) -> dict:
    """Receive state-change events from ServiceNow.

    ServiceNow must be configured to send POST requests with:
    - Header: X-ServiceNow-Signature: sha256=<hmac_hex>
    - Body: JSON with sys_id and state fields
    """
    body = await request.body()

    if not verify_snow_webhook_signature(body, x_servicenow_signature):
        log.warning("snow_webhook_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    sys_id = payload.get("sys_id", "")
    snow_state = str(payload.get("state", ""))

    if not sys_id:
        return {"received": True, "action": "ignored", "reason": "no sys_id"}

    result = await db.execute(
        select(Incident).where(Incident.snow_sys_id == sys_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        log.info("snow_webhook_no_match", sys_id=sys_id)
        return {"received": True, "action": "ignored", "reason": "no matching incident"}

    platform_status = _SNOW_TO_PLATFORM.get(snow_state)
    if platform_status and incident.status != platform_status:
        old_status = incident.status
        incident.status = platform_status
        await db.commit()
        log.info(
            "snow_webhook_status_synced",
            incident_id=str(incident.id),
            old=old_status,
            new=platform_status,
            snow_state=snow_state,
        )
        return {"received": True, "action": "updated", "status": platform_status}

    return {"received": True, "action": "no_change"}


@router.post("/slack", status_code=status.HTTP_200_OK)
async def slack_interactive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_slack_request_timestamp: str = Header(default=""),
    x_slack_signature: str = Header(default=""),
) -> dict:
    """Handle Slack interactive button payloads (approve/reject remediation steps).

    Slack sends a URL-encoded form field 'payload' containing JSON.
    Responds within 3 seconds to avoid Slack timeout.
    """
    from backend.core.config import settings

    if not settings.slack_enabled:
        return {"ok": False, "error": "Slack integration not enabled"}

    body = await request.body()

    from backend.integrations.slack import verify_slack_signature
    if not verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
        log.warning("slack_webhook_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    # Slack sends URL-encoded body with 'payload' field containing JSON
    import urllib.parse, json as _json
    try:
        form_data = urllib.parse.parse_qs(body.decode("utf-8"))
        raw_payload = form_data.get("payload", ["{}"])[0]
        payload = _json.loads(raw_payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Slack payload.")

    actions: list[dict] = payload.get("actions", [])
    if not actions:
        return {"ok": True, "action": "no_actions"}

    action = actions[0]
    action_id: str = action.get("action_id", "")
    value: str = action.get("value", "")
    user_email: str = payload.get("user", {}).get("name", "slack-user")

    # action_id format: "approve_remediation:<plan_id>" or "reject_remediation:<plan_id>"
    if ":" not in action_id:
        return {"ok": True, "action": "unknown"}

    action_type, plan_id = action_id.split(":", 1)
    step_numbers = [int(n) for n in value.split(",") if n.strip().isdigit()]

    from backend.models.remediation_model import RemediationPlan
    import uuid as _uuid
    result = await db.execute(
        select(RemediationPlan).where(RemediationPlan.id == _uuid.UUID(plan_id))
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return {"ok": False, "text": "Plan not found"}

    from backend.services import remediation_service
    import uuid as _uuid2

    # Use a system UUID for Slack-originated approvals (no real user object)
    _system_uuid = _uuid2.UUID("00000000-0000-0000-0000-000000000000")

    if action_type == "approve_remediation":
        await remediation_service.approve_steps(
            db, plan, step_numbers, _system_uuid, user_email
        )
        await db.commit()
        log.info("slack_remediation_approved", plan_id=plan_id, by=user_email)
        return {"ok": True, "text": f"✅ Steps approved by {user_email}"}

    elif action_type == "reject_remediation":
        await remediation_service.reject_steps(
            db, plan, step_numbers, "Rejected via Slack", user_email
        )
        await db.commit()
        log.info("slack_remediation_rejected", plan_id=plan_id, by=user_email)
        return {"ok": True, "text": f"❌ Steps rejected by {user_email}"}

    return {"ok": True, "action": "unhandled"}
