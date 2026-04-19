import pytest
from httpx import AsyncClient


async def _create_doc(client: AsyncClient, headers: dict, workspace_id: str) -> str:
    resp = await client.post("/api/documents", json={
        "title": "Audit Test Doc",
        "workspace_id": workspace_id,
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json()["document_id"]


@pytest.mark.asyncio
async def test_audit_trail_records_share_events(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    # Create a share — should produce an audit event
    resp = await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": user_bob["email"],
        "role": "viewer",
        "allow_ai": True,
    }, headers=auth_headers)
    assert resp.status_code == 201
    share_id = resp.json()["share_id"]

    # Read audit trail
    resp = await client.get(f"/api/documents/{doc_id}/audit", headers=auth_headers)
    assert resp.status_code == 200
    events = resp.json()
    event_types = [e["event_type"] for e in events]
    assert "share.created" in event_types

    # Delete share — should produce another audit event
    resp = await client.delete(
        f"/api/documents/{doc_id}/shares/{share_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    resp = await client.get(f"/api/documents/{doc_id}/audit", headers=auth_headers)
    event_types = [e["event_type"] for e in resp.json()]
    assert "share.deleted" in event_types


@pytest.mark.asyncio
async def test_owner_can_read_deleted_document_audit_trail(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    delete_resp = await client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    audit_resp = await client.get(f"/api/documents/{doc_id}/audit", headers=auth_headers)
    assert audit_resp.status_code == 200
    event_types = [event["event_type"] for event in audit_resp.json()]
    assert "document.deleted" in event_types


@pytest.mark.asyncio
async def test_non_owner_cannot_read_audit(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    # Share with Bob so he can see the doc, but he still shouldn't see the audit
    await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": user_bob["email"],
        "role": "editor",
        "allow_ai": True,
    }, headers=auth_headers)

    resp = await client.get(f"/api/documents/{doc_id}/audit", headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_share_updates_role(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    resp = await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": user_bob["email"],
        "role": "viewer",
        "allow_ai": True,
    }, headers=auth_headers)
    share_id = resp.json()["share_id"]

    # Update role to editor
    resp = await client.patch(
        f"/api/documents/{doc_id}/shares/{share_id}",
        json={"role": "editor"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "editor"

    # Verify audit event
    resp = await client.get(f"/api/documents/{doc_id}/audit", headers=auth_headers)
    event_types = [e["event_type"] for e in resp.json()]
    assert "share.updated" in event_types


@pytest.mark.asyncio
async def test_audit_trail_records_version_restore(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    # Create a content update to generate a version
    await client.patch(f"/api/documents/{doc_id}", json={
        "content": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "v2"}]}]}
    }, headers=auth_headers)

    # Get versions and restore
    resp = await client.get(f"/api/documents/{doc_id}/versions", headers=auth_headers)
    versions = resp.json()
    assert len(versions) >= 1
    version_id = versions[-1]["version_id"]

    resp = await client.post(
        f"/api/documents/{doc_id}/versions/{version_id}/restore",
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # Check audit trail
    resp = await client.get(f"/api/documents/{doc_id}/audit", headers=auth_headers)
    event_types = [e["event_type"] for e in resp.json()]
    assert "version.restored" in event_types


@pytest.mark.asyncio
async def test_document_mutations_are_audited(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    update_resp = await client.patch(
        f"/api/documents/{doc_id}",
        json={"title": "Renamed"},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200

    audit_resp = await client.get(f"/api/documents/{doc_id}/audit", headers=auth_headers)
    assert audit_resp.status_code == 200
    event_types = [event["event_type"] for event in audit_resp.json()]
    assert "document.created" in event_types
    assert "document.updated" in event_types
