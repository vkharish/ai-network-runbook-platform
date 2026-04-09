"""Simulator — executes simulated CLI commands, optionally applying failure state."""

from typing import Any

from backend.core.logging import get_logger
from backend.simulation.cli_loader import list_available_commands, load_cli_output

log = get_logger(__name__)


def run_command(
    device: str,
    command: str,
    failure_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute a simulated CLI command for a device.

    Args:
        device:        Device ID or hostname (e.g. 'r1', 'R1-CORE').
        command:       CLI command string (e.g. 'show bgp summary').
        failure_state: Optional dict from failure_simulator describing active failure.
                       If provided, output is modified to reflect failure.

    Returns:
        {output, device, command, simulated, success, failure_applied}
    """
    output = load_cli_output(device, command)

    if output is None:
        return {
            "output": f"% Unrecognized command or no simulated data for: {command}",
            "device": device,
            "command": command,
            "simulated": True,
            "success": False,
            "failure_applied": False,
        }

    failure_applied = False
    if failure_state and failure_state.get("success"):
        modified = _apply_failure_to_output(output, command, failure_state)
        if modified != output:
            output = modified
            failure_applied = True

    log.info(
        "simulator_command_run",
        device=device,
        command=command,
        failure_applied=failure_applied,
    )
    return {
        "output": output.strip(),
        "device": device,
        "command": command,
        "simulated": True,
        "success": True,
        "failure_applied": failure_applied,
    }


def get_device_summary(device: str) -> dict[str, Any]:
    """Return available commands and all CLI outputs for a device."""
    commands = list_available_commands(device)
    outputs: dict[str, str] = {}
    for cmd in commands:
        result = run_command(device, cmd)
        if result["success"]:
            outputs[cmd] = result["output"]
    return {"device": device, "available_commands": commands, "outputs": outputs}


# ------------------------------------------------------------------
# Private — modify static CLI output to reflect failure state
# ------------------------------------------------------------------

def _apply_failure_to_output(
    output: str,
    command: str,
    failure_state: dict[str, Any],
) -> str:
    cmd_lower = command.lower()
    failure_type = failure_state.get("type", "")

    if "bgp" in cmd_lower and failure_type == "bgp_session_drop":
        peer = failure_state.get("peer", "")
        if peer:
            lines = []
            for line in output.splitlines():
                if peer in line:
                    # Replace prefix count with "Idle" — mark session as down
                    import re
                    line = re.sub(r"\s+\d+\s*$", "    Idle", line.rstrip())
                lines.append(line)
            return "\n".join(lines)

    elif "interface" in cmd_lower and failure_type == "interface_down":
        affected_iface = failure_state.get("affected_interface", "")
        if affected_iface:
            output = output.replace(
                f"{affected_iface} is up, line protocol is up",
                f"{affected_iface} is down, line protocol is down",
            )
            # Juniper style
            output = output.replace(
                f"{affected_iface}: Physical link is Up",
                f"{affected_iface}: Physical link is Down",
            )

    elif "log" in cmd_lower and failure_type in ("bgp_session_drop", "interface_down", "ospf_adjacency_drop"):
        affected_device = failure_state.get("affected_device", "").upper()
        affected_iface = failure_state.get("affected_interface", "")
        failure_line = _generate_failure_log_line(failure_type, affected_device, affected_iface, failure_state)
        output = failure_line + "\n" + output

    return output


def _generate_failure_log_line(
    failure_type: str,
    device: str,
    iface: str,
    failure_state: dict[str, Any],
) -> str:
    if failure_type == "bgp_session_drop":
        peer = failure_state.get("peer", "unknown")
        return f"%BGP-5-ADJCHANGE: neighbor {peer} Down (Hold timer expired)"
    elif failure_type == "interface_down":
        return f"%LINK-3-UPDOWN: Interface {iface}, changed state to down"
    elif failure_type == "ospf_adjacency_drop":
        return f"%OSPF-5-ADJCHG: Process 1, Nbr on {iface} from FULL to DOWN (Dead timer expired)"
    return f"%SYS-5-CONFIG: Failure event on {device}"
