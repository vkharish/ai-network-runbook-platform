from uuid import UUID
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, ConfigDict
from backend.models.incident_model import IncidentSeverity, IncidentStatus


class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=512)
    description: str = Field(..., min_length=10)
    severity: IncidentSeverity = IncidentSeverity.P3
    affected_device: str | None = None
    affected_protocol: str | None = None


class IncidentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None
    affected_device: str | None = None
    affected_protocol: str | None = None


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str
    status: str
    severity: str
    affected_device: str | None
    affected_protocol: str | None
    root_cause: str | None
    ai_report: dict[str, Any] | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
