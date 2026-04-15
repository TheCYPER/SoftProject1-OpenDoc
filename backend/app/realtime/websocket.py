"""Yjs-aware WebSocket server for real-time collaboration.

Maintains authoritative CRDT document state on the server using pycrdt.
Clients sync via the standard y-protocols sync/awareness protocol.
The server intercepts Yjs updates to maintain state, and provides full
document state to newly connecting clients.

Lifecycle additions vs. the initial relay implementation:
- Server tracks `user_id` per connection and emits a JSON `presence_leave`
  control frame when a client disconnects, so peers can prune their
  awareness state without waiting for the Yjs heartbeat to expire.
- `receive()` is wrapped in an asyncio.wait_for so idle connections drop
  after WS_IDLE_TIMEOUT_SECONDS instead of hanging indefinitely.
- Close codes are explicit (4401 auth, 4403 forbidden, 1000 normal) so
  the client can distinguish reconnect-worthy failures from terminal ones.
- Viewer-role users that send an edit frame receive a JSON `error` frame
  with code "READ_ONLY" instead of being silently dropped.
- Yjs state is persisted periodically (every WS_PERSIST_INTERVAL_UPDATES
  applied updates) in addition to the existing "flush on room empty", so
  edits survive a server crash mid-session.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import pycrdt

from app.api.deps import get_db
from app.config import settings
from app.database import async_session_factory
from app.models.document import Document
from app.services.permissions import check_document_access_by_user_id

logger = logging.getLogger(__name__)
router = APIRouter()

# ── y-protocols constants ────────────────────────────────────────────────────
MSG_SYNC = 0
MSG_AWARENESS = 1

SYNC_STEP1 = 0
SYNC_STEP2 = 1
SYNC_UPDATE = 2

# ── explicit close codes ─────────────────────────────────────────────────────
CLOSE_AUTH_REQUIRED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_INTERNAL_ERROR = 1011


# ── lib0 varint helpers (compatible with y-protocols encoding) ───────────────

def _read_varuint(data: bytes, offset: int) -> tuple[int, int]:
    """Read a lib0 varuint from data at offset. Returns (value, new_offset)."""
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, offset
        shift += 7
    return result, offset


def _write_varuint(value: int) -> bytes:
    """Write a lib0 varuint."""
    buf = bytearray()
    while value > 0x7F:
        buf.append((value & 0x7F) | 0x80)
        value >>= 7
    buf.append(value & 0x7F)
    return bytes(buf)


def _read_varuint8array(data: bytes, offset: int) -> tuple[bytes, int]:
    """Read a lib0 varuint-length-prefixed byte array."""
    length, offset = _read_varuint(data, offset)
    return data[offset:offset + length], offset + length


def _write_varuint8array(data: bytes) -> bytes:
    """Write a lib0 varuint-length-prefixed byte array."""
    return _write_varuint(len(data)) + data


# ── Connection / Room ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Connection:
    """A single client attached to a Room.

    Frozen so the dict slot is swapped wholesale rather than mutated — keeps
    with the project's immutability preference.
    """

    websocket: WebSocket
    user_id: str


class Room:
    """Holds the authoritative pycrdt.Doc and connected clients for one document."""

    __slots__ = ("document_id", "ydoc", "connections", "_loaded", "_updates_since_flush")

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        self.ydoc = pycrdt.Doc()
        # Pre-register the prosemirror XmlFragment so pycrdt knows the type
        self.ydoc["prosemirror"] = pycrdt.XmlFragment()
        self.connections: dict[str, Connection] = {}
        self._loaded = False
        self._updates_since_flush = 0

    async def load_from_db(self, db: AsyncSession) -> None:
        """Load saved Yjs state from database, or initialize empty."""
        if self._loaded:
            return
        result = await db.execute(
            select(Document.yjs_state)
            .where(Document.document_id == self.document_id)
        )
        row = result.one_or_none()
        if row and row[0] is not None:
            try:
                self.ydoc.apply_update(row[0])
            except Exception:
                logger.warning("Failed to apply saved yjs_state for %s", self.document_id)
        self._loaded = True

    async def persist_to_db(self) -> None:
        """Save the current Yjs binary state to the database."""
        state = bytes(self.ydoc.get_update())
        async with async_session_factory() as db:
            result = await db.execute(
                select(Document).where(Document.document_id == self.document_id)
            )
            doc = result.scalar_one_or_none()
            if doc is not None:
                doc.yjs_state = state
                await db.commit()
        self._updates_since_flush = 0

    def encode_sync_step1(self) -> bytes:
        """Create a SyncStep1 message (state vector) to send to a new client."""
        state_vector = bytes(self.ydoc.get_state())
        return bytes([MSG_SYNC, SYNC_STEP1]) + _write_varuint8array(state_vector)

    def encode_sync_step2(self) -> bytes:
        """Create a SyncStep2 message (full doc update) to send to a new client."""
        update = bytes(self.ydoc.get_update())
        return bytes([MSG_SYNC, SYNC_STEP2]) + _write_varuint8array(update)


# Global room registry
_rooms: dict[str, Room] = {}


def _get_or_create_room(document_id: str) -> Room:
    if document_id not in _rooms:
        _rooms[document_id] = Room(document_id)
    return _rooms[document_id]


# ── Auth helper ──────────────────────────────────────────────────────────────

def _verify_token(token: str) -> str | None:
    """Return user_id if token is a valid *access* token, else None.

    Refresh tokens carry type="refresh" and are rejected here so they cannot
    be used to join a WebSocket session.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    # Tokens issued before the type claim existed are treated as access tokens.
    token_type = payload.get("type", "access")
    if token_type != "access":
        return None
    return payload.get("sub")


