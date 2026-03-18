"""WebSocket stub for real-time collaboration.

Simple message relay between clients in the same document room.
No CRDT — just broadcasts JSON messages to all connected peers.
"""

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.config import settings

router = APIRouter()

# In-memory room management: document_id -> {user_id: WebSocket}
_rooms: dict[str, dict[str, WebSocket]] = {}


def _verify_token(token: str) -> str | None:
    """Return user_id if token is valid, else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


@router.websocket("/ws/documents/{document_id}")
async def document_websocket(websocket: WebSocket, document_id: str, token: str = ""):
    user_id = _verify_token(token)
    if user_id is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()

    # Join room
    if document_id not in _rooms:
        _rooms[document_id] = {}
    _rooms[document_id][user_id] = websocket

    await _broadcast(document_id, user_id, {
        "type": "presence.update",
        "user_id": user_id,
        "action": "joined",
    })

    try:
        while True:
            data = await websocket.receive_json()
            await _broadcast(document_id, user_id, {
                **data,
                "user_id": user_id,
            })
    except WebSocketDisconnect:
        pass
    finally:
        _rooms.get(document_id, {}).pop(user_id, None)
        if document_id in _rooms and not _rooms[document_id]:
            del _rooms[document_id]
        await _broadcast(document_id, user_id, {
            "type": "presence.update",
            "user_id": user_id,
            "action": "left",
        })


async def _broadcast(
    document_id: str,
    sender_id: str,
    message: dict[str, Any],
) -> None:
    """Send a message to all peers in the room except the sender."""
    room = _rooms.get(document_id, {})
    for uid, ws in list(room.items()):
        if uid != sender_id:
            try:
                await ws.send_json(message)
            except Exception:
                room.pop(uid, None)
