import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_db
from app.main import app
from app.realtime import websocket as ws_router
from app.tests.conftest import _override_get_db

MSG_SYNC = 0
MSG_AWARENESS = 1
SYNC_STEP1 = 0
SYNC_STEP2 = 1
SYNC_UPDATE = 2


def _setup_user_and_doc(client: TestClient) -> tuple[str, str]:
    """Register a user, create a workspace + document, return (token, document_id)."""
    unique = uuid.uuid4().hex[:8]
    email = f"ws_{unique}@example.com"

    resp = client.post("/api/auth/register", json={
        "email": email,
        "display_name": "WS Test",
        "password": "testpass123",
    })
    assert resp.status_code == 201

    resp = client.post("/api/auth/login", json={
        "email": email,
        "password": "testpass123",
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    from app.models.workspace import Workspace
    import asyncio
    from app.tests.conftest import test_session_factory

    async def _make_ws() -> str:
        async with test_session_factory() as session:
            ws = Workspace(name="WS Workspace")
            session.add(ws)
            await session.commit()
            await session.refresh(ws)
            return ws.workspace_id

    workspace_id = asyncio.get_event_loop().run_until_complete(_make_ws())
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/documents", json={
        "title": "WS Test Doc",
        "workspace_id": workspace_id,
    }, headers=headers)
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    return token, doc_id


def _drain_initial_sync(ws) -> None:
    """Consume the initial SyncStep1 + SyncStep2 the server sends on connect."""
    # Server sends SyncStep1 then SyncStep2
    msg1 = ws.receive_bytes()
    assert msg1[0] == MSG_SYNC and msg1[1] == SYNC_STEP1
    msg2 = ws.receive_bytes()
    assert msg2[0] == MSG_SYNC and msg2[1] == SYNC_STEP2


def test_websocket_rejects_invalid_token():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws/documents/any-doc-id?token=invalid"):
                assert False, "Expected websocket authentication failure"
        except WebSocketDisconnect as exc:
            assert exc.code == 4001
    app.dependency_overrides.clear()


def test_websocket_rejects_unauthorized_document():
    """A valid token but no access to the document should be rejected."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token, _doc_id = _setup_user_and_doc(client)
        ws_router._rooms.clear()
        try:
            with client.websocket_connect(f"/ws/documents/{uuid.uuid4()}?token={token}"):
                assert False, "Expected access denied"
        except WebSocketDisconnect as exc:
            assert exc.code == 4003
    app.dependency_overrides.clear()


def test_websocket_sends_initial_sync_on_connect():
    """Server should send SyncStep1 and SyncStep2 when a client connects."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token, doc_id = _setup_user_and_doc(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws:
            msg1 = ws.receive_bytes()
            assert msg1[0] == MSG_SYNC
            assert msg1[1] == SYNC_STEP1

            msg2 = ws.receive_bytes()
            assert msg2[0] == MSG_SYNC
            assert msg2[1] == SYNC_STEP2
    app.dependency_overrides.clear()


def test_websocket_relays_sync_updates_between_clients():
    """Sync update from one client should be broadcast to another."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token, doc_id = _setup_user_and_doc(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws1:
            _drain_initial_sync(ws1)
            with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws2:
                _drain_initial_sync(ws2)
                # Send a sync update message from ws1
                update_payload = bytes([MSG_SYNC, SYNC_UPDATE, 2, 0xAA, 0xBB])
                ws1.send_bytes(update_payload)
                received = ws2.receive_bytes()
                assert received == update_payload
    app.dependency_overrides.clear()


def test_websocket_relays_awareness_between_clients():
    """Awareness messages should be relayed between clients."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token, doc_id = _setup_user_and_doc(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws1:
            _drain_initial_sync(ws1)
            with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws2:
                _drain_initial_sync(ws2)
                awareness_msg = bytes([MSG_AWARENESS, 3, 0x01, 0x02, 0x03])
                ws1.send_bytes(awareness_msg)
                received = ws2.receive_bytes()
                assert received == awareness_msg
    app.dependency_overrides.clear()


def test_same_user_can_open_multiple_connections():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token, doc_id = _setup_user_and_doc(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws1:
            _drain_initial_sync(ws1)
            with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws2:
                _drain_initial_sync(ws2)
                with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws3:
                    _drain_initial_sync(ws3)
                    update = bytes([MSG_SYNC, SYNC_UPDATE, 1, 0xFF])
                    ws1.send_bytes(update)
                    assert ws2.receive_bytes() == update
                    assert ws3.receive_bytes() == update
    app.dependency_overrides.clear()
