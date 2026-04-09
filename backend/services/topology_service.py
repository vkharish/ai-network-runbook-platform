"""Topology service — CRUD + graph operations for network topologies."""

import uuid
from typing import Any

import yaml
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.digital_twin.failure_simulator import apply_named_scenario, get_available_scenarios
from backend.digital_twin.graph_engine import (
    find_device_id,
    get_all_devices,
    get_device_info,
    get_impact_analysis,
    get_neighbors,
    get_shortest_path,
)
from backend.digital_twin.topology_builder import build_graph_from_yaml, graph_from_dict, graph_to_dict
from backend.models.topology_model import Topology, TopologyStatus

log = get_logger(__name__)


async def upload_topology(
    name: str,
    raw_yaml: str,
    description: str | None,
    set_as_default: bool,
    db: AsyncSession,
) -> Topology:
    """Parse YAML, build graph, store topology in DB."""
    # Validate YAML is parseable
    try:
        yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}")

    # Build graph and serialize
    G = build_graph_from_yaml(raw_yaml)
    graph_data = graph_to_dict(G)

    # If setting as default, unset all others first
    if set_as_default:
        await db.execute(
            update(Topology)
            .where(Topology.is_default == True)  # noqa: E712
            .values(is_default=False)
        )

    topology = Topology(
        name=name,
        description=description or graph_data.get("description", ""),
        raw_yaml=raw_yaml,
        graph_data=graph_data,
        status=TopologyStatus.ACTIVE.value,
        is_default=set_as_default,
    )
    db.add(topology)
    await db.flush()

    log.info(
        "topology_uploaded",
        topology_id=str(topology.id),
        name=name,
        nodes=len(graph_data.get("nodes", [])),
        edges=len(graph_data.get("edges", [])),
        is_default=set_as_default,
    )
    return topology


async def get_active_topology(db: AsyncSession) -> Topology | None:
    result = await db.execute(
        select(Topology)
        .where(Topology.is_default == True)  # noqa: E712
        .where(Topology.status == TopologyStatus.ACTIVE.value)
    )
    return result.scalar_one_or_none()


async def list_topologies(db: AsyncSession) -> list[Topology]:
    result = await db.execute(
        select(Topology)
        .where(Topology.status == TopologyStatus.ACTIVE.value)
        .order_by(Topology.created_at.desc())
    )
    return list(result.scalars().all())


async def get_topology_by_id(topology_id: str, db: AsyncSession) -> Topology | None:
    result = await db.execute(
        select(Topology).where(Topology.id == uuid.UUID(topology_id))
    )
    return result.scalar_one_or_none()


def query_neighbors(topology: Topology, device_identifier: str) -> dict[str, Any]:
    if not topology.graph_data:
        raise ValueError("Topology has no graph data.")
    G = graph_from_dict(topology.graph_data)
    device_id = find_device_id(G, device_identifier)
    if not device_id:
        raise ValueError(f"Device '{device_identifier}' not found in topology.")
    device_info = get_device_info(G, device_id)
    neighbors = get_neighbors(G, device_id)
    return {
        "device": device_info,
        "neighbors": neighbors,
        "neighbor_count": len(neighbors),
    }


def query_impact(topology: Topology, device_identifier: str) -> dict[str, Any]:
    if not topology.graph_data:
        raise ValueError("Topology has no graph data.")
    G = graph_from_dict(topology.graph_data)
    device_id = find_device_id(G, device_identifier)
    if not device_id:
        raise ValueError(f"Device '{device_identifier}' not found in topology.")
    return get_impact_analysis(G, device_id)


def query_path(topology: Topology, source: str, target: str) -> dict[str, Any]:
    if not topology.graph_data:
        raise ValueError("Topology has no graph data.")
    G = graph_from_dict(topology.graph_data)
    src_id = find_device_id(G, source)
    tgt_id = find_device_id(G, target)
    if not src_id:
        raise ValueError(f"Source device '{source}' not found.")
    if not tgt_id:
        raise ValueError(f"Target device '{target}' not found.")
    path = get_shortest_path(G, src_id, tgt_id)
    path_detail = [get_device_info(G, d) for d in path]
    return {"source": src_id, "target": tgt_id, "path": path, "path_detail": path_detail, "hops": len(path) - 1}


def simulate_failure(topology: Topology, scenario_name: str) -> dict[str, Any]:
    if not topology.graph_data:
        raise ValueError("Topology has no graph data.")
    G = graph_from_dict(topology.graph_data)
    available = get_available_scenarios(G)
    if scenario_name not in available:
        raise ValueError(
            f"Scenario '{scenario_name}' not found. Available: {list(available.keys())}"
        )
    G_failed, failure_report = apply_named_scenario(G, scenario_name)

    # Run impact analysis on the post-failure graph
    failed_device = available[scenario_name].get("affected_device", "")
    impact = get_impact_analysis(G_failed, failed_device) if failed_device else {}

    return {
        "failure_report": failure_report,
        "impact_analysis": impact,
        "available_scenarios": list(available.keys()),
        "post_failure_graph": graph_to_dict(G_failed),
    }


def get_topology_summary(topology: Topology) -> dict[str, Any]:
    if not topology.graph_data:
        return {"nodes": [], "edges": [], "devices": []}
    G = graph_from_dict(topology.graph_data)
    return {
        "name": topology.name,
        "devices": get_all_devices(G),
        "device_count": G.number_of_nodes(),
        "link_count": G.number_of_edges(),
        "available_scenarios": list(get_available_scenarios(G).keys()),
    }
