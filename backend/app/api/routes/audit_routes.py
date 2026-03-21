"""Audit log routes — admin-only view of system actions."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, require_role
from backend.core.security import Role
from backend.database.session import get_db
from backend.models.user_model import User
from backend.services.audit_service import list_audit_logs

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get(
    "/",
    dependencies=[Depends(require_role(Role.ADMIN))],
    summary="List audit log entries (admin only)",
)
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[dict]:
    entries = await list_audit_logs(
        db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
    )
    return [
        {
            "id": str(e.id),
            "user_id": str(e.user_id) if e.user_id else None,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "metadata": e.metadata_,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
