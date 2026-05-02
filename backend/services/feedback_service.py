"""Feedback service — record and retrieve diagnosis feedback."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.diagnosis_feedback_model import DiagnosisFeedback
from backend.schemas.feedback_schema import FeedbackCreate


async def create_feedback(
    db: AsyncSession,
    incident_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: FeedbackCreate,
) -> DiagnosisFeedback:
    fb = DiagnosisFeedback(
        id=uuid.uuid4(),
        incident_id=incident_id,
        rated_by=user_id,
        rating=payload.rating.value,
        comment=payload.comment,
        cited_chunk_ids=payload.cited_chunk_ids,
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return fb


async def list_feedback_for_incident(
    db: AsyncSession,
    incident_id: uuid.UUID,
) -> list[DiagnosisFeedback]:
    result = await db.execute(
        select(DiagnosisFeedback)
        .where(DiagnosisFeedback.incident_id == incident_id)
        .order_by(DiagnosisFeedback.created_at.desc())
    )
    return result.scalars().all()
