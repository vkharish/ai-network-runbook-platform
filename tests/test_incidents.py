"""Tests for incident CRUD and diagnosis trigger."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch

from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio

INCIDENT_PAYLOAD = {
    "title": "BGP session down on R1-CORE",
    "description": "R1-CORE BGP peer 10.0.0.2 stuck in Active state",
    "severity": "P2",
    "affected_device": "R1-CORE",
    "affected_protocol": "bgp",
}


async def test_create_incident(async_client: AsyncClient):
    headers = await register_and_login(async_client, "eng@test.com", "engineer123")
    resp = await async_client.post("/api/v1/incidents/", json=INCIDENT_PAYLOAD, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == INCIDENT_PAYLOAD["title"]
    assert data["status"] == "open"
    assert "id" in data


async def test_list_incidents(async_client: AsyncClient):
    headers = await register_and_login(async_client, "list@test.com", "listpass123")
    await async_client.post("/api/v1/incidents/", json=INCIDENT_PAYLOAD, headers=headers)
    resp = await async_client.get("/api/v1/incidents/", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


async def test_get_incident(async_client: AsyncClient):
    headers = await register_and_login(async_client, "get@test.com", "getpass1234")
    create_resp = await async_client.post("/api/v1/incidents/", json=INCIDENT_PAYLOAD, headers=headers)
    incident_id = create_resp.json()["id"]
    resp = await async_client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == incident_id


async def test_get_incident_not_found(async_client: AsyncClient):
    headers = await register_and_login(async_client, "notfound@test.com", "nfpass1234")
    resp = await async_client.get(
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert resp.status_code == 404


async def test_update_incident(async_client: AsyncClient):
    headers = await register_and_login(async_client, "upd@test.com", "updpass1234")
    create_resp = await async_client.post("/api/v1/incidents/", json=INCIDENT_PAYLOAD, headers=headers)
    incident_id = create_resp.json()["id"]
    resp = await async_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"title": "Updated Title"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


async def test_diagnose_triggers_celery(async_client: AsyncClient):
    headers = await register_and_login(async_client, "diag@test.com", "diagpass123")
    create_resp = await async_client.post("/api/v1/incidents/", json=INCIDENT_PAYLOAD, headers=headers)
    incident_id = create_resp.json()["id"]

    with patch("backend.app.api.routes.incident_routes.run_diagnosis_task") as mock_task:
        mock_task.delay.return_value = None
        resp = await async_client.post(
            f"/api/v1/incidents/{incident_id}/diagnose",
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "diagnosing"
    mock_task.delay.assert_called_once_with(incident_id)


async def test_diagnose_wrong_status_rejected(async_client: AsyncClient):
    headers = await register_and_login(async_client, "dws@test.com", "dwspass1234")
    create_resp = await async_client.post("/api/v1/incidents/", json=INCIDENT_PAYLOAD, headers=headers)
    incident_id = create_resp.json()["id"]

    # Set to closed manually — closed incidents cannot be re-diagnosed
    await async_client.patch(
        f"/api/v1/incidents/{incident_id}",
        json={"status": "closed"},
        headers=headers,
    )
    resp = await async_client.post(
        f"/api/v1/incidents/{incident_id}/diagnose",
        headers=headers,
    )
    assert resp.status_code == 400


async def test_incidents_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/incidents/")
    assert resp.status_code == 401
