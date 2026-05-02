"""NetBox REST API client for device inventory sync.

Reads devices from NetBox DCIM and upserts them into the local Device table.
All imports of httpx are inside methods — no top-level optional deps.

NetBox API: GET /api/dcim/devices/?limit=500&offset=0
Requires a read-only API token from NetBox Admin → API Tokens.
"""

from __future__ import annotations

from backend.core.logging import get_logger

log = get_logger(__name__)

# Maps NetBox platform slug → netmiko device_type string
_PLATFORM_TO_DEVICE_TYPE: dict[str, str] = {
    "ios":       "cisco_ios",
    "ios-xe":    "cisco_xe",
    "ios-xr":    "cisco_xr",
    "nxos":      "cisco_nxos",
    "nx-os":     "cisco_nxos",
    "eos":       "arista_eos",
    "junos":     "juniper_junos",
    "srlinux":   "nokia_srl",
    "sros":      "nokia_sros",
}

# Maps NetBox manufacturer slug → vendor name
_MFR_TO_VENDOR: dict[str, str] = {
    "cisco":    "cisco",
    "juniper":  "juniper",
    "arista":   "arista",
    "nokia":    "nokia",
    "palo-alto-networks": "palo_alto",
    "f5":       "f5",
}


def _platform_to_device_type(platform_slug: str) -> str:
    return _PLATFORM_TO_DEVICE_TYPE.get(platform_slug.lower(), "cisco_xe")


def _parse_ip(address: str | None) -> str | None:
    """Strip prefix length from NetBox IP (e.g. '10.0.0.1/24' → '10.0.0.1')."""
    if not address:
        return None
    return address.split("/")[0]


class NetBoxClient:
    """Async REST client for the NetBox DCIM API."""

    def __init__(self, url: str, token: str) -> None:
        self._base = url.rstrip("/") + "/api"
        self._headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get_devices(self, limit: int = 500, offset: int = 0) -> dict:
        """GET /dcim/devices/ — one page."""
        import httpx  # already in requirements

        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(
                f"{self._base}/dcim/devices/",
                params={"limit": limit, "offset": offset},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_all_devices(self) -> list[dict]:
        """Auto-paginate through all devices in NetBox."""
        all_devices: list[dict] = []
        offset = 0
        limit = 500
        while True:
            page = await self.get_devices(limit=limit, offset=offset)
            results: list[dict] = page.get("results", [])
            all_devices.extend(results)
            if not page.get("next"):
                break
            offset += limit
        log.info("netbox_devices_fetched", count=len(all_devices))
        return all_devices

    def parse_device(self, nb_device: dict) -> dict:
        """Convert a NetBox device dict into fields matching our Device model."""
        platform_slug = (
            (nb_device.get("platform") or {}).get("slug") or ""
        )
        mfr_slug = (
            ((nb_device.get("device_type") or {}).get("manufacturer") or {}).get("slug") or ""
        )
        primary_ip4 = (nb_device.get("primary_ip4") or {}).get("address")

        return {
            "hostname":     nb_device.get("name", ""),
            "display_name": nb_device.get("display", nb_device.get("name", "")),
            "vendor":       _MFR_TO_VENDOR.get(mfr_slug.lower(), mfr_slug or "unknown"),
            "os":           platform_slug or "unknown",
            "device_type":  _platform_to_device_type(platform_slug),
            "host":         _parse_ip(primary_ip4),
            "live_enabled": False,           # always safe default — ops team enables manually
        }

    @staticmethod
    def from_settings() -> "NetBoxClient | None":
        from backend.core.config import settings

        if not settings.netbox_enabled:
            return None
        if not settings.netbox_url or not settings.netbox_token:
            log.warning("netbox_misconfigured", reason="NETBOX_URL or NETBOX_TOKEN not set")
            return None
        return NetBoxClient(settings.netbox_url, settings.netbox_token)
