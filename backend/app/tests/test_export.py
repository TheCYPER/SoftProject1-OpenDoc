import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_export_html(client: AsyncClient, auth_headers: dict, workspace_id: str):
    resp = await client.post("/api/documents", json={
        "title": "Export Test",
        "workspace_id": workspace_id,
        "initial_content": {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Hello World"}]}
            ],
        },
    }, headers=auth_headers)
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    resp = await client.get(f"/api/documents/{doc_id}/export?format=html", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Hello World" in resp.text
    assert "Export Test" in resp.text


@pytest.mark.asyncio
async def test_export_txt(client: AsyncClient, auth_headers: dict, workspace_id: str):
    resp = await client.post("/api/documents", json={
        "title": "Plain Export",
        "workspace_id": workspace_id,
        "initial_content": {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Plain text content"}]}
            ],
        },
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    resp = await client.get(f"/api/documents/{doc_id}/export?format=txt", headers=auth_headers)
    assert resp.status_code == 200
    assert "Plain text content" in resp.text


@pytest.mark.asyncio
async def test_export_requires_auth(client: AsyncClient, workspace_id: str, auth_headers: dict):
    resp = await client.post("/api/documents", json={
        "title": "Auth Export Test",
        "workspace_id": workspace_id,
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    resp = await client.get(f"/api/documents/{doc_id}/export?format=html")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_viewer_can_export(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    resp = await client.post("/api/documents", json={
        "title": "Viewer Export",
        "workspace_id": workspace_id,
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": user_bob["email"],
        "role": "viewer",
        "allow_ai": True,
    }, headers=auth_headers)

    resp = await client.get(f"/api/documents/{doc_id}/export?format=html", headers=user_bob["headers"])
    assert resp.status_code == 200
