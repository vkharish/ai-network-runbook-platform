"""Simulation routes — execute simulated CLI commands against network devices."""

from fastapi import APIRouter, Depends, HTTPException

from backend.app.dependencies import get_current_user, require_role
from backend.automation.command_executor import execute, is_command_allowed
from backend.core.logging import get_logger
from backend.core.security import Role
from backend.models.user_model import User
from backend.schemas.simulation_schema import CommandRequest, CommandResponse
from backend.simulation.cli_loader import list_available_commands, list_available_devices

log = get_logger(__name__)
router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.post("/run-command", response_model=CommandResponse)
async def run_command(
    payload: CommandRequest,
    _: User = Depends(require_role(Role.ENGINEER)),
):
    """
    Execute a simulated CLI command on a network device.
    Commands are validated against the allow-list before execution.
    Only read-only show commands are permitted.
    """
    result = execute(
        device=payload.device,
        command=payload.command,
        failure_state=None,
    )
    return CommandResponse(**result)


@router.get("/devices")
async def list_devices(_: User = Depends(get_current_user)):
    """List all devices that have simulated CLI data."""
    devices = list_available_devices()
    return {"devices": devices, "count": len(devices)}


@router.get("/devices/{device}/commands")
async def list_commands(
    device: str,
    _: User = Depends(get_current_user),
):
    """List available commands for a specific device."""
    commands = list_available_commands(device)
    if not commands:
        raise HTTPException(status_code=404, detail=f"No simulator data for device: {device}")
    return {
        "device": device,
        "commands": commands,
        "count": len(commands),
    }


@router.get("/allowed-commands")
async def get_allowed_commands(_: User = Depends(get_current_user)):
    """Return the allow-list policy for command execution."""
    return {
        "policy": "read-only",
        "allowed_prefixes": ["show ", "get ", "display ", "run show "],
        "blocked_keywords": ["configure", "write", "delete", "erase", "reload", "shutdown", "no ", "clear ", "debug "],
        "note": "Only non-destructive read commands are permitted.",
    }
