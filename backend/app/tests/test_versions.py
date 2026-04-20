import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.api.deps import get_db
from app.main import app
from app.realtime import websocket as ws_router
from app.tests.conftest import _override_get_db

MSG_SYNC = 0
SYNC_STEP1 = 0
SYNC_STEP2 = 1
SYNC_UPDATE = 2


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
    initial_revision_id = versions[0]["base_revision_id"]

    # Update document content
    update_resp = await client.patch(f"/api/documents/{doc_id}", json={
        "content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "v2 content"}]}
        ]},
    }, headers=auth_headers)
    assert update_resp.status_code == 200
    updated_doc = update_resp.json()
    assert updated_doc["current_revision_id"] != initial_revision_id

    resp = await client.get(f"/api/documents/{doc_id}/versions", headers=auth_headers)
    assert resp.status_code == 200
    updated_versions = resp.json()
    assert len(updated_versions) >= 2
    assert updated_versions[0]["base_revision_id"] == updated_doc["current_revision_id"]

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


def _drain_initial_sync(ws) -> None:
    msg1 = ws.receive_bytes()
    assert msg1[0] == MSG_SYNC and msg1[1] == SYNC_STEP1
    msg2 = ws.receive_bytes()
    assert msg2[0] == MSG_SYNC and msg2[1] == SYNC_STEP2


def test_restore_broadcasts_yjs_update_to_connected_clients():
    """The REST restore endpoint must push a SYNC_UPDATE to the live WebSocket room
    so connected clients actually see the restored content. Without this, clients
    keep showing the old in-memory Yjs state even though the DB has been updated."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as http_client:
        # Register + login
        email = f"restore_{uuid.uuid4().hex[:8]}@example.com"
        resp = http_client.post("/api/auth/register", json={
            "email": email, "display_name": "Restore User", "password": "pw12345",
        })
        assert resp.status_code == 201
        resp = http_client.post("/api/auth/login", json={
            "email": email, "password": "pw12345",
        })
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Workspace (must be created in the same test session factory the app uses)
        import asyncio
        from app.tests.conftest import test_session_factory
        from app.models.workspace import Workspace

        async def _make_ws() -> str:
            async with test_session_factory() as session:
                ws = Workspace(name="Restore WS")
                session.add(ws)
                await session.commit()
                await session.refresh(ws)
                return ws.workspace_id

        workspace_id = asyncio.run(_make_ws())

        # Create doc with v1 content
        resp = http_client.post("/api/documents", json={
            "title": "Restore Doc",
            "workspace_id": workspace_id,
            "initial_content": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "v1 original"}]}
            ]},
        }, headers=headers)
        assert resp.status_code == 201
        doc_id = resp.json()["document_id"]

        # Update to v2
        resp = http_client.patch(f"/api/documents/{doc_id}", json={
            "content": {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "v2 updated"}]}
            ]},
        }, headers=headers)
        assert resp.status_code == 200

        # Find v1's version_id (reason="initial")
        resp = http_client.get(f"/api/documents/{doc_id}/versions", headers=headers)
        versions = resp.json()
        v1 = next(v for v in versions if v["reason"] == "initial")
        v1_id = v1["version_id"]

        ws_router._rooms.clear()

        # Connect WS, drain initial sync, then restore and assert broadcast arrives
        with http_client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws:
            _drain_initial_sync(ws)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(ws.receive_bytes)
                restore_resp = http_client.post(
                    f"/api/documents/{doc_id}/versions/{v1_id}/restore",
                    headers=headers,
                )
                assert restore_resp.status_code == 201, restore_resp.text
                msg = future.result(timeout=3)
                assert msg[0] == MSG_SYNC, f"expected SYNC frame, got type {msg[0]}"
                assert msg[1] == SYNC_UPDATE, f"expected SYNC_UPDATE, got {msg[1]}"
                assert len(msg) > 2, "SYNC_UPDATE payload should carry the delta bytes"
    app.dependency_overrides.clear()
