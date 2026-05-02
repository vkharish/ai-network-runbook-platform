"""Inbound webhook routes — receive events from external systems.

POST /webhooks/servicenow  — ServiceNow state-change notification
"""

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

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
