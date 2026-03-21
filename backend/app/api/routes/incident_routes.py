from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, require_role
from backend.core.security import Role
from backend.database.session import get_db
from backend.models.incident_model import Incident, IncidentStatus
from backend.models.user_model import User
from backend.schemas.incident_schema import IncidentCreate, IncidentResponse, IncidentUpdate
from backend.core.logging import get_logger
from backend.services.audit_service import log_action
from backend.tasks.diagnosis_task import run_diagnosis_task

log = get_logger(__name__)
router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    skip: int = 0, limit: int = 50, status_filter: str | None = None,
    db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user),
) -> list[Incident]:
    q = select(Incident).offset(skip).limit(limit).order_by(Incident.created_at.desc())
    if status_filter:
        q = q.where(Incident.status == status_filter)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post("/", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Incident:
    incident = Incident(**payload.model_dump(), created_by=current_user.id)
    db.add(incident)
    await db.flush()
    log.info("incident_created", incident_id=str(incident.id))
    return incident


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user),
) -> Incident:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: UUID, payload: IncidentUpdate, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ENGINEER)),
) -> Incident:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(incident, field, value)
    await db.flush()
    return incident


@router.post("/{incident_id}/diagnose", response_model=IncidentResponse)
async def trigger_diagnosis(
    incident_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(Role.ENGINEER)),
) -> Incident:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.status not in (IncidentStatus.OPEN.value, IncidentStatus.AWAITING_INPUT.value):
        raise HTTPException(status_code=400, detail=f"Cannot diagnose in status: {incident.status}")
    incident.status = IncidentStatus.DIAGNOSING.value
    await db.flush()
    run_diagnosis_task.delay(str(incident_id))
    log.info("diagnosis_triggered", incident_id=str(incident_id))
    await log_action(
        db,
        user_id=current_user.id,
        action="trigger_diagnosis",
        resource_type="incident",
        resource_id=str(incident_id),
    )
    return incident
