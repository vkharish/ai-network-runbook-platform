"""NetBox → Device Inventory Sync

Pulls devices from your NetBox instance and registers them in the
runbook platform's device inventory via the REST API.

Usage:
    python3 scripts/sync_netbox.py

Environment variables (or pass as args):
    NETBOX_URL       https://netbox.youroffice.com
    NETBOX_TOKEN     your-netbox-api-token
    RUNBOOK_URL      http://localhost:8000
    RUNBOOK_EMAIL    admin@youroffice.com
    RUNBOOK_PASSWORD yourpassword

Options:
    --dry-run        Print what would be synced without making changes
    --site           Filter by NetBox site name (e.g. "LAB-01")
    --role           Filter by device role (e.g. "router", "switch")
    --tag            Filter by NetBox tag (e.g. "managed")
    --live           Register devices with live_enabled=True (real SSH)
"""

import argparse
import os
import sys
import json
import requests
from urllib.parse import urljoin

# ── NetBox platform → our fields mapping ─────────────────────────────────────
# Maps NetBox platform slug → (vendor, os, netmiko_device_type)
PLATFORM_MAP = {
    # Cisco
    "ios":          ("cisco", "ios",    "cisco_ios"),
    "ios-xe":       ("cisco", "ios-xe", "cisco_xe"),
    "ios-xr":       ("cisco", "ios-xr", "cisco_xr"),
    "nxos":         ("cisco", "nxos",   "cisco_nxos"),
    "nxos-ssh":     ("cisco", "nxos",   "cisco_nxos_ssh"),
    # Juniper
    "junos":        ("juniper", "junos", "juniper_junos"),
    "junos-evo":    ("juniper", "junos", "juniper_junos"),
    # Arista
    "eos":          ("arista", "eos",   "arista_eos"),
    # Palo Alto
    "panos":        ("paloalto", "panos", "paloalto_panos"),
    # Generic fallback
    "linux":        ("linux",   "linux", "linux"),
}

DEFAULT_VENDOR      = "cisco"
DEFAULT_OS          = "ios-xe"
DEFAULT_DEVICE_TYPE = "cisco_xe"


def get_platform(platform_slug: str | None):
    if not platform_slug:
        return DEFAULT_VENDOR, DEFAULT_OS, DEFAULT_DEVICE_TYPE
    slug = platform_slug.lower()
    return PLATFORM_MAP.get(slug, (DEFAULT_VENDOR, DEFAULT_OS, DEFAULT_DEVICE_TYPE))


# ── NetBox client ─────────────────────────────────────────────────────────────

class NetBoxClient:
    def __init__(self, url: str, token: str):
        self.base = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def get_devices(self, site=None, role=None, tag=None, status="active"):
        """Fetch all active devices from NetBox with optional filters."""
        params = {"status": status, "limit": 1000}
        if site:
            params["site"] = site
        if role:
            params["role"] = role
        if tag:
            params["tag"] = tag

        devices = []
        url = f"{self.base}/api/dcim/devices/"

        while url:
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            devices.extend(data["results"])
            url = data.get("next")
            params = {}  # pagination uses full URL

        return devices

    def get_primary_ip(self, device: dict) -> str | None:
        """Extract primary management IP (strip prefix length)."""
        ip_obj = device.get("primary_ip") or device.get("primary_ip4")
        if not ip_obj:
            return None
        address = ip_obj.get("address", "")
        return address.split("/")[0] if address else None


# ── Runbook platform client ───────────────────────────────────────────────────

