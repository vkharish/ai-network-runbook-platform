"""CLI loader — maps (device, command) → simulated output from simulator/*.txt files."""

from pathlib import Path

from backend.core.logging import get_logger

log = get_logger(__name__)

SIMULATOR_DIR = Path(__file__).resolve().parent.parent.parent / "simulator"

# Canonical command → file stem mapping
_COMMAND_MAP: dict[str, str] = {
    "show bgp summary": "show_bgp_summary",
    "show ip bgp summary": "show_bgp_summary",
    "show bgp neighbors": "show_bgp_summary",
    "show ip bgp neighbors": "show_bgp_summary",
    "show interface": "show_interface",
    "show interfaces": "show_interface",
    "show ip interface brief": "show_interface",
    "show logging": "show_logs",
    "show log": "show_logs",
    "show logs": "show_logs",
}


def normalize_device(device: str) -> str:
    """'R1-CORE' → 'r1',  'R2-DIST' → 'r2',  'r1' → 'r1'"""
    return device.lower().split("-")[0].split("_")[0]


def load_cli_output(device: str, command: str) -> str | None:
    """
    Return the simulated CLI output for a device+command pair, or None if not found.
    Matching is case-insensitive and tries both exact and keyword-based lookup.
    """
    device_dir = SIMULATOR_DIR / normalize_device(device)
    if not device_dir.exists():
        log.warning("simulator_device_not_found", device=device, path=str(device_dir))
        return None

    cmd_lower = command.lower().strip()

    # Exact match
    stem = _COMMAND_MAP.get(cmd_lower)
    if stem:
        path = device_dir / f"{stem}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")

    # Keyword fuzzy match
    for pattern, file_stem in _COMMAND_MAP.items():
        if any(word in cmd_lower for word in pattern.split() if len(word) > 3):
            path = device_dir / f"{file_stem}.txt"
            if path.exists():
                return path.read_text(encoding="utf-8", errors="replace")

    log.warning("simulator_command_not_found", device=device, command=command)
    return None


def list_available_commands(device: str) -> list[str]:
    """Return the list of canonical commands available for a device."""
    device_dir = SIMULATOR_DIR / normalize_device(device)
    if not device_dir.exists():
        return []

    stem_to_cmd = {v: k for k, v in _COMMAND_MAP.items()}
    commands: list[str] = []
    seen_stems: set[str] = set()

    for txt in sorted(device_dir.glob("*.txt")):
        if txt.stem not in seen_stems:
            seen_stems.add(txt.stem)
            commands.append(stem_to_cmd.get(txt.stem, txt.stem.replace("_", " ")))

    return commands


def list_available_devices() -> list[str]:
    """Return all device IDs that have simulator data."""
    if not SIMULATOR_DIR.exists():
        return []
    return [d.name for d in sorted(SIMULATOR_DIR.iterdir()) if d.is_dir()]
