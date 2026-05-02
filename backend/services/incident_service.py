"""Incident service — runs the multi-agent diagnosis pipeline via OrchestratorAgent.

Flow (dynamic, determined by OrchestratorAgent):
  InvestigationAgent
    → AnalysisAgent
      → [SecondOpinionAgent  if confidence < 0.6]
      → [BGPSpecialistAgent  if protocol == bgp]
      → [JunosSpecialistAgent if Juniper device]
    → ReportAgent
  → persist to DB
"""

import uuid
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.orchestrator_agent import OrchestratorAgent
from backend.core.logging import get_logger
from backend.models.incident_model import Incident, IncidentStatus
from backend.models.remediation_model import RemediationPlan  # noqa: F401 — register mapper
from backend.models.runbook_model import Runbook  # noqa: F401 — ensure all mappers are registered
from backend.models.topology_model import Topology, TopologyStatus
from backend.models.user_model import User  # noqa: F401

log = get_logger(__name__)


async def run_diagnosis(incident_id: str, db: AsyncSession) -> dict:
    """
    Full diagnosis pipeline for a single incident.

    1. Fetch incident from DB.
    2. OrchestratorAgent — dynamically routes through specialist agents.
    3. Persist ai_report + root_cause, transition status → AWAITING_INPUT.

    Returns the saved ai_report dict.
    Reverts status to OPEN on failure so the engineer can retry.
    """
    result = await db.execute(select(Incident).where(Incident.id == uuid.UUID(incident_id)))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise ValueError(f"Incident {incident_id} not found")

    inc_ref = f"INC-{str(incident.incident_number or 0).zfill(4)}"
    log.info("diagnosis_pipeline_start", inc_ref=inc_ref, incident_id=incident_id, title=incident.title)

    try:
        # ── Load topology for neighbor context (optional) ────────────────
        topology_result = await db.execute(
            select(Topology)
            .where(Topology.is_default == True)  # noqa: E712
            .where(Topology.status == TopologyStatus.ACTIVE.value)
        )
        topology = topology_result.scalar_one_or_none()
        topology_graph = topology.graph_data if topology else None
        if topology_graph:
            log.info("topology_context_loaded", inc_ref=inc_ref, incident_id=incident_id, topology=topology.name)

        # ── Multi-agent orchestration ─────────────────────────────────────
        report, remediation_proposal = OrchestratorAgent().run(incident, topology_graph=topology_graph)

        orchestration = report.orchestration
        log.info(
            "diagnosis_pipeline_complete",
            inc_ref=inc_ref,
            incident_id=incident_id,
            agents_invoked=orchestration.get("agents_invoked", []),
            iterations=orchestration.get("total_iterations", 0),
            confidence=report.confidence,
            steps=len(report.steps),
            citations=len(report.citations),
            remediation_steps=len(remediation_proposal.steps) if remediation_proposal else 0,
        )

        # ── Persist diagnosis ─────────────────────────────────────────────
        # Truncate cli_evidence to prevent enormous JSONB storage on live devices
        report_dict = asdict(report)
        if report_dict.get("cli_evidence"):
            report_dict["cli_evidence"] = {
                k: v[:1000] + "…[truncated]" if len(v) > 1000 else v
                for k, v in report_dict["cli_evidence"].items()
            }
        incident.ai_report = report_dict
        incident.root_cause = report.root_cause
        incident.status = IncidentStatus.AWAITING_INPUT.value

        # ── Persist remediation plan (pending human approval) ─────────────
        # Upsert: delete existing plan first so re-diagnosis always produces a fresh one
        if remediation_proposal and remediation_proposal.steps:
            from backend.services.remediation_service import create_plan, get_plan
            existing_plan = await get_plan(db, incident.id)
            if existing_plan:
                await db.delete(existing_plan)
                await db.flush()
            await create_plan(db, incident.id, remediation_proposal)
            log.info(
                "remediation_plan_persisted",
                inc_ref=inc_ref,
                incident_id=incident_id,
                steps=len(remediation_proposal.steps),
            )

        await db.commit()

        log.info("diagnosis_persisted", inc_ref=inc_ref, incident_id=incident_id, status=incident.status)
        return incident.ai_report  # type: ignore[return-value]

    except Exception as exc:
        log.error("diagnosis_pipeline_failed", inc_ref=inc_ref, incident_id=incident_id, error=str(exc))
        # Revert to OPEN so the engineer can trigger a retry
        try:
            incident.status = IncidentStatus.OPEN.value
            await db.commit()
        except Exception:
            pass
        raise
