"""RemediationPlan ORM model.

One RemediationPlan per incident. Stores all proposed CLI steps as JSONB,
each with individual approval tracking and execution results.

Status lifecycle:
  PENDING_APPROVAL → engineer approves/rejects individual steps
  APPROVED         → at least one step approved, ready to execute
  EXECUTING        → Celery task is running approved steps
  COMPLETED        → all approved steps executed successfully
  FAILED           → one or more steps failed during execution
  REJECTED         → all steps were rejected by engineer
  ROLLED_BACK      → execution was reversed by admin
"""

import uuid
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import text

from backend.database.base import AuditBase


class RemediationPlan(AuditBase):
    __tablename__ = "remediation_plans"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Overall plan status
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_approval",
        index=True,
    )

    # JSONB array of RemediationStep dicts (see remediation_agent.py)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Free-text notes from the RemediationAgent
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Which LLM proposed this plan
    llm_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # Execution tracking
    executed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    executed_at: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Plan-level approval tracking (who approved the overall plan)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_at: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Execution summary written by Celery task on completion
    execution_log: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    incident: Mapped["Incident"] = relationship("Incident", back_populates="remediation_plan")  # type: ignore
    executed_by: Mapped["User | None"] = relationship("User", foreign_keys=[executed_by_id])  # type: ignore
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_id])  # type: ignore
