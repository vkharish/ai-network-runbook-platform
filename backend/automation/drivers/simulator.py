"""SimulatorDriver — reads pre-recorded CLI output from simulator/*.txt files.

This is the DEFAULT driver (live_enabled=False). Behavior is identical to the
original InvestigationAgent._load_cli_outputs() implementation.
"""

from pathlib import Path
from typing import Any

from backend.core.logging import get_logger

log = get_logger(__name__)

# Matches InvestigationAgent.SIMULATOR_DIR exactly
SIMULATOR_DIR = Path(__file__).resolve().parent.parent.parent.parent / "simulator"


class SimulatorDriver:
    """Reads *.txt files from simulator/{device}/ directory."""

    def run_command(self, device: Any, command: str) -> str:
        """Map a show command to its simulator file content."""
        outputs = self.load_all_outputs(device)
        # Try to match command to a file (e.g. "show bgp summary" → show_bgp_summary)
        cmd_key = command.lower().strip().replace(" ", "_").replace("/", "_")
        hostname = device.hostname.lower().split("-")[0].split("_")[0]
        full_key = f"{hostname}_{cmd_key}"
        # Try exact match first, then partial match
        if full_key in outputs:
            return outputs[full_key]
        for key, val in outputs.items():
            if cmd_key in key:
                return val
        return f"[simulator] No output found for command: {command}"

    def load_all_outputs(self, device: Any) -> dict[str, str]:
        """Load all *.txt files for the device — identical to _load_cli_outputs()."""
        if not SIMULATOR_DIR.exists():
            log.warning("simulator_dir_missing", path=str(SIMULATOR_DIR))
            return {}

        hostname = device.hostname if device else None
        if hostname:
            normalized = hostname.lower().split("-")[0].split("_")[0]
            device_dir = SIMULATOR_DIR / normalized
            dirs = [device_dir] if device_dir.exists() else list(SIMULATOR_DIR.iterdir())
        else:
            dirs = list(SIMULATOR_DIR.iterdir())

        outputs: dict[str, str] = {}
        for d in dirs:
            if not d.is_dir():
                continue
            for txt in sorted(d.glob("*.txt")):
                key = f"{d.name}_{txt.stem}"
                outputs[key] = txt.read_text(encoding="utf-8", errors="replace")

        log.info("simulator_outputs_loaded", device=hostname, files=list(outputs.keys()))
        return outputs
