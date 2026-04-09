"""Topology API routes — upload, query, neighbor lookup, failure simulation."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, require_role
from backend.core.logging import get_logger
from backend.core.security import Role
from backend.database.session import get_db
from backend.models.user_model import User
from backend.schemas.simulation_schema import FailureSimulationRequest, FailureSimulationResponse
from backend.schemas.topology_schema import TopologyCreate, TopologyResponse
from backend.services import topology_service

log = get_logger(__name__)
router = APIRouter(prefix="/topology", tags=["Topology"])


@router.post(
    "/upload",
    response_model=TopologyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_topology(
    payload: TopologyCreate,
    set_as_default: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(Role.ENGINEER)),
):
    try:
        topology = await topology_service.upload_topology(
            name=payload.name,
            raw_yaml=payload.raw_yaml,
            description=payload.description,
            set_as_default=set_as_default,
            db=db,
        )
        await db.commit()
        return topology
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/", response_model=list[TopologyResponse])
async def list_topologies(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await topology_service.list_topologies(db)


@router.get("/active")
async def get_active_topology(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    topology = await topology_service.get_active_topology(db)
    if not topology:
        raise HTTPException(status_code=404, detail="No active topology found. Upload one first.")
    return topology_service.get_topology_summary(topology)


@router.get("/{topology_id}")
async def get_topology(
    topology_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    topology = await topology_service.get_topology_by_id(topology_id, db)
    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found.")
    return topology_service.get_topology_summary(topology)


@router.get("/{topology_id}/device/{device_id}/neighbors")
async def get_device_neighbors(
    topology_id: str,
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    topology = await topology_service.get_topology_by_id(topology_id, db)
    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found.")
    try:
        return topology_service.query_neighbors(topology, device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{topology_id}/device/{device_id}/impact")
async def get_device_impact(
    topology_id: str,
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    topology = await topology_service.get_topology_by_id(topology_id, db)
    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found.")
    try:
        return topology_service.query_impact(topology, device_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{topology_id}/path")
async def get_path(
    topology_id: str,
    source: str,
    target: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    topology = await topology_service.get_topology_by_id(topology_id, db)
    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found.")
    try:
        return topology_service.query_path(topology, source, target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{topology_id}/simulate", response_model=FailureSimulationResponse)
async def simulate_failure(
    topology_id: str,
    payload: FailureSimulationRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(Role.ENGINEER)),
):
    topology = await topology_service.get_topology_by_id(topology_id, db)
    if not topology:
        raise HTTPException(status_code=404, detail="Topology not found.")
    try:
        return topology_service.simulate_failure(topology, payload.scenario_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
