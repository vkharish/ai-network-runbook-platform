from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import (
    Role, create_access_token, create_refresh_token,
    decode_token, hash_password, verify_password,
)
from backend.database.session import get_db
from backend.models.user_model import User
from backend.schemas.user_schema import LoginRequest, TokenResponse, UserCreate, UserResponse
from backend.app.dependencies import get_current_user
from backend.core.logging import get_logger
from backend.services import audit_service

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email, full_name=payload.full_name,
        hashed_password=hash_password(payload.password), role=payload.role.value,
    )
    db.add(user)
    await db.flush()
    log.info("user_registered", user_id=str(user.id), email=user.email)
    await audit_service.log_action(
        db, user_id=user.id, action="register",
        resource_type="user", resource_id=str(user.id),
        metadata={"email": user.email},
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    log.info("user_login", user_id=str(user.id))
    await audit_service.log_action(
        db, user_id=user.id, action="login",
        resource_type="user", resource_id=str(user.id),
    )
    return {
        "access_token": create_access_token(user.id, Role(user.role)),
        "refresh_token": create_refresh_token(user.id),
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token_str: str, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        payload = decode_token(refresh_token_str)
        if payload.get("type") != "refresh":
            raise ValueError
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    from uuid import UUID
    result = await db.execute(select(User).where(User.id == UUID(payload["sub"])))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "access_token": create_access_token(user.id, Role(user.role)),
        "refresh_token": create_refresh_token(user.id),
    }


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# ---------------------------------------------------------------------------
# SSO / OIDC endpoints (enabled only when OIDC_ENABLED=true)
# ---------------------------------------------------------------------------

@router.get("/oidc/login")
async def oidc_login(request: Request) -> None:
    """Redirect browser to the configured IdP authorization endpoint."""
    from backend.core.config import settings
    from backend.core import oidc

    if not settings.oidc_enabled:
        raise HTTPException(status_code=501, detail="OIDC SSO is not enabled.")

    return await oidc.get_authorization_url(request)


@router.get("/oidc/callback", response_model=TokenResponse)
async def oidc_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle IdP callback: exchange code → upsert user → return platform JWT."""
    from backend.core.config import settings
    from backend.core import oidc
    from datetime import datetime, timezone

    if not settings.oidc_enabled:
        raise HTTPException(status_code=501, detail="OIDC SSO is not enabled.")

    try:
        userinfo = await oidc.exchange_code(request)
    except Exception as exc:
        log.warning("oidc_callback_error", error=str(exc))
        raise HTTPException(status_code=400, detail=f"OIDC exchange failed: {exc}")

    email: str = userinfo.get("email", "")
    sub: str = userinfo.get("sub", "")
    full_name: str = userinfo.get("name", email)
    groups: list[str] = userinfo.get("groups", [])

    if not email or not sub:
        raise HTTPException(status_code=400, detail="IdP did not return email or sub claim.")

    # Look up by OIDC sub first (stable), then fall back to email
    result = await db.execute(select(User).where(User.oidc_sub == sub))
    user = result.scalar_one_or_none()

    if user is None:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    role = oidc.map_groups_to_role(groups)

    if user is None:
        # First OIDC login — provision the user account
        user = User(
            email=email,
            full_name=full_name,
            hashed_password="",          # OIDC users have no local password
            role=role.value,
            is_active=True,
            oidc_sub=sub,
            oidc_provider=settings.oidc_discovery_url,
        )
        db.add(user)
        await db.flush()
        log.info("oidc_user_provisioned", email=email, role=role.value)
    else:
        # Existing user — sync fields
        if user.oidc_sub is None:
            user.oidc_sub = sub
            user.oidc_provider = settings.oidc_discovery_url
        if settings.oidc_sync_roles:
            user.role = role.value
        await db.flush()
        log.info("oidc_user_login", email=email)

    await audit_service.log_action(
        db, user_id=user.id, action="oidc_login",
        resource_type="user", resource_id=str(user.id),
        metadata={"provider": settings.oidc_discovery_url},
    )
    await db.commit()

    return {
        "access_token": create_access_token(user.id, Role(user.role)),
        "refresh_token": create_refresh_token(user.id),
    }
