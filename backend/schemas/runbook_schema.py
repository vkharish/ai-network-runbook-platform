from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RunbookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    original_name: str
    file_type: str
    file_size_bytes: int
    status: str
    chunk_count: int
    description: str | None
    tags: list[str] | None
    created_at: datetime


class RunbookUpdate(BaseModel):
    description: str | None = None
    tags: list[str] | None = None


class RunbookQueryRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    filter_tags: list[str] | None = None


class RunbookQueryResponse(BaseModel):
    query: str
    results: list[dict]
    answer: str
