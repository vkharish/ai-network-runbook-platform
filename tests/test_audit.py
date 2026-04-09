"""Tests for RBAC audit log — verifies that key user actions are recorded."""

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from tests.conftest import register_and_login


# ---------------------------------------------------------------------------
# Auth events
# ---------------------------------------------------------------------------

async def test_register_creates_audit_entry(async_client):
    """Registering a user should create an audit log entry with action='register'."""
    resp = await async_client.post("/api/v1/auth/register", json={
        "email": "audit_reg@test.com",
        "password": "password123",
        "full_name": "Audit User",
        "role": "admin",
    })
    assert resp.status_code == 201

    login_resp = await async_client.post("/api/v1/auth/login", json={
        "email": "audit_reg@test.com",
        "password": "password123",
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    audit_resp = await async_client.get("/api/v1/audit/", headers=headers)
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    actions = [e["action"] for e in entries]
    assert "register" in actions


async def test_login_creates_audit_entry(async_client):
    """Successful login should create an audit log entry with action='login'."""
    await async_client.post("/api/v1/auth/register", json={
        "email": "audit_login@test.com",
        "password": "password123",
        "full_name": "Login Audit",
        "role": "admin",
    })
    login_resp = await async_client.post("/api/v1/auth/login", json={
        "email": "audit_login@test.com",
        "password": "password123",
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    audit_resp = await async_client.get("/api/v1/audit/", headers=headers)
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    actions = [e["action"] for e in entries]
    assert "login" in actions


async def test_failed_login_does_not_create_audit_entry(async_client):
    """Invalid credentials should NOT produce an audit entry."""
    await async_client.post("/api/v1/auth/register", json={
        "email": "audit_fail@test.com",
        "password": "rightpassword",
        "full_name": "Fail User",
        "role": "admin",
    })
    # Bad login
    await async_client.post("/api/v1/auth/login", json={
        "email": "audit_fail@test.com",
        "password": "wrongpassword",
    })

    # Login with correct creds to get token
    login_resp = await async_client.post("/api/v1/auth/login", json={
        "email": "audit_fail@test.com",
        "password": "rightpassword",
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    audit_resp = await async_client.get(
        "/api/v1/audit/",
        params={"action": "login_failed"},
        headers=headers,
    )
    assert audit_resp.status_code == 200
    assert audit_resp.json() == []


# ---------------------------------------------------------------------------
# Audit log API — access control
# ---------------------------------------------------------------------------

async def test_audit_log_requires_admin(async_client):
    """Non-admin users cannot access the audit log endpoint."""
    # Register as viewer (default role)
    resp = await async_client.post("/api/v1/auth/register", json={
        "email": "viewer_audit@test.com",
        "password": "password123",
        "full_name": "Viewer User",
        "role": "viewer",
    })
    assert resp.status_code == 201
    login_resp = await async_client.post("/api/v1/auth/login", json={
        "email": "viewer_audit@test.com",
        "password": "password123",
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    audit_resp = await async_client.get("/api/v1/audit/", headers=headers)
    assert audit_resp.status_code == 403


async def test_audit_log_unauthenticated_rejected(async_client):
    """Unauthenticated requests to audit endpoint must be rejected."""
    resp = await async_client.get("/api/v1/audit/")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Audit log filtering
# ---------------------------------------------------------------------------

async def test_audit_log_filter_by_action(async_client):
    """Filtering by action returns only matching entries."""
    await async_client.post("/api/v1/auth/register", json={
        "email": "audit_filter@test.com",
        "password": "password123",
        "full_name": "Filter User",
        "role": "admin",
    })
    login_resp = await async_client.post("/api/v1/auth/login", json={
        "email": "audit_filter@test.com",
        "password": "password123",
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Filter for register only
    resp = await async_client.get(
        "/api/v1/audit/",
        params={"action": "register"},
        headers=headers,
    )
    assert resp.status_code == 200
    entries = resp.json()
    for entry in entries:
        assert entry["action"] == "register"


# ---------------------------------------------------------------------------
# Unit tests — audit_service directly (no HTTP)
# ---------------------------------------------------------------------------

async def test_log_action_persists_entry(test_engine):
    """audit_service.log_action() saves an AuditLog row to the DB."""
    import uuid
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from backend.models.audit_log_model import AuditLog
    from backend.services import audit_service

    SessionLocal = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    user_id = uuid.uuid4()
    async with SessionLocal() as db:
        await audit_service.log_action(
            db,
            user_id=user_id,
            action="test_action",
            resource_type="test",
            resource_id="abc-123",
            metadata={"key": "value"},
        )

    async with SessionLocal() as db:
        result = await db.execute(
            select(AuditLog).where(AuditLog.action == "test_action")
        )
        entry = result.scalar_one_or_none()
        assert entry is not None
        assert entry.user_id == user_id
        assert entry.resource_type == "test"
        assert entry.resource_id == "abc-123"
        assert entry.metadata_ == {"key": "value"}


async def test_log_action_survives_null_user(test_engine):
    """log_action with user_id=None (system action) must not raise."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from backend.models.audit_log_model import AuditLog
    from backend.services import audit_service

    SessionLocal = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with SessionLocal() as db:
        await audit_service.log_action(
            db,
            user_id=None,
            action="system_action",
            resource_type="system",
            resource_id="startup",
        )

    async with SessionLocal() as db:
        result = await db.execute(
            select(AuditLog).where(AuditLog.action == "system_action")
        )
        entry = result.scalar_one_or_none()
        assert entry is not None
        assert entry.user_id is None
