"""Failure simulator — inject pre-defined or custom failure scenarios into the topology graph."""

from typing import Any

import networkx as nx

from backend.core.logging import get_logger

log = get_logger(__name__)


def inject_failure(G: nx.Graph, scenario: dict[str, Any]) -> tuple[nx.Graph, dict[str, Any]]:
    """
    Apply a failure scenario to a COPY of the graph.
    Returns (modified_graph, failure_report).

    Supported types:
      - interface_down       → mark edge as down, weight=9999
      - bgp_session_drop     → mark BGP neighbor state as idle
      - ospf_adjacency_drop  → mark OSPF adjacency as down on edge
    """
    G_failed = G.copy()
    failure_type = scenario.get("type", "")
    affected_device = scenario.get("affected_device", "")
    affected_iface = scenario.get("affected_interface", "")

    report: dict[str, Any] = {
        "scenario": scenario.get("description", "Unknown failure"),
        "type": failure_type,
        "affected_device": affected_device,
        "affected_interface": affected_iface,
        "changes": [],
        "success": False,
    }

    if failure_type == "interface_down":
        changed = False
        for u, v, data in list(G_failed.edges(data=True)):
            local_match = u == affected_device and data.get("local_iface") == affected_iface
            remote_match = v == affected_device and data.get("remote_iface") == affected_iface
            if local_match or remote_match:
                G_failed.edges[u, v]["status"] = "down"
                G_failed.edges[u, v]["weight"] = 9999
                report["changes"].append(
                    f"Link {u}↔{v} (interface {affected_iface}) set to DOWN"
                )
                changed = True
        report["success"] = changed

    elif failure_type == "bgp_session_drop":
        peer = scenario.get("peer", "")
        if affected_device in G_failed:
            node_data = G_failed.nodes[affected_device]
            protocols = node_data.get("protocols", {})
            bgp = protocols.get("bgp", {})
            for nbr in bgp.get("neighbors", []):
                if nbr.get("peer") == peer:
                    nbr["state"] = "idle"
                    report["changes"].append(
                        f"BGP session on {affected_device} to peer {peer} → Idle"
                    )
                    report["success"] = True

    elif failure_type == "ospf_adjacency_drop":
        if affected_device in G_failed:
            for nbr_id in G_failed.neighbors(affected_device):
                edge = G_failed.edges[affected_device, nbr_id]
                if (
                    edge.get("local_iface") == affected_iface
                    or edge.get("remote_iface") == affected_iface
                ):
                    G_failed.edges[affected_device, nbr_id]["ospf_state"] = "down"
                    report["changes"].append(
                        f"OSPF adjacency {affected_device}↔{nbr_id} dropped"
                    )
                    report["success"] = True

    log.info(
        "failure_injected",
        type=failure_type,
        device=affected_device,
        changes=len(report["changes"]),
    )
    return G_failed, report


def get_available_scenarios(G: nx.Graph) -> dict[str, Any]:
    """Return the pre-defined failure scenarios from the topology."""
    return G.graph.get("failure_scenarios", {})


def apply_named_scenario(G: nx.Graph, scenario_name: str) -> tuple[nx.Graph, dict[str, Any]]:
    """Apply a named scenario from the topology's failure_scenarios section."""
    scenarios = get_available_scenarios(G)
    if scenario_name not in scenarios:
        return G.copy(), {
            "success": False,
            "error": f"Scenario '{scenario_name}' not found. Available: {list(scenarios.keys())}",
        }
    scenario = scenarios[scenario_name]
    scenario["name"] = scenario_name
    return inject_failure(G, scenario)
