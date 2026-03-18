import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_version_list_and_restore(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    # Create a document
    resp = await client.post("/api/documents", json={
        "title": "Versioned Doc",
        "workspace_id": workspace_id,
        "initial_content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "v1 content"}]}
        ]},
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    # List versions (should have initial)
    resp = await client.get(f"/api/documents/{doc_id}/versions", headers=auth_headers)
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) >= 1
    v1_id = versions[0]["version_id"]

    # Update document content
    await client.patch(f"/api/documents/{doc_id}", json={
        "content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "v2 content"}]}
        ]},
    }, headers=auth_headers)

    # Restore v1
    resp = await client.post(
        f"/api/documents/{doc_id}/versions/{v1_id}/restore",
        headers=auth_headers,
    )
    assert resp.status_code == 201
    restored = resp.json()
    assert restored["restored_from_version_id"] == v1_id
    assert restored["reason"] == "restore"

    # Verify document content is back to v1
    resp = await client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    content = resp.json()["content"]
    assert content["content"][0]["content"][0]["text"] == "v1 content"
