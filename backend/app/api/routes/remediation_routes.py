"""Remediation routes — human-in-the-loop approval and execution.

Workflow:
  GET  /incidents/{id}/remediation          — view proposed plan
  POST /incidents/{id}/remediation/approve  — approve specific steps (ENGINEER+)
  POST /incidents/{id}/remediation/reject   — reject steps with reason (ENGINEER+)
  POST /incidents/{id}/remediation/execute  — execute approved steps (ADMIN only)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, require_role
from backend.core.security import Role
from backend.database.session import get_db
from backend.models.user_model import User
from backend.schemas.remediation_schema import (
    ApproveStepsRequest,
    RejectStepsRequest,
    RemediationPlanResponse,
    RemediationStepResponse,
)
from backend.services import remediation_service

router = APIRouter(prefix="/incidents", tags=["Remediation"])


def _to_response(plan) -> RemediationPlanResponse:
    return RemediationPlanResponse(
        id=plan.id,
        incident_id=plan.incident_id,
        status=plan.status,
        steps=[RemediationStepResponse(**s) for s in plan.steps],
        notes=plan.notes,
        llm_provider=plan.llm_provider,
        executed_at=plan.executed_at,
    )


@router.get("/{incident_id}/remediation", response_model=RemediationPlanResponse)
async def get_remediation_plan(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> RemediationPlanResponse:
    """View the AI-proposed remediation plan for an incident."""
    plan = await remediation_service.get_plan(db, incident_id)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail="No remediation plan found. Run /diagnose first.",
        )
    return _to_response(plan)


@router.post("/{incident_id}/remediation/approve", response_model=RemediationPlanResponse)
async def approve_steps(
    incident_id: UUID,
    payload: ApproveStepsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ENGINEER)),
) -> RemediationPlanResponse:
    """Approve specific remediation steps by step number.

    Only approved steps will be executed when /execute is called.
    Requires ENGINEER role or above.
    """
    plan = await remediation_service.get_plan(db, incident_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found.")
    if plan.status in ("executing", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Plan is already {plan.status} — cannot modify approvals.",
        )
    if not payload.step_numbers:
        raise HTTPException(status_code=400, detail="Provide at least one step_number.")

    plan = await remediation_service.approve_steps(
        db, plan, payload.step_numbers, current_user.email
    )
    await db.commit()
    return _to_response(plan)


@router.post("/{incident_id}/remediation/reject", response_model=RemediationPlanResponse)
async def reject_steps(
    incident_id: UUID,
    payload: RejectStepsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ENGINEER)),
) -> RemediationPlanResponse:
    """Reject specific remediation steps with a mandatory reason.

    Rejected steps will be skipped during execution.
    Requires ENGINEER role or above.
    """
    plan = await remediation_service.get_plan(db, incident_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found.")
    if plan.status in ("executing", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Plan is already {plan.status} — cannot modify approvals.",
        )
    if not payload.step_numbers:
        raise HTTPException(status_code=400, detail="Provide at least one step_number.")
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="A rejection reason is required.")

    plan = await remediation_service.reject_steps(
        db, plan, payload.step_numbers, payload.reason, current_user.email
    )
    await db.commit()
    return _to_response(plan)


@router.post("/{incident_id}/remediation/execute", status_code=status.HTTP_202_ACCEPTED)
async def execute_remediation(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
) -> dict:
    """Execute all approved remediation steps on the target devices.

    Requires ADMIN role — engineer approves, admin executes.
    Steps run sequentially via Celery. Poll GET /remediation to see progress.
    """
    plan = await remediation_service.get_plan(db, incident_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Remediation plan not found.")
    if plan.status == "executing":
        raise HTTPException(status_code=409, detail="Execution already in progress.")
    if plan.status == "completed":
        raise HTTPException(status_code=409, detail="Plan already completed.")
    if plan.status == "rejected":
        raise HTTPException(status_code=400, detail="All steps were rejected — nothing to execute.")

    try:
        task_id = await remediation_service.trigger_execution(
            db, plan, current_user.id, current_user.email
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "message": "Remediation execution started",
        "task_id": task_id,
        "incident_id": str(incident_id),
        "poll": f"/api/v1/incidents/{incident_id}/remediation",
    }
