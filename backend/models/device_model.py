"""Device inventory model — stores device connection details for live polling."""

import uuid
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database.base import AuditBase


class Device(AuditBase):
    __tablename__ = "devices"

    hostname: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    vendor: Mapped[str] = mapped_column(String(32), nullable=False)          # cisco, juniper, arista...
    os: Mapped[str] = mapped_column(String(32), nullable=False)              # ios-xe, junos, eos...
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)     # netmiko device_type string
    host: Mapped[str | None] = mapped_column(String(128), nullable=True)     # IP/FQDN — null = simulator only
    port: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    topology_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # maps to graph node id

    credential: Mapped["DeviceCredential | None"] = relationship(
        "DeviceCredential", back_populates="device", uselist=False, cascade="all, delete-orphan"
    )


class DeviceCredential(AuditBase):
    __tablename__ = "device_credentials"

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)   # Fernet encrypted

    device: Mapped["Device"] = relationship("Device", back_populates="credential")
