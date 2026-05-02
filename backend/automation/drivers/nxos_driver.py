"""Cisco NX-OS driver — executes commands via NX-API (HTTP JSON).

NX-API is the preferred transport for NX-OS (Nexus switches):
- Supported on N3K, N5K, N7K, N9K, and vPC pairs
- Single HTTP session, supports command batching

NX-API must be enabled on the device:
    feature nxapi

NX-API endpoint: POST http(s)://{host}:{port}/ins
Auth: HTTP Basic (same credentials as SSH)

Falls back to SSH via NetmikoDriver if NX-API is unavailable.
"""

import time
from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)

_NXOS_COMMANDS = [
    "show version",
    "show interface status",
    "show bgp ipv4 unicast summary",
    "show ip ospf neighbors",
    "show logging last 100",
    "show ip route summary",
]


class NXOSDriver:
    """Executes commands on Cisco NX-OS via NX-API."""

    def run_command(self, device: Any, command: str) -> str:
        """Run a single NX-API command. Returns text output."""
        results = self._nxapi_request(device, [command])
        return results.get(command, "")

    def load_all_outputs(self, device: Any) -> dict[str, str]:
        """Run all standard NX-OS show commands in a single NX-API call."""
        hostname_prefix = device.hostname.lower().split("-")[0]
        t0 = time.perf_counter()

        outputs = self._nxapi_request(device, _NXOS_COMMANDS)
        result: dict[str, str] = {}
        for cmd, text in outputs.items():
            key = f"{hostname_prefix}_{cmd.lower().replace(' ', '_').replace('/', '_')}"
            result[key] = text

        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        log.info(
            "nxos_nxapi_done",
            device=device.hostname,
            commands=len(outputs),
            elapsed_ms=elapsed,
        )
        return result

    def _nxapi_request(self, device: Any, commands: list[str]) -> dict[str, str]:
        """Send NX-API request for a list of commands. Returns {command: output} dict."""
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx is required for NXOSDriver")

        from backend.core.vault import get_credential

        username, password = get_credential(device)
        url = self._nxapi_url(device)

        # NX-API accepts one command per request (type=cli_show) or multiple (type=cli_show_array)
        payload = {
            "ins_api": {
                "version": "1.0",
                "type": "cli_show_array",
                "chunk": "0",
                "sid": "sid",
                "input": " ; ".join(commands),
                "output_format": "text",
            }
        }

        try:
            resp = httpx.post(
                url,
                json=payload,
                auth=(username, password),
                timeout=30,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()

            # NX-API response: {"ins_api": {"outputs": {"output": [...]}}}
            ins_output = data.get("ins_api", {}).get("outputs", {}).get("output", [])
            if isinstance(ins_output, dict):
                ins_output = [ins_output]  # single command returns dict, not list

            result: dict[str, str] = {}
            for i, cmd in enumerate(commands):
                if i < len(ins_output):
                    body = ins_output[i].get("body", "")
                    # body is a string for text format
                    result[cmd] = body if isinstance(body, str) else str(body)
                else:
                    result[cmd] = ""
            return result

        except Exception as exc:
            log.error(
                "nxos_nxapi_failed",
                device=device.hostname,
                url=url,
                error=str(exc),
            )
            # Fallback to SSH via NetmikoDriver
            log.info("nxos_nxapi_fallback_ssh", device=device.hostname)
            from backend.automation.drivers.netmiko_driver import NetmikoDriver
            driver = NetmikoDriver()
            return {cmd: driver.run_command(device, cmd) for cmd in commands}

    def _nxapi_url(self, device: Any) -> str:
        port = getattr(device, "port", 80)
        scheme = "https" if port in (443, 8443) else "http"
        return f"{scheme}://{device.host}:{port}/ins"
