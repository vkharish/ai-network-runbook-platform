"""Feedback routes — only registered when FEEDBACK_ENABLED=true.

POST /incidents/{incident_id}/feedback     Submit helpful/not_helpful rating
GET  /incidents/{incident_id}/feedback     List feedback for an incident
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user
from backend.database.session import get_db
from backend.models.user_model import User
from backend.schemas.feedback_schema import FeedbackCreate, FeedbackResponse
from backend.services import feedback_service

router = APIRouter(tags=["Feedback"])


@router.post(
    "/incidents/{incident_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    incident_id: UUID,
    payload: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await feedback_service.create_feedback(db, incident_id, current_user.id, payload)


@router.get(
    "/incidents/{incident_id}/feedback",
    response_model=list[FeedbackResponse],
)
async def get_feedback(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await feedback_service.list_feedback_for_incident(db, incident_id)
