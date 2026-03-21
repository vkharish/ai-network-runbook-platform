from uuid import UUID
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class TopologyCreate(BaseModel):
    name: str
    description: str | None = None
    raw_yaml: str


class TopologyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str | None
    status: str
    is_default: bool
    graph_data: dict[str, Any] | None
    created_at: datetime
