import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_document_crud(client: AsyncClient, auth_headers: dict, workspace_id: str):
    # Create
    resp = await client.post("/api/documents", json={
        "title": "Test Doc",
        "workspace_id": workspace_id,
    }, headers=auth_headers)
    assert resp.status_code == 201
    doc = resp.json()
    doc_id = doc["document_id"]
    assert doc["title"] == "Test Doc"
    assert doc["status"] == "active"
    assert doc["content"] == {"type": "doc", "content": []}

    # Get
    resp = await client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Test Doc"

    # List
    resp = await client.get("/api/documents", headers=auth_headers)
    assert resp.status_code == 200
    assert any(d["document_id"] == doc_id for d in resp.json())

    # Update
    resp = await client.patch(f"/api/documents/{doc_id}", json={
        "title": "Updated Title",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"

    # Delete (soft)
    resp = await client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Get after delete should 404
    resp = await client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_document_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/documents/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_document_unauthorized(client: AsyncClient, workspace_id: str):
    resp = await client.post("/api/documents", json={
        "title": "No Auth",
        "workspace_id": workspace_id,
    })
    assert resp.status_code == 401
