"""Remediation service — approval workflow and execution orchestration.

Flow:
  1. RemediationAgent proposes steps (called from incident_service after diagnosis)
  2. Engineer approves/rejects individual steps via API
  3. Admin (or engineer) triggers execution
  4. Celery task runs approved steps via DeviceGateway, stores output
"""

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.logging import get_logger
from backend.models.remediation_model import RemediationPlan
from backend.models.incident_model import Incident

log = get_logger(__name__)


async def create_plan(
    db: AsyncSession,
    incident_id: uuid.UUID,
    proposal,   # RemediationProposal from RemediationAgent
) -> RemediationPlan:
    """Persist a RemediationProposal as a RemediationPlan row."""
    steps = [asdict(s) for s in proposal.steps]
    plan = RemediationPlan(
        incident_id=incident_id,
        status="pending_approval",
        steps=steps,
        notes=proposal.notes,
        llm_provider=proposal.llm_provider,
    )
    db.add(plan)
    await db.flush()
    log.info("remediation_plan_created", incident_id=str(incident_id), steps=len(steps))
    return plan


async def get_plan(db: AsyncSession, incident_id: uuid.UUID) -> RemediationPlan | None:
    result = await db.execute(
        select(RemediationPlan).where(RemediationPlan.incident_id == incident_id)
    )
    return result.scalar_one_or_none()


async def approve_steps(
    db: AsyncSession,
    plan: RemediationPlan,
    step_numbers: list[int],
    approver_id: uuid.UUID,
    approver_email: str,
) -> RemediationPlan:
    """Mark selected steps as approved. Sets plan-level approved_by_id on first approval."""
    now = datetime.now(timezone.utc).isoformat()
    updated = []
    for step in plan.steps:
        s = dict(step)
        if s["step_number"] in step_numbers and s["approval_status"] == "pending":
            s["approval_status"] = "approved"
            s["approved_by"] = approver_email
            s["approved_at"] = now
        updated.append(s)

    plan.steps = updated
    plan.status = _compute_plan_status(updated)

    # Set plan-level approver if not already set
    if plan.approved_by_id is None and any(
        s.get("approval_status") == "approved" for s in updated
    ):
        plan.approved_by_id = approver_id
        plan.approved_at = now

    await db.flush()
    log.info(
        "remediation_steps_approved",
        incident_id=str(plan.incident_id),
        approved=step_numbers,
        approver=approver_email,
    )
    return plan


async def reject_steps(
    db: AsyncSession,
    plan: RemediationPlan,
    step_numbers: list[int],
    reason: str,
    rejector_email: str,
) -> RemediationPlan:
    """Mark selected steps as rejected."""
    updated = []
    for step in plan.steps:
        s = dict(step)
        if s["step_number"] in step_numbers and s["approval_status"] == "pending":
            s["approval_status"] = "rejected"
            s["rejection_reason"] = reason
            s["approved_by"] = rejector_email
        updated.append(s)

    plan.steps = updated
    plan.status = _compute_plan_status(updated)
    await db.flush()
    log.info(
        "remediation_steps_rejected",
        incident_id=str(plan.incident_id),
        rejected=step_numbers,
        reason=reason,
    )
    return plan


async def trigger_execution(
    db: AsyncSession,
    plan: RemediationPlan,
    executor_id: uuid.UUID,
    executor_email: str,
) -> str:
    """Validate approved steps exist and enqueue Celery execution task.

    Returns the Celery task ID.
    """
    approved = [s for s in plan.steps if s.get("approval_status") == "approved"]
    if not approved:
        raise ValueError("No approved steps to execute. Approve at least one step first.")

    plan.status = "executing"
    plan.executed_by_id = executor_id
    plan.executed_at = datetime.now(timezone.utc).isoformat()
    await db.flush()

    from backend.tasks.remediation_task import execute_remediation_plan
    task = execute_remediation_plan.delay(str(plan.id))
    log.info(
        "remediation_execution_triggered",
        incident_id=str(plan.incident_id),
        plan_id=str(plan.id),
        task_id=task.id,
        executor=executor_email,
        approved_steps=len(approved),
    )
    return task.id


async def rollback_plan(
    db: AsyncSession,
    plan: RemediationPlan,
    requester_email: str,
) -> str:
    """Enqueue rollback of a completed remediation plan. Returns Celery task ID."""
    if plan.status not in ("completed", "failed"):
        raise ValueError(
            f"Only completed or failed plans can be rolled back. Current status: {plan.status}"
        )
    plan.status = "rolling_back"
    await db.flush()

    from backend.tasks.remediation_task import rollback_remediation_plan
    task = rollback_remediation_plan.delay(str(plan.id))
    log.info(
        "remediation_rollback_triggered",
        incident_id=str(plan.incident_id),
        plan_id=str(plan.id),
        task_id=task.id,
        requester=requester_email,
    )
    return task.id


def _compute_plan_status(steps: list[dict]) -> str:
    """Derive overall plan status from individual step statuses."""
    statuses = {s.get("approval_status") for s in steps}
    if statuses == {"rejected"}:
        return "rejected"
    if "approved" in statuses:
        return "approved"
    return "pending_approval"
