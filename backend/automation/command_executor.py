"""Command executor — allow-listed command execution.

In development/simulation mode, delegates to the simulator.
In production, would delegate to Netmiko for real device execution.
All commands are validated against an allow-list before execution.
"""

from backend.core.config import settings, AppEnv
from backend.core.logging import get_logger
from backend.simulation.simulator import run_command as sim_run_command

log = get_logger(__name__)

# Only read-only show/display/get commands are permitted.
# This prevents any configuration or destructive commands from executing.
_ALLOWED_PREFIXES = (
    "show ",
    "get ",
    "display ",      # Huawei
    "run show ",     # Juniper
)

_BLOCKED_KEYWORDS = (
    "configure",
    "config t",
    "write",
    "delete",
    "erase",
    "reload",
    "shutdown",
    "no ",
    "clear ",        # could reset counters/sessions
    "debug ",        # can impact device performance
)


def is_command_allowed(command: str) -> bool:
    cmd_lower = command.lower().strip()

    # Must start with an allowed prefix
    if not any(cmd_lower.startswith(p) for p in _ALLOWED_PREFIXES):
        return False

    # Must not contain any blocked keywords
    if any(kw in cmd_lower for kw in _BLOCKED_KEYWORDS):
        return False

    return True


def execute(
    device: str,
    command: str,
    failure_state: dict | None = None,
) -> dict:
    """
    Execute a command against a device.

    - Validates command against allow-list.
    - In development/simulation: returns simulated output.
    - In production: would use Netmiko to connect to real device.

    Returns:
        {output, device, command, success, allowed, simulated}
    """
    if not is_command_allowed(command):
        log.warning("command_blocked", device=device, command=command)
        return {
            "output": f"Command not permitted: '{command}'. Only read-only show commands are allowed.",
            "device": device,
            "command": command,
            "success": False,
            "allowed": False,
            "simulated": True,
        }

    log.info("command_execute", device=device, command=command, env=settings.app_env.value)

    if settings.app_env != AppEnv.PRODUCTION:
        result = sim_run_command(device, command, failure_state=failure_state)
        result["allowed"] = True
        return result

    # Production path — real Netmiko execution (Week 4+ extension)
    # from backend.automation.netmiko_client import connect_and_run
    # return connect_and_run(device, command)
    return {
        "output": "Real device execution not configured.",
        "device": device,
        "command": command,
        "success": False,
        "allowed": True,
        "simulated": False,
    }
