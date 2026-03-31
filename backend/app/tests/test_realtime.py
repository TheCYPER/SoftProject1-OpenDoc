import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_db
from app.main import app
from app.realtime import websocket as ws_router
from app.tests.conftest import _override_get_db


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
    headers = {"Authorization": f"Bearer {token}"}

    # Create workspace directly via DB helper isn't available here, so we
    # create a workspace inline using the ORM through the test DB session.
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

    resp = client.post("/api/documents", json={
        "title": "WS Test Doc",
        "workspace_id": workspace_id,
    }, headers=headers)
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    return token, doc_id


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


def test_websocket_relays_binary_updates_between_clients():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token, doc_id = _setup_user_and_doc(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws1:
            with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws2:
                payload = b"yjs-update"
                ws1.send_bytes(payload)
                assert ws2.receive_bytes() == payload
    app.dependency_overrides.clear()


def test_websocket_rooms_are_isolated():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token, doc_a = _setup_user_and_doc(client)
        _token, doc_b = _setup_user_and_doc(client)
        # Give the second user access to doc_b (they already own it, just reuse)
        # Use the same user for simplicity: create a second doc owned by same user
        # _setup_user_and_doc creates a fresh user each time, so reuse token for doc_b
        # Instead: create doc_b with the same token
        from app.models.workspace import Workspace
        import asyncio
        from app.tests.conftest import test_session_factory

        async def _make_ws() -> str:
            async with test_session_factory() as session:
                ws = Workspace(name="WS Workspace B")
                session.add(ws)
                await session.commit()
                await session.refresh(ws)
                return ws.workspace_id

        workspace_id = asyncio.get_event_loop().run_until_complete(_make_ws())
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post("/api/documents", json={
            "title": "Doc B",
            "workspace_id": workspace_id,
        }, headers=headers)
        assert resp.status_code == 201
        doc_b = resp.json()["document_id"]

        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/{doc_a}?token={token}") as ws_a:
            with client.websocket_connect(f"/ws/documents/{doc_b}?token={token}") as ws_b:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(ws_b.receive_bytes)
                    ws_a.send_bytes(b"isolated")
                    try:
                        future.result(timeout=0.2)
                        assert False, "Expected no binary message for a different room"
                    except TimeoutError:
                        pass
                    ws_b.close()
                    try:
                        future.result(timeout=1)
                    except Exception:
                        pass  # disconnect raises — that's expected
    app.dependency_overrides.clear()


def test_same_user_can_open_multiple_connections():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token, doc_id = _setup_user_and_doc(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws1:
            with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws2:
                with client.websocket_connect(f"/ws/documents/{doc_id}?token={token}") as ws3:
                    ws1.send_bytes(b"fanout")
                    assert ws2.receive_bytes() == b"fanout"
                    assert ws3.receive_bytes() == b"fanout"
    app.dependency_overrides.clear()
