"""Slack WebAPI client — two-way integration.

Outbound: Block Kit messages to a configured channel.
Inbound:  Interactive button payloads (approve/reject remediation) via webhook.

All httpx calls are lazy. No-op when SLACK_ENABLED=false (default).

Setup:
  1. Create a Slack App at api.slack.com
  2. Add OAuth scope: chat:write
  3. Install to workspace → copy Bot User OAuth Token → SLACK_BOT_TOKEN
  4. Set Interactivity & Shortcuts request URL → {base_url}/api/v1/webhooks/slack
  5. Copy Signing Secret → SLACK_SIGNING_SECRET
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)

_SLACK_API = "https://slack.com/api"


def verify_slack_signature(body: bytes, timestamp_header: str, signature_header: str) -> bool:
    """Validate X-Slack-Signature using HMAC-SHA256.

    Slack signs: "v0:{timestamp}:{body}" with the signing secret.
    Header format: v0=<hex_digest>
    Also validates timestamp is within 5 minutes (replay protection).
    """
    from backend.core.config import settings

    if not settings.slack_signing_secret:
        return True  # dev mode — accept all

    try:
        ts = int(timestamp_header)
    except (ValueError, TypeError):
        return False

    if abs(time.time() - ts) > 300:
        return False  # replay attack

    sig_base = f"v0:{timestamp_header}:{body.decode('utf-8', errors='replace')}"
    computed = "v0=" + hmac.new(
        settings.slack_signing_secret.encode(),
        sig_base.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature_header)


class SlackClient:
    """Sends Block Kit messages to Slack via chat.postMessage."""

    def __init__(self, bot_token: str, channel: str) -> None:
        self._token = bot_token
        self._channel = channel
        self._headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json",
        }

    async def post_message(self, text: str, blocks: list[dict] | None = None) -> dict:
        """POST to slack.com/api/chat.postMessage."""
        import httpx

        payload: dict[str, Any] = {"channel": self._channel, "text": text}
        if blocks:
            payload["blocks"] = blocks

        async with httpx.AsyncClient(headers=self._headers, timeout=15) as client:
            resp = await client.post(f"{_SLACK_API}/chat.postMessage", json=payload)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                log.warning("slack_api_error", error=data.get("error"))
            return data

    async def post_incident_alert(self, incident: Any) -> None:
        """Post a rich Block Kit incident alert. Only for P1/P2."""
        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
        severity_emoji = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}.get(incident.severity, "⚪")

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{severity_emoji} {inc_ref} — {incident.severity} Incident"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{incident.title}*\n{incident.description[:200]}"},
                "fields": [
                    {"type": "mrkdwn", "text": f"*Device:*\n{incident.affected_device or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Protocol:*\n{incident.affected_protocol or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{incident.status}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{incident.severity}"},
                ],
            },
            {"type": "divider"},
        ]
        await self.post_message(text=f"{severity_emoji} {inc_ref}: {incident.title}", blocks=blocks)
        log.info("slack_incident_alert_sent", incident_id=str(incident.id))

    async def post_diagnosis_complete(self, incident: Any, report: dict) -> None:
        """Post diagnosis summary with link to remediation."""
        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
        root_cause = report.get("root_cause", "Unknown")
        confidence = report.get("confidence", 0)
        conf_pct = f"{int(float(confidence) * 100)}%" if confidence else "N/A"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"✅ *{inc_ref} Diagnosis Complete*\n*Root Cause:* {root_cause[:300]}\n*Confidence:* {conf_pct}",
                },
            },
        ]
        await self.post_message(text=f"✅ {inc_ref}: Diagnosis complete", blocks=blocks)

    async def post_remediation_approval_request(self, incident: Any, plan_id: str, steps: list[dict]) -> None:
        """Post interactive message with Approve/Reject buttons for remediation steps."""
        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
        step_numbers = [str(s["step_number"]) for s in steps if s.get("approval_status") == "pending"]

        step_text = "\n".join(
            f"• Step {s['step_number']}: `{s['command']}` on *{s['device']}*"
            for s in steps[:5]  # show max 5
        )

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔧 *{inc_ref} — Remediation Approval Required*\n\n{step_text}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve All"},
                        "style": "primary",
                        "action_id": f"approve_remediation:{plan_id}",
                        "value": ",".join(step_numbers),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject All"},
                        "style": "danger",
                        "action_id": f"reject_remediation:{plan_id}",
                        "value": ",".join(step_numbers),
                    },
                ],
            },
        ]
        await self.post_message(text=f"🔧 {inc_ref}: Remediation approval required", blocks=blocks)

    async def post_remediation_update(self, incident: Any, action: str, actor: str) -> None:
        """Post confirmation after approval/rejection."""
        inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
        emoji = "✅" if action == "approved" else "❌"
        await self.post_message(
            text=f"{emoji} {inc_ref}: Remediation {action} by {actor}"
        )

    @staticmethod
    def from_settings() -> "SlackClient | None":
        from backend.core.config import settings

        if not settings.slack_enabled:
            return None
        if not settings.slack_bot_token or not settings.slack_channel:
            log.warning("slack_misconfigured", reason="SLACK_BOT_TOKEN or SLACK_CHANNEL not set")
            return None
        return SlackClient(settings.slack_bot_token, settings.slack_channel)
