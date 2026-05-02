import uuid
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import AuditBase


class RunbookStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    PENDING_REVIEW = "pending_review"  # Phase 3: auto-generated runbooks awaiting approval


class Runbook(AuditBase):
    __tablename__ = "runbooks"

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=RunbookStatus.PENDING.value, index=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    chroma_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Phase 3: auto-generated runbooks (nullable — only set when RUNBOOK_AUTOGEN_ENABLED=true)
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    def __repr__(self) -> str:
        return f"<Runbook {self.original_name!r} status={self.status}>"
