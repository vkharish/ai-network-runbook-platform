"""Site model for multi-tenant isolation.

A Site represents a physical or logical network domain (datacenter, campus, branch).
Devices, incidents, and users can be scoped to a site.

All site_id columns on other models are nullable — this model is only active when
MULTITENANCY_ENABLED=true. With the flag off, all records have site_id=NULL and
queries return all records regardless.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import AuditBase


class Site(AuditBase):
    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships (back-populated from Device, Incident, User when site_id is set)
    devices: Mapped[list["Device"]] = relationship(  # type: ignore
        "Device", back_populates="site", lazy="selectin"
    )
    incidents: Mapped[list["Incident"]] = relationship(  # type: ignore
        "Incident", back_populates="site", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Site {self.slug!r}>"
