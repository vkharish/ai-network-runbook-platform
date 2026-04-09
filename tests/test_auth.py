"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def test_register_creates_user(async_client: AsyncClient):
    resp = await async_client.post("/api/v1/auth/register", json={
        "email": "user@test.com",
        "password": "securepassword123",
        "full_name": "Test User",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "user@test.com"
    assert "id" in data


async def test_register_duplicate_email_rejected(async_client: AsyncClient):
    payload = {"email": "dup@test.com", "password": "pass1234567", "full_name": "Dup User"}
    await async_client.post("/api/v1/auth/register", json=payload)
    resp = await async_client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code in (400, 409)


async def test_login_returns_tokens(async_client: AsyncClient):
    await async_client.post("/api/v1/auth/register", json={
        "email": "login@test.com", "password": "mypassword999", "full_name": "Login User",
    })
    resp = await async_client.post("/api/v1/auth/login", json={
        "email": "login@test.com", "password": "mypassword999",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password_rejected(async_client: AsyncClient):
    await async_client.post("/api/v1/auth/register", json={
        "email": "wp@test.com", "password": "correct_password", "full_name": "WP User",
    })
    resp = await async_client.post("/api/v1/auth/login", json={
        "email": "wp@test.com", "password": "wrong_password",
    })
    assert resp.status_code == 401


async def test_me_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(async_client: AsyncClient):
    headers = await register_and_login(async_client, "me@test.com", "mepassword99")
    resp = await async_client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@test.com"
