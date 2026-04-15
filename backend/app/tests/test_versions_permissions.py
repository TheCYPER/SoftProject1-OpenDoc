"""Permission tests for /api/documents/{id}/versions — viewer cannot restore."""

import pytest
from httpx import AsyncClient


async def _create_doc_with_version(
    client: AsyncClient, owner_headers: dict, workspace_id: str
) -> tuple[str, str]:
    resp = await client.post("/api/documents", json={
        "title": "Versioned perm doc",
        "workspace_id": workspace_id,
        "initial_content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "v1"}]}
        ]},
    }, headers=owner_headers)
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    resp = await client.get(f"/api/documents/{doc_id}/versions", headers=owner_headers)
    version_id = resp.json()[0]["version_id"]
    return doc_id, version_id


@pytest.mark.asyncio
async def test_non_member_cannot_list_versions(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id, _ = await _create_doc_with_version(client, auth_headers, workspace_id)

    resp = await client.get(
        f"/api/documents/{doc_id}/versions", headers=user_bob["headers"]
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_member_cannot_restore(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id, version_id = await _create_doc_with_version(
        client, auth_headers, workspace_id
    )

    resp = await client.post(
        f"/api/documents/{doc_id}/versions/{version_id}/restore",
        headers=user_bob["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_can_list_but_not_restore(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id, version_id = await _create_doc_with_version(
        client, auth_headers, workspace_id
    )
    await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": user_bob["email"],
        "role": "viewer",
        "allow_ai": False,
    }, headers=auth_headers)

    resp = await client.get(
        f"/api/documents/{doc_id}/versions", headers=user_bob["headers"]
    )
    assert resp.status_code == 200

    resp = await client.post(
        f"/api/documents/{doc_id}/versions/{version_id}/restore",
        headers=user_bob["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_editor_can_restore(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id, version_id = await _create_doc_with_version(
        client, auth_headers, workspace_id
    )
    await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": user_bob["email"],
        "role": "editor",
        "allow_ai": False,
    }, headers=auth_headers)

    resp = await client.post(
        f"/api/documents/{doc_id}/versions/{version_id}/restore",
        headers=user_bob["headers"],
    )
    assert resp.status_code == 201
