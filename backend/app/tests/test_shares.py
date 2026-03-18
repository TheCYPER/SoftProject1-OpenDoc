import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_share_create_and_delete(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    # Create a document first
    resp = await client.post("/api/documents", json={
        "title": "Shared Doc",
        "workspace_id": workspace_id,
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    # Create share
    resp = await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": "bob@example.com",
        "role": "editor",
        "allow_ai": True,
    }, headers=auth_headers)
    assert resp.status_code == 201
    share = resp.json()
    assert share["grantee_type"] == "USER"
    assert share["role"] == "editor"
    share_id = share["share_id"]

    # Delete share
    resp = await client.delete(
        f"/api/documents/{doc_id}/shares/{share_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204
