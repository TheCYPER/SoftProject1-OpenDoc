"""WebSocket handler for real-time collaboration.

Binary message relay between clients in the same document room.
Yjs handles CRDT merging on the clients; the backend authenticates, checks
document access, and relays updates.
"""

import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import settings
from app.services.permissions import check_document_access_by_user_id

router = APIRouter()

# In-memory room management: document_id -> {connection_id: WebSocket}
_rooms: dict[str, dict[str, WebSocket]] = {}


def _verify_token(token: str) -> str | None:
    """Return user_id if token is valid, else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


@router.websocket("/ws/documents/{document_id}")
async def document_websocket(
    websocket: WebSocket,
    document_id: str,
    token: str = "",
    db: AsyncSession = Depends(get_db),
):
    user_id = _verify_token(token)
    if user_id is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    has_access = await check_document_access_by_user_id(db, document_id, user_id)
    if not has_access:
        await websocket.close(code=4003, reason="Access denied")
        return

    await websocket.accept()
    connection_id = str(uuid.uuid4())

    if document_id not in _rooms:
        _rooms[document_id] = {}
    _rooms[document_id][connection_id] = websocket

    try:
        while True:
            message = await websocket.receive()
            data = message.get("bytes")
            if data is None:
                if message.get("text") is not None:
                    await websocket.close(code=1003, reason="Binary websocket frames only")
                    return
                continue
            await _broadcast(document_id, connection_id, data)
    except WebSocketDisconnect:
        pass
    finally:
        _rooms.get(document_id, {}).pop(connection_id, None)
        if document_id in _rooms and not _rooms[document_id]:
            del _rooms[document_id]


async def _broadcast(
    document_id: str,
    sender_connection_id: str,
    message: bytes,
) -> None:
    """Send a message to all peers in the room except the sender."""
    room = _rooms.get(document_id, {})
    for connection_id, ws in list(room.items()):
        if connection_id != sender_connection_id:
            try:
                await ws.send_bytes(message)
            except Exception:
                room.pop(connection_id, None)
