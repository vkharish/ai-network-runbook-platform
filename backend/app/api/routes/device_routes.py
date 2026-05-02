"""Device inventory CRUD routes."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, require_role
from backend.core.security import Role
from backend.database.session import get_db
from backend.models.device_model import Device, DeviceCredential
from backend.models.user_model import User
from backend.schemas.device_schema import DeviceCreate, DeviceCredentialSet, DeviceResponse, DeviceUpdate
from backend.core.security import encrypt_credential
from backend.services import audit_service

router = APIRouter(prefix="/devices", tags=["Devices"])


def _encrypt_jump_hosts(jump_hosts: list) -> list[dict]:
    """Encrypt passwords for all jump host hops before DB storage."""
    encrypted = []
    for hop in jump_hosts:
        # hop may be JumpHostInput (schema) or dict
        if hasattr(hop, "model_dump"):
            hop_dict = hop.model_dump()
        else:
            hop_dict = dict(hop)
        plaintext = hop_dict.pop("password", None)
        hop_dict["password_encrypted"] = encrypt_credential(plaintext) if plaintext else ""
        encrypted.append(hop_dict)
    return encrypted


def _to_response(device: Device, has_credentials: bool = False) -> DeviceResponse:
    jump_hosts = getattr(device, "jump_hosts", None) or []
    return DeviceResponse(
        id=device.id,
        hostname=device.hostname,
        display_name=device.display_name,
        vendor=device.vendor,
        os=device.os,
        device_type=device.device_type,
        host=device.host,
        port=device.port,
        live_enabled=device.live_enabled,
        topology_node_id=device.topology_node_id,
        has_credentials=has_credentials,
        jump_host_count=len(jump_hosts),
    )


@router.get("/", response_model=list[DeviceResponse])
async def list_devices(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[DeviceResponse]:
    result = await db.execute(
        select(Device).options(selectinload(Device.credential)).order_by(Device.hostname)
    )
    return [_to_response(d, has_credentials=d.credential is not None) for d in result.scalars().all()]


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ENGINEER)),
) -> DeviceResponse:
    data = payload.model_dump()
    # Encrypt jump host passwords before storing
    data["jump_hosts"] = _encrypt_jump_hosts(data.get("jump_hosts", []))
    device = Device(**data)
    db.add(device)
    await db.flush()
    await audit_service.log_action(
        db, user_id=current_user.id, action="device_create",
        resource_type="device", resource_id=str(device.id),
        metadata={"hostname": device.hostname},
    )
    return _to_response(device, has_credentials=False)


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> DeviceResponse:
    result = await db.execute(
        select(Device).options(selectinload(Device.credential)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _to_response(device, has_credentials=device.credential is not None)


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: UUID,
    payload: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ENGINEER)),
) -> DeviceResponse:
    result = await db.execute(
        select(Device).options(selectinload(Device.credential)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    updates = payload.model_dump(exclude_none=True)
    if "jump_hosts" in updates:
        updates["jump_hosts"] = _encrypt_jump_hosts(updates["jump_hosts"])
    for field, value in updates.items():
        setattr(device, field, value)
    await db.flush()
    await audit_service.log_action(
        db, user_id=current_user.id, action="device_update",
        resource_type="device", resource_id=str(device_id),
        metadata=payload.model_dump(exclude_none=True),
    )
    return _to_response(device, has_credentials=device.credential is not None)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
) -> None:
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.delete(device)
    await audit_service.log_action(
        db, user_id=current_user.id, action="device_delete",
        resource_type="device", resource_id=str(device_id),
    )


@router.post("/{device_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def set_credentials(
    device_id: UUID,
    payload: DeviceCredentialSet,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
) -> None:
    """Set or replace SSH credentials for a device (password is encrypted at rest)."""
    result = await db.execute(
        select(Device).options(selectinload(Device.credential)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Delete existing credential if present
    if device.credential:
        await db.delete(device.credential)
        await db.flush()

    cred = DeviceCredential(
        device_id=device_id,
        username=payload.username,
        password_encrypted=encrypt_credential(payload.password),
    )
    db.add(cred)
    await audit_service.log_action(
        db, user_id=current_user.id, action="device_credentials_set",
        resource_type="device", resource_id=str(device_id),
    )


@router.post("/{device_id}/test", response_model=dict)
async def test_connection(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ENGINEER)),
) -> dict:
    """Test SSH connectivity to a live device."""
    result = await db.execute(
        select(Device).options(selectinload(Device.credential)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.live_enabled:
        return {"success": False, "message": "Device is not in live mode (live_enabled=false)"}
    if not device.host:
        return {"success": False, "message": "No host/IP configured"}

    try:
        from backend.automation.drivers.netmiko_driver import NetmikoDriver
        driver = NetmikoDriver()
        output = driver.run_command(device, "show version")
        return {"success": True, "message": "Connection successful", "output_preview": output[:200]}
    except Exception as exc:
        return {"success": False, "message": str(exc)}
