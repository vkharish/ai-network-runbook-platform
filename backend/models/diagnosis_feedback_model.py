"""DiagnosisFeedback — stores helpful/not_helpful ratings on AI diagnoses.

Each feedback record ties an incident to one or more runbook chunk IDs that were
cited in the diagnosis, together with the user's thumbs-up/down rating. The
feedback reranker uses these ratings to adjust future RAG retrieval scores.
"""

import uuid
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import AuditBase


class FeedbackRating(str, Enum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


class DiagnosisFeedback(AuditBase):
    __tablename__ = "diagnosis_feedback"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rating: Mapped[str] = mapped_column(String(20), nullable=False)  # FeedbackRating
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # List of ChromaDB chunk IDs cited in the diagnosis
    cited_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Was this feedback used to update reranker weights?
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    incident: Mapped["Incident"] = relationship("Incident")  # type: ignore

    def __repr__(self) -> str:
        return f"<DiagnosisFeedback incident={self.incident_id} rating={self.rating}>"
