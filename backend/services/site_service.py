"""Site service — CRUD for multi-tenant site isolation."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.models.site_model import Site
from backend.schemas.site_schema import SiteCreate, SiteUpdate

log = get_logger(__name__)


async def create_site(db: AsyncSession, payload: SiteCreate) -> Site:
    result = await db.execute(select(Site).where(Site.slug == payload.slug))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Site with slug '{payload.slug}' already exists.",
        )
    site = Site(**payload.model_dump())
    db.add(site)
    await db.commit()
    await db.refresh(site)
    log.info("site_created", site_id=str(site.id), slug=site.slug)
    return site


async def list_sites(db: AsyncSession) -> list[Site]:
    result = await db.execute(select(Site).order_by(Site.name))
    return list(result.scalars().all())


async def get_site(db: AsyncSession, site_id: uuid.UUID) -> Site:
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found.")
    return site


async def update_site(db: AsyncSession, site_id: uuid.UUID, payload: SiteUpdate) -> Site:
    site = await get_site(db, site_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(site, field, value)
    await db.commit()
    await db.refresh(site)
    return site


async def delete_site(db: AsyncSession, site_id: uuid.UUID) -> None:
    site = await get_site(db, site_id)
    await db.delete(site)
    await db.commit()
    log.info("site_deleted", site_id=str(site_id))


def apply_site_filter(query, model_class, current_user):
    """Apply site_id filter to a query when multitenancy is enabled.

    When MULTITENANCY_ENABLED=false → returns query unchanged (all records visible).
    When MULTITENANCY_ENABLED=true:
      - User has no site_id → sees all records (admin/global user)
      - User has site_id   → sees only records in their site
    """
    from backend.core.config import settings

    if not settings.multitenancy_enabled:
        return query

    user_site_id = getattr(current_user, "site_id", None)
    if user_site_id is None:
        return query  # global admin — no filter

    return query.where(model_class.site_id == user_site_id)
