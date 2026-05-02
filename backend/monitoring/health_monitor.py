"""Health monitor — detects anomalies in device CLI output.

Runs read-only commands on live devices (or simulator), parses output
for known failure signatures, and returns a list of detected anomalies.

Each anomaly has:
  - device: hostname
  - protocol: bgp | ospf | interface | system
  - severity: P1 | P2 | P3
  - description: human-readable finding
  - raw_evidence: relevant CLI snippet
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.core.logging import get_logger

log = get_logger(__name__)

# Commands to run per device for health checks
HEALTH_CHECK_COMMANDS = [
    "show interfaces",
    "show bgp summary",
    "show ip ospf neighbor",
]


@dataclass
class Anomaly:
    device: str
    protocol: str
    severity: str
    description: str
    raw_evidence: str


# ---------------------------------------------------------------------------
# Signature matchers
# ---------------------------------------------------------------------------

def _check_bgp(device: str, output: str) -> list[Anomaly]:
    anomalies = []

    # BGP session not established
    for match in re.finditer(
        r"(\d{1,3}(?:\.\d{1,3}){3})\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+(Active|Idle|Connect)",
        output,
    ):
        peer_ip = match.group(1)
        state = match.group(2)
        anomalies.append(Anomaly(
            device=device,
            protocol="bgp",
            severity="P2",
            description=f"BGP peer {peer_ip} is in {state} state (not Established)",
            raw_evidence=match.group(0)[:200],
        ))

    return anomalies


def _check_interfaces(device: str, output: str) -> list[Anomaly]:
    anomalies = []

    # Interface line protocol down
    for match in re.finditer(
        r"([\w/\-\.]+) is (?:administratively )?down, line protocol is down",
        output,
        re.IGNORECASE,
    ):
        iface = match.group(1)
        anomalies.append(Anomaly(
            device=device,
            protocol="interface",
            severity="P2",
            description=f"Interface {iface} is down",
            raw_evidence=match.group(0)[:200],
        ))

    # High input/output error rate
    for match in re.finditer(r"(\d+) input errors", output):
        errors = int(match.group(1))
        if errors > 1000:
            anomalies.append(Anomaly(
                device=device,
                protocol="interface",
                severity="P3",
                description=f"High input error count: {errors}",
                raw_evidence=match.group(0),
            ))

    return anomalies


def _check_ospf(device: str, output: str) -> list[Anomaly]:
    anomalies = []

    # No OSPF neighbors
    if "show ip ospf neighbor" in output.lower() and not re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", output):
        anomalies.append(Anomaly(
            device=device,
            protocol="ospf",
            severity="P2",
            description="No OSPF neighbors found",
            raw_evidence=output[:200],
        ))

    # OSPF neighbor in EXSTART or EXCHANGE state (stuck)
    for match in re.finditer(
        r"(\d{1,3}(?:\.\d{1,3}){3})\s+\S+\s+(EXSTART|EXCHANGE|DOWN)",
        output,
    ):
        neighbor = match.group(1)
        state = match.group(2)
        anomalies.append(Anomaly(
            device=device,
            protocol="ospf",
            severity="P2",
            description=f"OSPF neighbor {neighbor} stuck in {state} state",
            raw_evidence=match.group(0)[:200],
        ))

    return anomalies


def analyze_output(device: str, command: str, output: str) -> list[Anomaly]:
    """Parse CLI output and return detected anomalies."""
    cmd = command.lower()
    if "bgp" in cmd:
        return _check_bgp(device, output)
    if "interface" in cmd:
        return _check_interfaces(device, output)
    if "ospf" in cmd:
        return _check_ospf(device, output)
    return []


def run_health_checks(device, gateway_fn) -> list[Anomaly]:
    """Run all health check commands against a device and collect anomalies."""
    all_anomalies: list[Anomaly] = []
    for command in HEALTH_CHECK_COMMANDS:
        try:
            output = gateway_fn(device, command)
            anomalies = analyze_output(device.hostname, command, output)
            all_anomalies.extend(anomalies)
            if anomalies:
                log.info(
                    "health_check_anomaly_found",
                    device=device.hostname,
                    command=command,
                    count=len(anomalies),
                )
        except Exception as exc:
            log.warning("health_check_command_failed", device=device.hostname, command=command, error=str(exc))
    return all_anomalies
