"""Graph engine — topology queries: neighbors, shortest path, impact analysis."""

from typing import Any

import networkx as nx

from backend.core.logging import get_logger

log = get_logger(__name__)


def find_device_id(G: nx.Graph, identifier: str) -> str | None:
    """
    Resolve a device by ID or hostname (case-insensitive).
    e.g. 'R1-CORE' → 'r1', 'r1' → 'r1'
    """
    identifier_lower = identifier.lower()
    # Exact node ID match
    if identifier_lower in G:
        return identifier_lower
    # Hostname match
    for node_id, attrs in G.nodes(data=True):
        hostname = attrs.get("hostname", "").lower()
        if hostname == identifier_lower or node_id == identifier_lower:
            return node_id
        # Partial match: "R1-CORE" matches node "r1" because r1 is prefix
        if identifier_lower.startswith(node_id) or node_id.startswith(identifier_lower.split("-")[0]):
            return node_id
    return None


def get_device_info(G: nx.Graph, device_id: str) -> dict[str, Any] | None:
    if device_id not in G:
        return None
    return {"device_id": device_id, **G.nodes[device_id]}


def get_neighbors(G: nx.Graph, device_id: str) -> list[dict[str, Any]]:
    """Return all direct neighbors with link and device attributes."""
    if device_id not in G:
        return []
    neighbors = []
    for nbr in G.neighbors(device_id):
        edge = G.edges[device_id, nbr]
        nbr_attrs = G.nodes[nbr]
        neighbors.append(
            {
                "device_id": nbr,
                "hostname": nbr_attrs.get("hostname", nbr),
                "vendor": nbr_attrs.get("vendor", "unknown"),
                "os": nbr_attrs.get("os", "unknown"),
                "role": nbr_attrs.get("role", "unknown"),
                "local_interface": edge.get("local_iface", ""),
                "remote_interface": edge.get("remote_iface", ""),
                "link_status": edge.get("status", "up"),
                "local_ip": edge.get("local_ip", ""),
            }
        )
    return neighbors


def get_shortest_path(G: nx.Graph, source: str, target: str) -> list[str]:
    """Return device IDs along shortest path, or [] if unreachable."""
    try:
        return nx.shortest_path(G, source=source, target=target, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def get_impact_analysis(G: nx.Graph, failed_device: str) -> dict[str, Any]:
    """
    Determine which devices lose core reachability if failed_device goes down.
    Core devices are those with role='core'.
    """
    core_devices = [n for n, d in G.nodes(data=True) if d.get("role") == "core"]

    G_without = G.copy()
    if failed_device in G_without:
        G_without.remove_node(failed_device)

    isolated = []
    for device in G_without.nodes:
        if not core_devices:
            break
        can_reach_core = any(
            nx.has_path(G_without, device, core)
            for core in core_devices
            if core in G_without
        )
        if not can_reach_core:
            isolated.append(
                {
                    "device_id": device,
                    "hostname": G_without.nodes[device].get("hostname", device),
                    "role": G_without.nodes[device].get("role", "unknown"),
                }
            )

    log.info(
        "impact_analysis",
        failed_device=failed_device,
        isolated_count=len(isolated),
    )
    return {
        "failed_device": failed_device,
        "failed_hostname": G.nodes[failed_device].get("hostname", failed_device) if failed_device in G else failed_device,
        "isolated_devices": isolated,
        "impact_count": len(isolated),
        "core_devices": core_devices,
    }


def get_all_devices(G: nx.Graph) -> list[dict[str, Any]]:
    return [{"device_id": n, **G.nodes[n]} for n in G.nodes]
