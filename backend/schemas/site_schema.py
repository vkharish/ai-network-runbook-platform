"""Pydantic schemas for the Site (multi-tenant) API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class SiteCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None

    @field_validator("slug")
    @classmethod
    def slug_must_be_valid(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("slug must contain only lowercase letters, digits, and hyphens")
        return v


class SiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
