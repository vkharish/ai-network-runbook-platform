from fastapi import APIRouter, Depends, HTTPException, status
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
