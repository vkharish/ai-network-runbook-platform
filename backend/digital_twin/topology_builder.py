"""Parse topology YAML → NetworkX graph and serialize back to JSON-compatible dict."""

from typing import Any

import networkx as nx
import yaml

from backend.core.logging import get_logger

log = get_logger(__name__)


def build_graph_from_yaml(yaml_str: str) -> nx.Graph:
    """
    Parse topology YAML and build a NetworkX undirected graph.
    Nodes = devices, Edges = physical links.
    """
    data = yaml.safe_load(yaml_str)
    G = nx.Graph()
    G.graph["name"] = data.get("name", "unnamed")
    G.graph["description"] = data.get("description", "")
    G.graph["failure_scenarios"] = data.get("failure_scenarios", {})

    devices: dict[str, Any] = data.get("devices", {})

    # Add nodes
    for device_id, attrs in devices.items():
        G.add_node(
            device_id,
            hostname=attrs.get("hostname", device_id),
            vendor=attrs.get("vendor", "unknown"),
            os=attrs.get("os", "unknown"),
            model=attrs.get("model", "unknown"),
            role=attrs.get("role", "unknown"),
            loopback=attrs.get("loopback", ""),
            protocols=attrs.get("protocols", {}),
        )

    # Add edges from interface definitions (deduplicated)
    added: set[tuple[str, str]] = set()
    for device_id, attrs in devices.items():
        for iface in attrs.get("interfaces", []):
            neighbor = iface.get("neighbor")
            if not neighbor or neighbor not in devices:
                continue
            key = tuple(sorted([device_id, neighbor]))
            if key in added:
                continue
            added.add(key)
            G.add_edge(
                device_id,
                neighbor,
                local_iface=iface.get("name", ""),
                local_ip=iface.get("ip", ""),
                remote_iface=iface.get("neighbor_iface", ""),
                status=iface.get("status", "up"),
                weight=1,
            )

    log.info(
        "topology_graph_built",
        name=G.graph["name"],
        nodes=G.number_of_nodes(),
        edges=G.number_of_edges(),
    )
    return G


def graph_to_dict(G: nx.Graph) -> dict[str, Any]:
    """Serialize graph to a JSON-compatible dict for JSONB storage."""
    return {
        "name": G.graph.get("name", ""),
        "description": G.graph.get("description", ""),
        "failure_scenarios": G.graph.get("failure_scenarios", {}),
        "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
        "edges": [
            {"source": u, "target": v, **G.edges[u, v]}
            for u, v in G.edges
        ],
    }


def graph_from_dict(d: dict[str, Any]) -> nx.Graph:
    """Reconstruct a NetworkX graph from a serialized dict (read from JSONB)."""
    G = nx.Graph()
    G.graph["name"] = d.get("name", "")
    G.graph["description"] = d.get("description", "")
    G.graph["failure_scenarios"] = d.get("failure_scenarios", {})

    for node in d.get("nodes", []):
        node = dict(node)
        node_id = node.pop("id")
        G.add_node(node_id, **node)

    for edge in d.get("edges", []):
        edge = dict(edge)
        u = edge.pop("source")
        v = edge.pop("target")
        G.add_edge(u, v, **edge)

    return G
