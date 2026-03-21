from enum import Enum

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import AuditBase


class TopologyStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Topology(AuditBase):
    __tablename__ = "topologies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=TopologyStatus.ACTIVE.value
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<Topology {self.name!r}>"
