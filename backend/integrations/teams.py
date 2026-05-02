"""Microsoft Teams notifications via incoming webhook (Adaptive Cards).

Outbound only in Phase 2 — sends Adaptive Card payloads to a Teams channel.
All httpx calls are lazy. No-op when TEAMS_ENABLED=false (default).

Setup: In Teams → channel → Connectors → Incoming Webhook → copy URL → TEAMS_WEBHOOK_URL
"""

from __future__ import annotations

from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)


class TeamsClient:
    """Sends Adaptive Cards to a Microsoft Teams incoming webhook."""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def post_adaptive_card(self, card_body: list[dict], actions: list[dict] | None = None) -> None:
        """POST an Adaptive Card to the Teams webhook."""
        import httpx  # already in requirements

        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": card_body,
                        **({"actions": actions} if actions else {}),
                    },
                }
            ],
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(self._webhook_url, json=payload)
            resp.raise_for_status()

    async def post_incident_alert(self, incident: Any) -> None:
        """Post a P1/P2 incident creation alert as an Adaptive Card."""
        severity_color = {"P1": "attention", "P2": "warning"}.get(incident.severity, "default")
        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"

        body = [
            {
                "type": "TextBlock",
                "text": f"🚨 {inc_ref} — {incident.title}",
                "weight": "Bolder",
                "size": "Large",
                "color": severity_color,
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Severity",  "value": incident.severity},
                    {"title": "Status",    "value": incident.status},
                    {"title": "Device",    "value": incident.affected_device or "N/A"},
                    {"title": "Protocol",  "value": incident.affected_protocol or "N/A"},
                ],
            },
            {
                "type": "TextBlock",
                "text": incident.description[:300],
                "wrap": True,
                "isSubtle": True,
            },
        ]
        await self.post_adaptive_card(body)
        log.info("teams_incident_alert_sent", incident_id=str(incident.id))

    async def post_diagnosis_complete(self, incident: Any, report: dict) -> None:
        """Post diagnosis summary card after AI analysis completes."""
        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
        root_cause = report.get("root_cause", "Unknown")
        confidence = report.get("confidence", 0)
        conf_pct = f"{int(confidence * 100)}%" if isinstance(confidence, float) else str(confidence)

        body = [
            {
                "type": "TextBlock",
                "text": f"✅ {inc_ref} — Diagnosis Complete",
                "weight": "Bolder",
                "size": "Medium",
                "color": "good",
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Root Cause",  "value": root_cause[:200]},
                    {"title": "Confidence",  "value": conf_pct},
                    {"title": "Status",      "value": incident.status},
                ],
            },
        ]
        await self.post_adaptive_card(body)
        log.info("teams_diagnosis_sent", incident_id=str(incident.id))

    async def post_remediation_update(self, incident: Any, action: str, actor: str) -> None:
        """Post remediation approval/rejection notification."""
        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
        emoji = "✅" if action == "approved" else "❌"
        color = "good" if action == "approved" else "attention"

        body = [
            {
                "type": "TextBlock",
                "text": f"{emoji} {inc_ref} — Remediation {action.capitalize()} by {actor}",
                "weight": "Bolder",
                "color": color,
                "wrap": True,
            },
        ]
        await self.post_adaptive_card(body)

    @staticmethod
    def from_settings() -> "TeamsClient | None":
        from backend.core.config import settings

        if not settings.teams_enabled:
            return None
        if not settings.teams_webhook_url:
            log.warning("teams_misconfigured", reason="TEAMS_WEBHOOK_URL not set")
            return None
        return TeamsClient(settings.teams_webhook_url)
