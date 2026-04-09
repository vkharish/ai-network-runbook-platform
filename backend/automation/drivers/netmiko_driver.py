"""NetmikoDriver — live SSH execution via Netmiko.

Works for ALL vendors — Cisco IOS/IOS-XE/IOS-XR, Juniper JunOS, Arista EOS,
Huawei, Nokia, etc. Vendor abstraction is done by the device_type field on
the Device model (e.g. "cisco_ios", "juniper_junos", "arista_eos").

Only activated when device.live_enabled = True.
"""

from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)


class NetmikoDriver:
    """Executes commands on real devices via Netmiko SSH."""

    def run_command(self, device: Any, command: str) -> str:
        """SSH into device and run a single command. Returns output string."""
        creds = device.credential
        if not creds:
            raise ValueError(f"No credentials configured for device {device.hostname}")
        if not device.host:
            raise ValueError(f"No host/IP configured for device {device.hostname}")

        try:
            from netmiko import ConnectHandler
            from backend.core.security import decrypt_credential

            password = decrypt_credential(creds.password_encrypted)

            conn_params = {
                "device_type": device.device_type,
                "host": device.host,
                "port": device.port,
                "username": creds.username,
                "password": password,
                "timeout": 30,
                "banner_timeout": 15,
                "conn_timeout": 10,
            }

            log.info(
                "netmiko_connecting",
                device=device.hostname,
                host=device.host,
                device_type=device.device_type,
            )

            with ConnectHandler(**conn_params) as conn:
                output = conn.send_command(command, read_timeout=30)

            log.info("netmiko_command_done", device=device.hostname, command=command[:60])
            return output

        except Exception as exc:
            log.error("netmiko_command_failed", device=device.hostname, command=command, error=str(exc))
            raise

    def load_all_outputs(self, device: Any) -> dict[str, str]:
        """Run standard show commands in a single SSH session to avoid rate-limiting."""
        import time
        commands = _standard_commands(device.os)
        outputs: dict[str, str] = {}
        hostname_prefix = device.hostname.lower().split("-")[0]

        try:
            from netmiko import ConnectHandler
            from backend.core.security import decrypt_credential

            creds = device.credential
            if not creds or not device.host:
                raise ValueError(f"No credentials/host for {device.hostname}")

            password = decrypt_credential(creds.password_encrypted)
            conn_params = {
                "device_type": device.device_type,
                "host": device.host,
                "port": device.port,
                "username": creds.username,
                "password": password,
                "timeout": 30,
                "banner_timeout": 15,
                "conn_timeout": 10,
            }

            log.info("netmiko_session_start", device=device.hostname, commands=len(commands))

            # Single SSH session for all commands — avoids repeated connection overhead
            with ConnectHandler(**conn_params) as conn:
                for cmd in commands:
                    try:
                        output = conn.send_command(cmd, read_timeout=30)
                        key = f"{hostname_prefix}_{cmd.lower().replace(' ', '_').replace('/', '_')}"
                        outputs[key] = output
                        log.info("netmiko_command_done", device=device.hostname, command=cmd[:60])
                        time.sleep(0.5)  # brief pause between commands
                    except Exception as exc:
                        log.warning("netmiko_command_skipped", command=cmd, error=str(exc))

            log.info("netmiko_session_done", device=device.hostname, collected=len(outputs))

        except Exception as exc:
            log.error("netmiko_session_failed", device=device.hostname, error=str(exc))

        return outputs


def _standard_commands(os: str) -> list[str]:
    """Return standard diagnostic commands for the given OS."""
    cisco_commands = [
        "show version",
        "show interfaces",
        "show bgp summary",
        "show ip ospf neighbor",
        "show logging",
        "show ip route summary",
    ]
    juniper_commands = [
        "show version",
        "show interfaces terse",
        "show bgp summary",
        "show ospf neighbor",
        "show log messages",
        "show route summary",
    ]
    os_lower = os.lower()
    if "junos" in os_lower or "juniper" in os_lower:
        return juniper_commands
    return cisco_commands  # default to Cisco for all others
