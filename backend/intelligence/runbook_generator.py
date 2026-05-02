"""Auto-Runbook Generator — drafts Markdown runbooks from resolved incidents.

Only called when RUNBOOK_AUTOGEN_ENABLED=true.

Process:
  1. Fetch the incident (must be RESOLVED) and its ai_report.
  2. Render a structured prompt containing the incident summary.
  3. Call the configured LLM to draft a Markdown runbook.
  4. Save the draft as a new Runbook record with status=PENDING_REVIEW.
  5. Return the new Runbook ID.

The draft is NOT auto-indexed into ChromaDB — an operator must review and
approve via PATCH /runbooks/{id}/approve before it goes live in RAG.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from backend.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

_AUTOGEN_SYSTEM_PROMPT = (
    "You are a senior network operations engineer writing a troubleshooting runbook. "
    "Based on the resolved incident details provided, create a clear, structured Markdown runbook "
    "that a NOC engineer can follow the next time a similar incident occurs. "
    "Include: Overview, Symptoms, Root Cause Analysis steps, Remediation Steps, and Verification. "
    "Be concise, actionable, and use numbered lists for steps."
)


def _build_prompt(incident: object) -> str:
    report = getattr(incident, "ai_report", {}) or {}
    sections = [
        f"## Incident: {incident.title}",  # type: ignore[attr-defined]
        f"**Severity:** {incident.severity}",  # type: ignore[attr-defined]
        f"**Affected Device:** {incident.affected_device or 'N/A'}",  # type: ignore[attr-defined]
        f"**Affected Protocol:** {incident.affected_protocol or 'N/A'}",  # type: ignore[attr-defined]
        f"\n**Description:**\n{incident.description}",  # type: ignore[attr-defined]
    ]
    if incident.root_cause:  # type: ignore[attr-defined]
        sections.append(f"\n**Root Cause:**\n{incident.root_cause}")  # type: ignore[attr-defined]
    if report:
        import json
        sections.append(f"\n**AI Diagnosis Report (JSON):**\n```json\n{json.dumps(report, indent=2)}\n```")
    return "\n".join(sections)


async def generate_runbook_draft(db: "AsyncSession", incident_id: uuid.UUID) -> uuid.UUID | None:
    """
    Generate a runbook draft for a resolved incident.
    Returns the new Runbook ID or None on failure.
    """
    from sqlalchemy import select
    from backend.models.incident_model import Incident, IncidentStatus
    from backend.models.runbook_model import Runbook, RunbookStatus
    from backend.agents.llm_client import get_llm_client

    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        log.warning("autogen_incident_not_found", incident_id=str(incident_id))
        return None
    if incident.status not in (IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value):
        log.warning("autogen_incident_not_resolved", incident_id=str(incident_id), status=incident.status)
        return None

    prompt = _build_prompt(incident)
    llm = get_llm_client()
    try:
        draft_content = llm.complete(
            messages=[
                {"role": "system", "content": _AUTOGEN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
        )
    except Exception as exc:
        log.error("autogen_llm_failed", incident_id=str(incident_id), error=str(exc))
        return None

    # Persist the draft Markdown as a synthetic "file" with status=PENDING_REVIEW
    safe_title = (incident.title or "incident")[:80].replace("/", "_").replace(" ", "_")
    filename = f"autogen_{incident_id}_{safe_title}.md"

    runbook = Runbook(
        id=uuid.uuid4(),
        filename=filename,
        original_name=filename,
        file_type="md",
        file_size_bytes=len(draft_content.encode()),
        status=RunbookStatus.PENDING_REVIEW.value,
        chunk_count=0,
        description=f"Auto-generated from incident: {incident.title}",
        tags=["auto_generated", incident.affected_protocol or "network"],
        auto_generated=True,
        source_incident_id=incident_id,
    )
    db.add(runbook)
    await db.commit()
    await db.refresh(runbook)

    # Persist the draft content to disk so the approval flow can ingest it
    import os
    upload_dir = "uploads/runbooks"
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, filename), "w") as fh:
        fh.write(draft_content)

    log.info(
        "autogen_runbook_created",
        runbook_id=str(runbook.id),
        incident_id=str(incident_id),
        filename=filename,
    )
    return runbook.id
