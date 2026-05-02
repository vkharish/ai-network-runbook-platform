"""Schemas for Device inventory API."""

from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator


class JumpHostInput(BaseModel):
    """One hop in the jump host chain — password in plaintext, encrypted before storage."""
    host: str
    port: int = 22
    username: str
    password: str   # plaintext — encrypted at rest


class JumpHostStored(BaseModel):
    """Stored representation — password_encrypted instead of password."""
    host: str
    port: int = 22
    username: str
    password_encrypted: str


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
    # Jump host chain — ordered list, first = entry point closest to your machine
    jump_hosts: list[JumpHostInput] = []


class DeviceCredentialSet(BaseModel):
    username: str
    password: str   # plaintext — encrypted before storage


class DeviceUpdate(BaseModel):
    display_name: str | None = None
    host: str | None = None
    port: int | None = None
    live_enabled: bool | None = None
    jump_hosts: list[JumpHostInput] | None = None


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
    jump_host_count: int = 0   # how many hops configured
