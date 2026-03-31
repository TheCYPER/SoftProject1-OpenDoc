from concurrent.futures import ThreadPoolExecutor, TimeoutError

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_db
from app.main import app
from app.realtime import websocket as ws_router
from app.tests.conftest import _override_get_db


def _create_token(client: TestClient) -> str:
    resp = client.post("/api/auth/register", json={
        "email": "ws_test@example.com",
        "display_name": "WS Test",
        "password": "testpass123",
    })
    assert resp.status_code == 201

    resp = client.post("/api/auth/login", json={
        "email": "ws_test@example.com",
        "password": "testpass123",
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_websocket_rejects_invalid_token():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws/documents/doc-1?token=invalid"):
                assert False, "Expected websocket authentication failure"
        except WebSocketDisconnect as exc:
            assert exc.code == 4001
    app.dependency_overrides.clear()


def test_websocket_relays_binary_updates_between_clients():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token = _create_token(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/doc-1?token={token}") as ws1:
            with client.websocket_connect(f"/ws/documents/doc-1?token={token}") as ws2:
                payload = b"yjs-update"
                ws1.send_bytes(payload)
                assert ws2.receive_bytes() == payload
    app.dependency_overrides.clear()


def test_websocket_rooms_are_isolated():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token = _create_token(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/doc-a?token={token}") as ws_a:
            with client.websocket_connect(f"/ws/documents/doc-b?token={token}") as ws_b:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(ws_b.receive_bytes)
                    ws_a.send_bytes(b"isolated")
                    try:
                        future.result(timeout=0.2)
                        assert False, "Expected no binary message for a different room"
                    except TimeoutError:
                        pass
                    ws_b.close()
                    future.result(timeout=1)
    app.dependency_overrides.clear()


def test_same_user_can_open_multiple_connections():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        token = _create_token(client)
        ws_router._rooms.clear()
        with client.websocket_connect(f"/ws/documents/doc-1?token={token}") as ws1:
            with client.websocket_connect(f"/ws/documents/doc-1?token={token}") as ws2:
                with client.websocket_connect(f"/ws/documents/doc-1?token={token}") as ws3:
                    ws1.send_bytes(b"fanout")
                    assert ws2.receive_bytes() == b"fanout"
                    assert ws3.receive_bytes() == b"fanout"
    app.dependency_overrides.clear()
