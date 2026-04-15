"""Document-level permission coverage beyond the share CRUD tests.

test_shares.py already covers the happy paths (editor-can-patch,
viewer-can-read, etc.). This file focuses on edge cases:

- expired share blocks access
- deleted document returns 404 even for a prior viewer
- viewer cannot PATCH content
- non-owner cannot soft-delete
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


async def _create_doc(client: AsyncClient, headers: dict, workspace_id: str) -> str:
    resp = await client.post("/api/documents", json={
        "title": "Perm doc",
        "workspace_id": workspace_id,
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json()["document_id"]


async def _share_with(
    client: AsyncClient,
    owner_headers: dict,
    doc_id: str,
    email: str,
    role: str = "viewer",
    expires_at: datetime | None = None,
) -> None:
    payload: dict = {
        "grantee_type": "USER",
        "grantee_ref": email,
        "role": role,
        "allow_ai": True,
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at.isoformat()
    resp = await client.post(
        f"/api/documents/{doc_id}/shares", json=payload, headers=owner_headers
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_expired_share_blocks_access(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await _share_with(
        client, auth_headers, doc_id, user_bob["email"], role="viewer", expires_at=past
    )

    resp = await client.get(f"/api/documents/{doc_id}", headers=user_bob["headers"])
    assert resp.status_code == 403
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_viewer_patch_content_denied(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"], role="viewer")

    resp = await client.patch(f"/api/documents/{doc_id}", json={
        "content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "pwned"}]}
        ]},
    }, headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_editor_cannot_soft_delete(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"], role="editor")

    resp = await client.delete(f"/api/documents/{doc_id}", headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deleted_document_returns_404_for_viewer(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"], role="viewer")

    # Owner soft-deletes
    resp = await client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 204

    # Previously-shared viewer now sees 404 (access check happens after the
    # soft-delete short-circuit)
    resp = await client.get(f"/api/documents/{doc_id}", headers=user_bob["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_without_auth_returns_401(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    resp = await client.patch(f"/api/documents/{doc_id}", json={"title": "hi"})
    assert resp.status_code == 401
