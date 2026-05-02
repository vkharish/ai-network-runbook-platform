"""ServiceNow Table API client.

Provides async CRUD operations against the ServiceNow incident table.
All methods are no-ops (return None / empty) when SNOW_ENABLED=false
so the rest of the codebase never needs to guard on that flag.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from backend.core.logging import get_logger

log = get_logger(__name__)

# Map platform incident status → ServiceNow state value
SNOW_STATUS_MAP: dict[str, str] = {
    "open": "1",            # New
    "diagnosing": "2",      # In Progress
    "awaiting_input": "3",  # On Hold
    "resolved": "6",        # Resolved
    "closed": "7",          # Closed
}

# Map platform severity → SNOW impact + urgency (1=High, 2=Medium, 3=Low)
SNOW_SEVERITY_MAP: dict[str, tuple[str, str]] = {
    "P1": ("1", "1"),
    "P2": ("2", "1"),
    "P3": ("2", "2"),
    "P4": ("3", "3"),
}


class ServiceNowClient:
    """Async REST client for the ServiceNow Table API."""

    def __init__(self, instance_url: str, username: str, password: str) -> None:
        self._base = f"https://{instance_url}/api/now/table"
        self._auth = (username, password)
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def create_incident(self, payload: dict[str, Any]) -> str:
        """POST /incident — returns the SNOW sys_id of the created record."""
        async with httpx.AsyncClient(auth=self._auth, headers=self._headers, timeout=15) as client:
            resp = await client.post(f"{self._base}/incident", json=payload)
            resp.raise_for_status()
            sys_id: str = resp.json()["result"]["sys_id"]
            log.info("snow_incident_created", sys_id=sys_id)
            return sys_id

    async def update_incident(self, sys_id: str, payload: dict[str, Any]) -> None:
        """PATCH /incident/{sys_id}."""
        async with httpx.AsyncClient(auth=self._auth, headers=self._headers, timeout=15) as client:
            resp = await client.patch(f"{self._base}/incident/{sys_id}", json=payload)
            resp.raise_for_status()
            log.info("snow_incident_updated", sys_id=sys_id)

    async def get_incident(self, sys_id: str) -> dict[str, Any]:
        """GET /incident/{sys_id}."""
        async with httpx.AsyncClient(auth=self._auth, headers=self._headers, timeout=15) as client:
            resp = await client.get(f"{self._base}/incident/{sys_id}")
            resp.raise_for_status()
            return resp.json()["result"]

    @staticmethod
    def from_settings() -> "ServiceNowClient | None":
        """Return a client if SNOW_ENABLED=true, otherwise None."""
        from backend.core.config import settings

        if not settings.snow_enabled:
            return None
        if not settings.snow_instance_url:
            log.warning("snow_misconfigured", reason="SNOW_INSTANCE_URL not set")
            return None
        return ServiceNowClient(
            settings.snow_instance_url,
            settings.snow_username,
            settings.snow_password,
        )


def verify_snow_webhook_signature(body: bytes, signature_header: str) -> bool:
    """Validate inbound ServiceNow webhook using HMAC-SHA256.

    ServiceNow sends: X-ServiceNow-Signature: sha256=<hex_digest>
    """
    from backend.core.config import settings

    if not settings.snow_webhook_secret:
        # No secret configured — accept all (dev mode)
        return True

    expected_prefix = "sha256="
    if not signature_header.startswith(expected_prefix):
        return False

    received_digest = signature_header[len(expected_prefix):]
    computed = hmac.new(
        settings.snow_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, received_digest)
