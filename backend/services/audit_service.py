"""Audit service — fire-and-forget action logging for RBAC compliance."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.models.audit_log_model import AuditLog

log = get_logger(__name__)


async def log_action(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist an audit log entry.  Never raises — failures are logged only."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_=metadata,
        )
        db.add(entry)
        await db.commit()
        log.info(
            "audit_logged",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=str(user_id) if user_id else None,
        )
    except Exception as exc:
        log.error("audit_log_failed", action=action, error=str(exc))


async def list_audit_logs(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100,
    user_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
) -> list[AuditLog]:
    """Return audit log entries with optional filters (admin only)."""
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if action:
        q = q.where(AuditLog.action == action)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())
