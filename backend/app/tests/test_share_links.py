"""Tests for share-by-link: create, revoke, redeem."""

import pytest
from httpx import AsyncClient


async def _create_doc(client: AsyncClient, headers: dict, workspace_id: str) -> str:
    resp = await client.post("/api/documents", json={
        "title": "Link doc",
        "workspace_id": workspace_id,
    }, headers=headers)
    assert resp.status_code == 201
    return resp.json()["document_id"]


async def _create_link(
    client: AsyncClient,
    owner_headers: dict,
    doc_id: str,
    role: str = "viewer",
    expires_in_hours: int | None = None,
) -> tuple[str, str]:
    """Returns (share_id, raw_token)."""
    resp = await client.post(f"/api/documents/{doc_id}/share-links", json={
        "role": role,
        "expires_in_hours": expires_in_hours,
        "allow_ai": True,
    }, headers=owner_headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data["share_id"], data["token"]


@pytest.mark.asyncio
async def test_owner_can_create_link(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    share_id, token = await _create_link(client, auth_headers, doc_id, role="editor")
    assert share_id
    assert token and len(token) >= 20


@pytest.mark.asyncio
async def test_non_owner_cannot_create_link(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    resp = await client.post(f"/api/documents/{doc_id}/share-links", json={
        "role": "viewer",
    }, headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_link_rejects_bad_role(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    resp = await client.post(f"/api/documents/{doc_id}/share-links", json={
        "role": "admin",
    }, headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_redeem_grants_document_access(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    _, token = await _create_link(client, auth_headers, doc_id, role="viewer")

    # Before redeem: Bob cannot read
    resp = await client.get(f"/api/documents/{doc_id}", headers=user_bob["headers"])
    assert resp.status_code == 403

    # Redeem as Bob
    resp = await client.post("/api/shares/redeem", json={
        "token": token,
    }, headers=user_bob["headers"])
    assert resp.status_code == 200
    assert resp.json()["document_id"] == doc_id
    assert resp.json()["role"] == "viewer"

    # After redeem: Bob can read
    resp = await client.get(f"/api/documents/{doc_id}", headers=user_bob["headers"])
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_redeem_editor_link_allows_patch(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    _, token = await _create_link(client, auth_headers, doc_id, role="editor")

    await client.post("/api/shares/redeem", json={"token": token}, headers=user_bob["headers"])

    resp = await client.patch(f"/api/documents/{doc_id}", json={
        "title": "Renamed via link",
    }, headers=user_bob["headers"])
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed via link"


@pytest.mark.asyncio
async def test_redeem_unknown_token_rejected(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post("/api/shares/redeem", json={
        "token": "not-a-valid-token",
    }, headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_redeem_revoked_token_rejected(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    share_id, token = await _create_link(client, auth_headers, doc_id)

    # Revoke
    resp = await client.delete(
        f"/api/documents/{doc_id}/share-links/{share_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    # Redeem should now fail
    resp = await client.post("/api/shares/redeem", json={
        "token": token,
    }, headers=user_bob["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_owner_cannot_revoke_link(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    share_id, _ = await _create_link(client, auth_headers, doc_id)

    resp = await client.delete(
        f"/api/documents/{doc_id}/share-links/{share_id}",
        headers=user_bob["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_redeem_is_idempotent(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    _, token = await _create_link(client, auth_headers, doc_id)

    # Redeem twice — second call should still succeed, no duplicate share row
    resp1 = await client.post("/api/shares/redeem", json={"token": token}, headers=user_bob["headers"])
    assert resp1.status_code == 200
    resp2 = await client.post("/api/shares/redeem", json={"token": token}, headers=user_bob["headers"])
    assert resp2.status_code == 200

    # Owner's share list should still show exactly one USER grant + one LINK row
    resp = await client.get(f"/api/documents/{doc_id}/shares", headers=auth_headers)
    rows = resp.json()
    user_rows = [r for r in rows if r["grantee_type"] == "USER"]
    assert len(user_rows) == 1


@pytest.mark.asyncio
async def test_redeem_expired_link_rejected(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    # Create a link with short TTL then manually backdate to expire it.
    _, token = await _create_link(
        client, auth_headers, doc_id, expires_in_hours=1
    )

    # Force expiry directly in the DB (tests use same SQLite file)
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    from app.models.document_share import DocumentShare
    from app.tests.conftest import test_session_factory

    async with test_session_factory() as session:
        await session.execute(
            update(DocumentShare)
            .where(DocumentShare.grantee_type == "LINK")
            .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
        await session.commit()

    resp = await client.post("/api/shares/redeem", json={
        "token": token,
    }, headers=user_bob["headers"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_link_rejects_nonpositive_expiry(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    resp = await client.post(f"/api/documents/{doc_id}/share-links", json={
        "role": "viewer",
        "expires_in_hours": 0,
    }, headers=auth_headers)
    assert resp.status_code == 400
