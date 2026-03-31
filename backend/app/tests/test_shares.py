import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_doc(client: AsyncClient, headers: dict, workspace_id: str) -> str:
    resp = await client.post("/api/documents", json={
        "title": "Share Test Doc",
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
) -> str:
    resp = await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": email,
        "role": role,
        "allow_ai": True,
    }, headers=owner_headers)
    assert resp.status_code == 201, f"Share creation failed: {resp.text}"
    return resp.json()["share_id"]


# ---------------------------------------------------------------------------
# Share CRUD — ownership enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_can_list_shares(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"])

    resp = await client.get(f"/api/documents/{doc_id}/shares", headers=auth_headers)
    assert resp.status_code == 200
    shares = resp.json()
    assert len(shares) == 1
    assert shares[0]["grantee_ref"] == user_bob["email"]


@pytest.mark.asyncio
async def test_non_owner_cannot_list_shares(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    resp = await client.get(f"/api/documents/{doc_id}/shares", headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_create_share(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    resp = await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": user_bob["email"],
        "role": "editor",
        "allow_ai": True,
    }, headers=auth_headers)
    assert resp.status_code == 201
    share = resp.json()
    assert share["grantee_ref"] == user_bob["email"]
    assert share["role"] == "editor"


@pytest.mark.asyncio
async def test_non_owner_cannot_create_share(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    resp = await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": "charlie@example.com",
        "role": "viewer",
        "allow_ai": False,
    }, headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_delete_share(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    share_id = await _share_with(client, auth_headers, doc_id, user_bob["email"])

    resp = await client.delete(
        f"/api/documents/{doc_id}/shares/{share_id}", headers=auth_headers
    )
    assert resp.status_code == 204

    # Verify list is now empty
    resp = await client.get(f"/api/documents/{doc_id}/shares", headers=auth_headers)
    assert resp.json() == []


@pytest.mark.asyncio
async def test_non_owner_cannot_delete_share(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    share_id = await _share_with(client, auth_headers, doc_id, user_bob["email"])

    resp = await client.delete(
        f"/api/documents/{doc_id}/shares/{share_id}", headers=user_bob["headers"]
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Document access via share
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unshared_user_cannot_read_document(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    resp = await client.get(f"/api/documents/{doc_id}", headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_shared_viewer_can_read_document(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"], role="viewer")

    resp = await client.get(f"/api/documents/{doc_id}", headers=user_bob["headers"])
    assert resp.status_code == 200
    assert resp.json()["document_id"] == doc_id


@pytest.mark.asyncio
async def test_shared_viewer_cannot_update_document(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"], role="viewer")

    resp = await client.patch(
        f"/api/documents/{doc_id}",
        json={"title": "Hijacked"},
        headers=user_bob["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_shared_editor_can_update_document(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"], role="editor")

    resp = await client.patch(
        f"/api/documents/{doc_id}",
        json={"title": "Bob's Edit"},
        headers=user_bob["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Bob's Edit"


@pytest.mark.asyncio
async def test_shared_editor_cannot_delete_document(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"], role="editor")

    resp = await client.delete(f"/api/documents/{doc_id}", headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_shared_document_appears_in_grantee_list(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)
    await _share_with(client, auth_headers, doc_id, user_bob["email"], role="viewer")

    resp = await client.get("/api/documents", headers=user_bob["headers"])
    assert resp.status_code == 200
    ids = [d["document_id"] for d in resp.json()]
    assert doc_id in ids


@pytest.mark.asyncio
async def test_unshared_document_not_in_other_user_list(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id = await _create_doc(client, auth_headers, workspace_id)

    resp = await client.get("/api/documents", headers=user_bob["headers"])
    ids = [d["document_id"] for d in resp.json()]
    assert doc_id not in ids
