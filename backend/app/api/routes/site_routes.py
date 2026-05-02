"""Site management routes — only registered when MULTITENANCY_ENABLED=true.

GET    /sites/          List all sites
POST   /sites/          Create site (ADMIN only)
GET    /sites/{id}      Get site detail
PATCH  /sites/{id}      Update site (ADMIN only)
DELETE /sites/{id}      Delete site (ADMIN only)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.dependencies import get_current_user, require_role
from backend.core.security import Role
from backend.database.session import get_db
from backend.models.user_model import User
from backend.schemas.site_schema import SiteCreate, SiteResponse, SiteUpdate
from backend.services import site_service

router = APIRouter(prefix="/sites", tags=["Sites"])


@router.get("/", response_model=list[SiteResponse])
async def list_sites(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list:
    return await site_service.list_sites(db)


@router.post("/", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(
    payload: SiteCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(Role.ADMIN)),
):
    return await site_service.create_site(db, payload)


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return await site_service.get_site(db, site_id)


@router.patch("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: UUID,
    payload: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(Role.ADMIN)),
):
    return await site_service.update_site(db, site_id, payload)


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(Role.ADMIN)),
) -> None:
    await site_service.delete_site(db, site_id)
