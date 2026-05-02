"""Schemas for the Remediation API."""

from uuid import UUID
from pydantic import BaseModel, ConfigDict


class RemediationStepResponse(BaseModel):
    step_number: int
    device: str
    command: str
    rationale: str
    risk_level: str
    expected_outcome: str
    approval_status: str          # pending | approved | rejected
    approved_by: str | None
    approved_at: str | None
    rejection_reason: str | None
    execution_status: str | None  # None | executing | completed | failed
    execution_output: str | None
    executed_at: str | None


class RemediationPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    status: str
    steps: list[RemediationStepResponse]
    notes: str
    llm_provider: str
    executed_at: str | None
    approved_by_id: UUID | None = None
    approved_at: str | None = None
    execution_log: dict | None = None


class ApproveStepsRequest(BaseModel):
    step_numbers: list[int]    # which step numbers to approve


class RejectStepsRequest(BaseModel):
    step_numbers: list[int]
    reason: str                # mandatory reason for rejection
