import uuid
from enum import Enum

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import AuditBase


class IncidentStatus(str, Enum):
    OPEN = "open"
    DIAGNOSING = "diagnosing"
    AWAITING_INPUT = "awaiting_input"
    RESOLVED = "resolved"
    CLOSED = "closed"
    PREDICTED = "predicted"  # Phase 3: anomaly detector pre-creates incident


class IncidentSeverity(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class Incident(AuditBase):
    __tablename__ = "incidents"

    incident_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=IncidentStatus.OPEN.value, index=True
    )
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default=IncidentSeverity.P3.value)
    affected_device: Mapped[str | None] = mapped_column(String(255), nullable=True)
    affected_protocol: Mapped[str | None] = mapped_column(String(100), nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    diagnosis_steps: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    snow_sys_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Phase 3: incident correlation (nullable — only set when CORRELATION_ENABLED=true)
    parent_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    correlation_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Multi-tenant site isolation (nullable — only used when MULTITENANCY_ENABLED=true)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site: Mapped["Site | None"] = relationship("Site", back_populates="incidents")  # type: ignore

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_by_user: Mapped["User"] = relationship("User", back_populates="incidents")
    remediation_plan: Mapped["RemediationPlan | None"] = relationship(  # type: ignore
        "RemediationPlan", back_populates="incident", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Incident {self.title!r} status={self.status}>"
