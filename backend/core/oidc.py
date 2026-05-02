"""OIDC / SSO support via authlib.

Provides authorization code flow for enterprise IdPs (Okta, Azure AD, Google Workspace).
Local JWT auth continues to work unchanged when OIDC_ENABLED=false.

Usage in auth_routes.py:
    GET /auth/oidc/login     → redirect to IdP
    GET /auth/oidc/callback  → exchange code → return platform JWT pair
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.core.logging import get_logger
from backend.core.security import Role

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

log = get_logger(__name__)

_oauth = None  # type: ignore[assignment]


def configure_oidc(app: "FastAPI") -> None:
    """Register the OIDC provider with authlib. Call from main.py lifespan."""
    global _oauth

    from backend.core.config import settings

    if not settings.oidc_enabled:
        return

    try:
        from authlib.integrations.starlette_client import OAuth  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "authlib is not installed. Add 'authlib>=1.3.0' to requirements.txt."
        ) from exc

    _oauth = OAuth()
    _oauth.register(
        name="oidc",
        server_metadata_url=settings.oidc_discovery_url,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        client_kwargs={
            "scope": "openid email profile",
            "token_endpoint_auth_method": "client_secret_post",
        },
    )
    log.info("oidc_configured", discovery_url=settings.oidc_discovery_url)


async def get_authorization_url(request: "Request") -> str:
    """Return the IdP authorization URL to redirect the browser to."""
    from backend.core.config import settings

    if _oauth is None:
        raise RuntimeError("OIDC not configured. Set OIDC_ENABLED=true.")

    redirect_uri = settings.oidc_redirect_uri
    return await _oauth.oidc.authorize_redirect(request, redirect_uri)


async def exchange_code(request: "Request") -> dict:
    """Exchange the authorization code for ID token claims."""
    if _oauth is None:
        raise RuntimeError("OIDC not configured. Set OIDC_ENABLED=true.")

    token = await _oauth.oidc.authorize_access_token(request)
    userinfo: dict = token.get("userinfo") or {}
    if not userinfo:
        userinfo = await _oauth.oidc.userinfo(token=token)
    return userinfo


def map_groups_to_role(groups: list[str]) -> Role:
    """Map OIDC group claims to platform Role enum.

    Configured via OIDC_ADMIN_GROUPS and OIDC_ENGINEER_GROUPS (comma-separated).
    Falls back to VIEWER if no matching group.
    """
    from backend.core.config import settings

    admin_groups = {g.strip() for g in settings.oidc_admin_groups.split(",") if g.strip()}
    engineer_groups = {g.strip() for g in settings.oidc_engineer_groups.split(",") if g.strip()}

    group_set = set(groups)
    if admin_groups & group_set:
        return Role.ADMIN
    if engineer_groups & group_set:
        return Role.ENGINEER
    return Role.VIEWER
