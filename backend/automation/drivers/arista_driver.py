"""Arista EOS driver — executes commands via eAPI (HTTPS JSON-RPC).

Arista eAPI is preferred over SSH for EOS devices because:
- Single HTTP connection vs SSH session setup overhead
- Batched command execution (all commands in one request)
- Structured JSON output available (using format="text" for compatibility)
- No SSH key management required when eAPI is enabled

eAPI must be enabled on the device:
    management api http-commands
      no shutdown

eAPI endpoint: POST https://{host}:{port}/command-api
Auth: HTTP Basic (same credentials as SSH fallback)
"""

import time
from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)

_EAPI_COMMANDS = [
    "show version",
    "show interfaces status",
    "show ip bgp summary",
    "show ip ospf neighbor",
    "show logging last 100",
    "show ip route summary",
]


class AristaDriver:
    """Executes commands on Arista EOS devices via eAPI."""

    def run_command(self, device: Any, command: str) -> str:
        """Run a single eAPI command. Returns text output string."""
        results = self._eapi_request(device, [command])
        if results:
            return results.get(command, "")
        return ""

    def load_all_outputs(self, device: Any) -> dict[str, str]:
        """Run all standard EOS show commands in a single eAPI request."""
        hostname_prefix = device.hostname.lower().split("-")[0]
        t0 = time.perf_counter()

        outputs = self._eapi_request(device, _EAPI_COMMANDS)
        result: dict[str, str] = {}
        for cmd, text in outputs.items():
            key = f"{hostname_prefix}_{cmd.lower().replace(' ', '_').replace('/', '_')}"
            result[key] = text

        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        log.info(
            "arista_eapi_done",
            device=device.hostname,
            commands=len(outputs),
            elapsed_ms=elapsed,
        )
        return result

    def _eapi_request(self, device: Any, commands: list[str]) -> dict[str, str]:
        """Send a batch eAPI request. Returns {command: text_output} dict."""
        try:
            import httpx  # already in requirements — not an optional dep
        except ImportError:
            raise RuntimeError("httpx is required for AristaDriver")

        from backend.core.vault import get_credential

        username, password = get_credential(device)
        url = self._eapi_url(device)

        payload = {
            "jsonrpc": "2.0",
            "method": "runCmds",
            "params": {
                "version": 1,
                "cmds": commands,
                "format": "text",
            },
            "id": "arista-driver-1",
        }

        try:
            resp = httpx.post(
                url,
                json=payload,
                auth=(username, password),
                timeout=30,
                verify=False,  # self-signed certs common in lab/enterprise
            )
            resp.raise_for_status()
            data = resp.json()
            results_list: list[dict] = data.get("result", [])
            return {
                cmd: (results_list[i].get("output", "") if i < len(results_list) else "")
                for i, cmd in enumerate(commands)
            }
        except Exception as exc:
            log.error(
                "arista_eapi_failed",
                device=device.hostname,
                url=url,
                error=str(exc),
            )
            # Fallback to SSH via NetmikoDriver
            log.info("arista_eapi_fallback_ssh", device=device.hostname)
            from backend.automation.drivers.netmiko_driver import NetmikoDriver
            driver = NetmikoDriver()
            return {cmd: driver.run_command(device, cmd) for cmd in commands}

    def _eapi_url(self, device: Any) -> str:
        port = getattr(device, "port", 443)
        scheme = "https" if port == 443 else "http"
        return f"{scheme}://{device.host}:{port}/command-api"
