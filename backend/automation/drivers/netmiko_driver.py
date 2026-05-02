"""NetmikoDriver — live SSH execution via Netmiko.

Supports:
  - Direct connection (no jump host)
  - Single jump host
  - Multi-hop jump host chain (unlimited hops)

Works on Windows, Linux, and macOS.

Jump host chain is stored in device.jump_hosts as an ordered list:
  []                          → direct connection
  [{host, port, user, pass}]  → one jump host
  [{...}, {...}]              → two hops (bastion → intermediate → target)
"""

import time
from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)


class NetmikoDriver:
    """Executes commands on real devices via Netmiko SSH."""

    def run_command(self, device: Any, command: str) -> str:
        """SSH into device and run a single command. Returns output string."""
        conn_params = self._build_conn_params(device)
        try:
            from netmiko import ConnectHandler
            log.info("netmiko_connecting", device=device.hostname,
                     host=device.host, device_type=device.device_type,
                     via_jumphosts=len(getattr(device, "jump_hosts", [])))
            with ConnectHandler(**conn_params) as conn:
                output = conn.send_command(command, read_timeout=30)
            log.info("netmiko_command_done", device=device.hostname, command=command[:60])
            return output
        except Exception as exc:
            log.error("netmiko_command_failed", device=device.hostname,
                      command=command, error=str(exc))
            raise
        finally:
            self._close_sock(conn_params)

    def load_all_outputs(self, device: Any) -> dict[str, str]:
        """Run all standard show commands in one SSH session."""
        commands = _standard_commands(device.os)
        outputs: dict[str, str] = {}
        hostname_prefix = device.hostname.lower().split("-")[0]
        conn_params = self._build_conn_params(device)

        try:
            from netmiko import ConnectHandler
            log.info("netmiko_session_start", device=device.hostname,
                     commands=len(commands),
                     via_jumphosts=len(getattr(device, "jump_hosts", [])))

            with ConnectHandler(**conn_params) as conn:
                for cmd in commands:
                    try:
                        output = conn.send_command(cmd, read_timeout=30)
                        key = f"{hostname_prefix}_{cmd.lower().replace(' ', '_').replace('/', '_')}"
                        outputs[key] = output
                        log.info("netmiko_command_done", device=device.hostname, command=cmd[:60])
                        time.sleep(0.5)
                    except Exception as exc:
                        log.warning("netmiko_command_skipped", command=cmd, error=str(exc))

            log.info("netmiko_session_done", device=device.hostname, collected=len(outputs))

        except Exception as exc:
            log.error("netmiko_session_failed", device=device.hostname, error=str(exc))
        finally:
            self._close_sock(conn_params)

        return outputs

    # ------------------------------------------------------------------
    # Jump host tunnel builder
    # ------------------------------------------------------------------

    def _build_conn_params(self, device: Any) -> dict:
        """Build Netmiko connection params, establishing jump host tunnel if needed."""
        from backend.core.security import decrypt_credential

        creds = device.credential
        if not creds:
            raise ValueError(f"No credentials configured for {device.hostname}")
        if not device.host:
            raise ValueError(f"No host/IP configured for {device.hostname}")

        password = decrypt_credential(creds.password_encrypted)
        jump_hosts = getattr(device, "jump_hosts", []) or []

        conn_params: dict = {
            "device_type": device.device_type,
            "host":        device.host,
            "port":        device.port,
            "username":    creds.username,
            "password":    password,
            "timeout":     30,
            "banner_timeout": 15,
            "conn_timeout":   10,
        }

        if jump_hosts:
            # Build a paramiko socket tunnel through the full hop chain
            # and pass it to Netmiko via the `sock` parameter.
            sock = self._build_tunnel(jump_hosts, device.host, device.port)
            conn_params["sock"] = sock

        return conn_params

    def _build_tunnel(self, jump_hosts: list[dict], target_host: str, target_port: int):
        """
        Build a paramiko channel tunnelled through each jump host in order.

        jump_hosts = [hop1, hop2, ...]  (first = entry point, last = closest to target)
        Returns a paramiko.Channel that Netmiko can use as a socket.

        Works on Windows — pure Python, no ProxyCommand needed.
        """
        import paramiko
        from backend.core.security import decrypt_credential

        transports = []  # track all transports so we can close them later

        try:
            # ── Connect to the first jump host directly ──────────────────
            hop = jump_hosts[0]
            hop_pass = decrypt_credential(hop["password_encrypted"])

            log.info("jumphost_connecting", hop=1, host=hop["host"])
            transport = paramiko.Transport((hop["host"], int(hop.get("port", 22))))
            transport.connect(username=hop["username"], password=hop_pass)
            transports.append(transport)

            # ── Chain through any additional jump hosts ───────────────────
            for i, hop in enumerate(jump_hosts[1:], start=2):
                hop_pass = decrypt_credential(hop["password_encrypted"])
                next_host = hop["host"]
                next_port = int(hop.get("port", 22))

                log.info("jumphost_connecting", hop=i, host=next_host)
                # Open a channel through the current transport to the next hop
                channel = transport.open_channel(
                    "direct-tcpip",
                    (next_host, next_port),
                    ("127.0.0.1", 0),
                )
                next_transport = paramiko.Transport(channel)
                next_transport.connect(username=hop["username"], password=hop_pass)
                transports.append(next_transport)
                transport = next_transport

            # ── Final hop: open channel to the target device ─────────────
            log.info("jumphost_tunnel_ready", target=target_host,
                     hops=len(jump_hosts))
            sock = transport.open_channel(
                "direct-tcpip",
                (target_host, target_port),
                ("127.0.0.1", 0),
            )
            # Attach transports to socket so _close_sock() can clean them up
            sock._jump_transports = transports
            return sock

        except Exception as exc:
            # Clean up any open transports on failure
            for t in reversed(transports):
                try: t.close()
                except: pass
            log.error("jumphost_tunnel_failed", target=target_host, error=str(exc))
            raise

    def _close_sock(self, conn_params: dict):
        """Close jump host transports after the Netmiko session ends."""
        sock = conn_params.get("sock")
        if sock and hasattr(sock, "_jump_transports"):
            for t in reversed(sock._jump_transports):
                try:
                    t.close()
                except Exception:
                    pass


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
    return cisco_commands
