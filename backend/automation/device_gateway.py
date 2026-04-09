"""DeviceGateway — single entry point for all device CLI operations.

Usage:
    gateway = DeviceGateway()
    outputs = gateway.load_all_outputs("R4-ACCESS")   # returns dict[str, str]
    output  = gateway.run_command("R4-ACCESS", "show bgp summary")

The gateway picks the driver automatically:
  - device.live_enabled = False → SimulatorDriver (default, safe)
  - device.live_enabled = True  → NetmikoDriver (live SSH, all vendors)

InvestigationAgent uses this instead of _load_cli_outputs() directly.
"""

from backend.automation.device_registry import SyntheticDevice, get_device_sync
from backend.automation.drivers.simulator import SimulatorDriver
from backend.core.logging import get_logger

log = get_logger(__name__)

_simulator_driver = SimulatorDriver()


def _get_driver(device):
    if device.live_enabled:
        from backend.automation.drivers.netmiko_driver import NetmikoDriver
        return NetmikoDriver()
    return _simulator_driver


class DeviceGateway:
    """Vendor-agnostic device interface. Plug-and-play: swap driver via live_enabled flag."""

    def load_all_outputs(self, hostname: str | None, db=None) -> dict[str, str]:
        """Load all CLI outputs for a device. Used by InvestigationAgent."""
        device = get_device_sync(hostname) if hostname else SyntheticDevice(hostname="unknown")
        driver = _get_driver(device)
        log.info(
            "gateway_load_outputs",
            hostname=hostname,
            driver=driver.__class__.__name__,
            live=device.live_enabled,
        )
        return driver.load_all_outputs(device)

    def run_command(self, hostname: str, command: str, db=None) -> str:
        """Run a single command on a device."""
        device = get_device_sync(hostname)
        driver = _get_driver(device)
        log.info(
            "gateway_run_command",
            hostname=hostname,
            command=command[:60],
            driver=driver.__class__.__name__,
            live=device.live_enabled,
        )
        return driver.run_command(device, command)
