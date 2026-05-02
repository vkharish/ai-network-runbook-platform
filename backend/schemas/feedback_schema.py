import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from backend.models.diagnosis_feedback_model import FeedbackRating


class FeedbackCreate(BaseModel):
    rating: FeedbackRating
    comment: str | None = None
    cited_chunk_ids: list[str] | None = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    rated_by: uuid.UUID | None
    rating: str
    comment: str | None
    cited_chunk_ids: list | None
    applied: bool
    created_at: datetime