# ── Broadcast helpers ────────────────────────────────────────────────────────

async def _broadcast_bytes(room: Room, sender_id: str, data: bytes) -> None:
    """Send binary message to every connection except `sender_id`. Clean up
    connections that error out mid-send."""
    dead: list[str] = []
    for conn_id, conn in room.connections.items():
        if conn_id == sender_id:
            continue
        try:
            await conn.websocket.send_bytes(data)
        except Exception:
            dead.append(conn_id)
    for conn_id in dead:
        room.connections.pop(conn_id, None)


async def _broadcast_text(room: Room, sender_id: str | None, payload: dict) -> None:
    """Send a JSON control frame to every connection (optionally excluding sender)."""
    serialized = json.dumps(payload)
    dead: list[str] = []
    for conn_id, conn in room.connections.items():
        if sender_id is not None and conn_id == sender_id:
            continue
        try:
            await conn.websocket.send_text(serialized)
        except Exception:
            dead.append(conn_id)
    for conn_id in dead:
        room.connections.pop(conn_id, None)


async def _send_text_safe(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_text(json.dumps(payload))
    except Exception:
        pass


# ── WebSocket endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws/documents/{document_id}")
async def document_websocket(
    websocket: WebSocket,
    document_id: str,
    token: str = "",
    db: AsyncSession = Depends(get_db),
) -> None:
    # ── Auth ──
    user_id = _verify_token(token)
    if user_id is None:
        await websocket.close(code=CLOSE_AUTH_REQUIRED, reason="Authentication required")
        return

    has_access = await check_document_access_by_user_id(db, document_id, user_id, required_role="viewer")
    if not has_access:
        await websocket.close(code=CLOSE_FORBIDDEN, reason="Access denied")
        return
    can_edit = await check_document_access_by_user_id(db, document_id, user_id, required_role="editor")

    await websocket.accept()
    connection_id = str(uuid.uuid4())

    # ── Join room ──
    room = _get_or_create_room(document_id)
    await room.load_from_db(db)
    room.connections[connection_id] = Connection(websocket=websocket, user_id=user_id)

    # ── Send server state to the new client ──
    try:
        await websocket.send_bytes(room.encode_sync_step1())
        await websocket.send_bytes(room.encode_sync_step2())
    except Exception:
        room.connections.pop(connection_id, None)
        return

    idle_timeout = settings.WS_IDLE_TIMEOUT_SECONDS
    persist_threshold = settings.WS_PERSIST_INTERVAL_UPDATES

    # ── Message loop ──
    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=idle_timeout
                )
            except asyncio.TimeoutError:
                logger.debug("Idle timeout for connection %s", connection_id)
                await websocket.close(code=1000, reason="Idle timeout")
                break

            if message.get("type") == "websocket.disconnect":
                break

            raw = message.get("bytes")
            if raw is None:
                # Text frames from clients (ping/control) — ignore; only the
                # server emits text frames today.
                continue
            if len(raw) < 2:
                continue

            msg_type = raw[0]

            if msg_type == MSG_SYNC:
                sync_type = raw[1]

                if sync_type == SYNC_STEP1:
                    try:
                        client_sv, _ = _read_varuint8array(raw, 2)
                        diff = bytes(room.ydoc.get_update(client_sv)) if client_sv else bytes(room.ydoc.get_update())
                    except Exception:
                        diff = bytes(room.ydoc.get_update())
                    reply = bytes([MSG_SYNC, SYNC_STEP2]) + _write_varuint8array(diff)
                    await websocket.send_bytes(reply)

                elif sync_type == SYNC_STEP2 or sync_type == SYNC_UPDATE:
                    if not can_edit:
                        await _send_text_safe(websocket, {
                            "type": "error",
                            "code": "READ_ONLY",
                            "detail": "Viewer role cannot send document updates",
                        })
                        continue
                    try:
                        update_data, _ = _read_varuint8array(raw, 2)
                        if update_data:
                            room.ydoc.apply_update(update_data)
                            room._updates_since_flush += 1
                    except Exception:
                        logger.debug("Failed to apply update from client", exc_info=True)
                    await _broadcast_bytes(room, connection_id, raw)

                    # Periodic flush so crashes don't discard in-flight edits
                    if room._updates_since_flush >= persist_threshold:
                        try:
                            await room.persist_to_db()
                        except Exception:
                            logger.exception(
                                "Failed periodic persist for %s", document_id
                            )

            elif msg_type == MSG_AWARENESS:
                await _broadcast_bytes(room, connection_id, raw)

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        logger.exception("WebSocket error for document %s", document_id)
    finally:
        # ── Leave room ──
        leaving = room.connections.pop(connection_id, None)

        # Let peers prune awareness for this user immediately.
        if leaving is not None and room.connections:
            await _broadcast_text(room, None, {
                "type": "presence_leave",
                "user_id": leaving.user_id,
                "connection_id": connection_id,
            })

        # If room is empty, persist and clean up
        if not room.connections:
            try:
                await room.persist_to_db()
            except Exception:
                logger.exception("Failed to persist room state for %s", document_id)
            _rooms.pop(document_id, None)
