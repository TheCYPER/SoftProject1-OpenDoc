"""WebSocket auth edge cases.

test_realtime.py covers the happy path + invalid-token + refresh-token
rejection. This file targets the remaining auth branches:
- empty token query param
- JWT with bogus signature
- JWT with no `sub` claim
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_db
from app.config import settings
from app.main import app
from app.realtime import websocket as ws_router
from app.tests.conftest import _override_get_db


def test_missing_token_is_rejected():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws/documents/any-id"):
                assert False, "Expected auth failure with no token"
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
    app.dependency_overrides.clear()


def test_empty_token_is_rejected():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws/documents/any-id?token="):
                assert False, "Expected auth failure with empty token"
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
    app.dependency_overrides.clear()


def test_token_signed_with_wrong_secret_is_rejected():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        bad_token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            "not-the-real-secret",
            algorithm=settings.ALGORITHM,
        )
        try:
            with client.websocket_connect(
                f"/ws/documents/any-id?token={bad_token}"
            ):
                assert False, "Expected auth failure with bad signature"
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
    app.dependency_overrides.clear()


def test_token_missing_sub_is_rejected():
    """A signed token without a `sub` claim should be rejected."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        no_sub = jwt.encode(
            {
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        try:
            with client.websocket_connect(
                f"/ws/documents/any-id?token={no_sub}"
            ):
                assert False, "Expected auth failure with missing sub"
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
    app.dependency_overrides.clear()


def test_expired_access_token_is_rejected():
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        expired = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "type": "access",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        try:
            with client.websocket_connect(
                f"/ws/documents/any-id?token={expired}"
            ):
                assert False, "Expected auth failure with expired token"
        except WebSocketDisconnect as exc:
            assert exc.code == 4401
    app.dependency_overrides.clear()


def test_valid_token_for_nonexistent_document_rejected():
    """A token for an authenticated but non-existent document → 4403."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        # Register & login to get a real access token
        resp = client.post("/api/auth/register", json={
            "email": f"ws_auth_{uuid.uuid4().hex[:6]}@example.com",
            "display_name": "WS Auth",
            "password": "pw",
        })
        assert resp.status_code == 201
        resp = client.post("/api/auth/login", json={
            "email": resp.json()["email"],
            "password": "pw",
        })
        token = resp.json()["access_token"]
        ws_router._rooms.clear()

        try:
            with client.websocket_connect(
                f"/ws/documents/nonexistent-doc-id?token={token}"
            ):
                assert False, "Expected forbidden on nonexistent doc"
        except WebSocketDisconnect as exc:
            assert exc.code == 4403
    app.dependency_overrides.clear()
