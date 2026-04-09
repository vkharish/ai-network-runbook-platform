"""Schemas for Device inventory API."""

from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DeviceCreate(BaseModel):
    hostname: str
    display_name: str
    vendor: str
    os: str
    device_type: str
    host: str | None = None
    port: int = 22
    live_enabled: bool = False
    topology_node_id: str | None = None


class DeviceCredentialSet(BaseModel):
    username: str
    password: str   # plaintext — encrypted before storage


class DeviceUpdate(BaseModel):
    display_name: str | None = None
    host: str | None = None
    port: int | None = None
    live_enabled: bool | None = None


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hostname: str
    display_name: str
    vendor: str
    os: str
    device_type: str
    host: str | None
    port: int
    live_enabled: bool
    topology_node_id: str | None
    has_credentials: bool = False