class RunbookClient:
    def __init__(self, url: str, email: str, password: str):
        self.base = url.rstrip("/")
        self.session = requests.Session()
        self._login(email, password)

    def _login(self, email: str, password: str):
        resp = self.session.post(
            f"{self.base}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.session.headers["Authorization"] = f"Bearer {token}"
        print(f"✓ Logged in to runbook platform")

    def get_existing_devices(self) -> dict[str, dict]:
        """Returns existing devices keyed by hostname."""
        resp = self.session.get(f"{self.base}/api/v1/devices/")
        if resp.status_code == 404:
            return {}  # endpoint not yet registered
        resp.raise_for_status()
        return {d["hostname"]: d for d in resp.json()}

    def create_device(self, payload: dict) -> dict:
        resp = self.session.post(f"{self.base}/api/v1/devices/", json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_device(self, device_id: str, payload: dict) -> dict:
        resp = self.session.patch(f"{self.base}/api/v1/devices/{device_id}", json=payload)
        resp.raise_for_status()
        return resp.json()


# ── Sync logic ────────────────────────────────────────────────────────────────

def build_device_payload(nb_device: dict, nb_client: NetBoxClient, live: bool) -> dict:
    """Map a NetBox device dict → runbook platform device payload."""
    hostname  = nb_device["name"]
    platform  = nb_device.get("platform")
    platform_slug = platform["slug"] if platform else None
    vendor, os_name, device_type = get_platform(platform_slug)

    # Prefer primary IP; fall back to None (simulator mode)
    host = nb_client.get_primary_ip(nb_device)

    # Build display name from site + hostname
    site = nb_device.get("site")
    site_name = site["name"] if site else ""
    display_name = f"{site_name} — {hostname}".strip(" —")

    # Map NetBox role to topology_node_id (optional)
    role = nb_device.get("role") or nb_device.get("device_role")
    role_slug = role["slug"] if role else None

    return {
        "hostname":         hostname,
        "display_name":     display_name,
        "vendor":           vendor,
        "os":               os_name,
        "device_type":      device_type,
        "host":             host,
        "port":             22,
        "live_enabled":     live and host is not None,
        "topology_node_id": role_slug,
    }


def sync(args):
    print(f"\n{'='*60}")
    print(f"  NetBox → Runbook Platform Device Sync")
    print(f"{'='*60}")
    print(f"  NetBox:   {args.netbox_url}")
    print(f"  Runbook:  {args.runbook_url}")
    print(f"  Dry run:  {args.dry_run}")
    print(f"  Live SSH: {args.live}")
    if args.site:  print(f"  Site:     {args.site}")
    if args.role:  print(f"  Role:     {args.role}")
    if args.tag:   print(f"  Tag:      {args.tag}")
    print()

    # Connect to NetBox
    nb = NetBoxClient(args.netbox_url, args.netbox_token)

    # Fetch devices from NetBox
    print("Fetching devices from NetBox...")
    nb_devices = nb.get_devices(site=args.site, role=args.role, tag=args.tag)
    print(f"  Found {len(nb_devices)} devices in NetBox\n")

    if not nb_devices:
        print("No devices found. Check your filters.")
        return

    if args.dry_run:
        print("DRY RUN — no changes will be made\n")
        for d in nb_devices:
            payload = build_device_payload(d, nb, args.live)
            host_str = payload["host"] or "no IP (simulator)"
            live_str = "LIVE SSH" if payload["live_enabled"] else "simulator"
            print(f"  {'[+]'} {payload['hostname']:30s} {payload['vendor']:10s} {payload['os']:10s} {host_str:20s} [{live_str}]")
        print(f"\nWould sync {len(nb_devices)} devices.")
        return

    # Connect to runbook platform
    rb = RunbookClient(args.runbook_url, args.runbook_email, args.runbook_password)
    existing = rb.get_existing_devices()
    print(f"  Existing devices in runbook platform: {len(existing)}\n")

    created = updated = skipped = errors = 0

    for nb_device in nb_devices:
        hostname = nb_device["name"]
        try:
            payload = build_device_payload(nb_device, nb, args.live)
            host_str  = payload["host"] or "no IP"
            live_str  = "LIVE" if payload["live_enabled"] else "sim"

            if hostname in existing:
                # Update existing device
                device_id = existing[hostname]["id"]
                rb.update_device(device_id, payload)
                print(f"  [↺] {hostname:30s} {payload['vendor']:10s} {host_str:20s} [{live_str}] — updated")
                updated += 1
            else:
                # Create new device
                rb.create_device(payload)
                print(f"  [+] {hostname:30s} {payload['vendor']:10s} {host_str:20s} [{live_str}] — created")
                created += 1

        except Exception as exc:
            print(f"  [✗] {hostname:30s} ERROR: {exc}")
            errors += 1

    print(f"\n{'='*60}")
    print(f"  Sync complete")
    print(f"  Created:  {created}")
    print(f"  Updated:  {updated}")
    print(f"  Errors:   {errors}")
    print(f"{'='*60}\n")

    if errors:
        print("⚠  Some devices failed. Check errors above.")
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sync devices from NetBox to runbook platform")

    parser.add_argument("--netbox-url",      default=os.getenv("NETBOX_URL"),      help="NetBox base URL")
    parser.add_argument("--netbox-token",    default=os.getenv("NETBOX_TOKEN"),    help="NetBox API token")
    parser.add_argument("--runbook-url",     default=os.getenv("RUNBOOK_URL", "http://localhost:8000"), help="Runbook platform URL")
    parser.add_argument("--runbook-email",   default=os.getenv("RUNBOOK_EMAIL"),   help="Runbook admin email")
    parser.add_argument("--runbook-password",default=os.getenv("RUNBOOK_PASSWORD"),help="Runbook admin password")

    parser.add_argument("--site",    default=None,  help="Filter by NetBox site name")
    parser.add_argument("--role",    default=None,  help="Filter by device role slug (e.g. router)")
    parser.add_argument("--tag",     default=None,  help="Filter by NetBox tag")
    parser.add_argument("--live",    action="store_true", help="Enable live SSH for devices that have a primary IP")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without making changes")

    # Jump host chain — pass one or more times for multi-hop
    # Format: username:password@host:port
    # Example: --jump-host netops:pass@bastion.corp:22 --jump-host netops:pass@mgmt-switch:22
    parser.add_argument("--jump-host", action="append", dest="jump_hosts", default=[],
                        metavar="user:pass@host:port",
                        help="Jump host (repeat for multi-hop). Format: user:pass@host:port")

    args = parser.parse_args()

    # Validate required args
    missing = []
    if not args.netbox_url:      missing.append("--netbox-url / NETBOX_URL")
    if not args.netbox_token:    missing.append("--netbox-token / NETBOX_TOKEN")
    if not args.runbook_email:   missing.append("--runbook-email / RUNBOOK_EMAIL")
    if not args.runbook_password:missing.append("--runbook-password / RUNBOOK_PASSWORD")

    if missing and not args.dry_run:
        print("Missing required arguments:")
        for m in missing: print(f"  {m}")
        sys.exit(1)

    sync(args)


if __name__ == "__main__":
    main()
