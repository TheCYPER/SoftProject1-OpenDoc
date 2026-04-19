"""Yjs-aware WebSocket server for real-time collaboration.

Maintains authoritative CRDT document state on the server using pycrdt.
Clients sync via the standard y-protocols sync/awareness protocol.
The server intercepts Yjs updates to maintain state, and provides full
document state to newly connecting clients.

Lifecycle additions vs. the initial relay implementation:
- Server tracks `user_id` per connection and the latest awareness state per
  Yjs client id, so newcomers receive current presence immediately.
- Disconnects broadcast both a Yjs awareness-null update and a JSON
  `presence_leave` control frame, so peers can prune ghost cursors without
  waiting for the awareness timeout.
- `receive()` is wrapped in an asyncio.wait_for so idle connections drop
  after WS_IDLE_TIMEOUT_SECONDS instead of hanging indefinitely.
- Close codes are explicit (4401 auth, 4403 forbidden, 4408 permission
  refresh, 1000 normal) so the client can distinguish reconnect-worthy
  failures from terminal ones.
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
from dataclasses import dataclass, replace
from typing import Any

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
CLOSE_PERMISSION_REFRESH = 4408
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


def _mark_attributes_from_prosemirror(
    marks: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    yjs_attrs: dict[str, dict[str, Any]] = {}
    for mark in marks or []:
        if not isinstance(mark, dict):
            raise ValueError("Text marks must be objects")
        mark_type = mark.get("type")
        if not isinstance(mark_type, str) or not mark_type:
            raise ValueError("Text marks require a type")
        mark_attrs = mark.get("attrs") or {}
        if not isinstance(mark_attrs, dict):
            raise ValueError("Text mark attrs must be an object")
        yjs_attrs[mark_type] = mark_attrs
    return yjs_attrs


def _append_prosemirror_nodes(
    parent: pycrdt.XmlFragment | pycrdt.XmlElement,
    nodes: list[dict[str, Any]] | None,
) -> None:
    if nodes is None:
        return
    if not isinstance(nodes, list):
        raise ValueError("Document content must be a list of nodes")

    index = 0
    while index < len(nodes):
        node = nodes[index]
        if not isinstance(node, dict):
            raise ValueError("Document nodes must be objects")

        node_type = node.get("type")
        if not isinstance(node_type, str) or not node_type:
            raise ValueError("Document nodes require a type")

        if node_type == "text":
            text_node = pycrdt.XmlText()
            parent.children.append(text_node)
            text_offset = 0
            while index < len(nodes):
                current = nodes[index]
                if not isinstance(current, dict) or current.get("type") != "text":
                    break
                text_value = current.get("text", "")
                if text_value is None:
                    text_value = ""
                if not isinstance(text_value, str):
                    raise ValueError("Text node text must be a string")
                if text_value:
                    mark_attrs = _mark_attributes_from_prosemirror(current.get("marks"))
                    text_node.insert(text_offset, text_value, mark_attrs or None)
                    text_offset += len(text_value)
                index += 1
            continue

        attrs = node.get("attrs") or {}
        if not isinstance(attrs, dict):
            raise ValueError(f"{node_type} attrs must be an object")

        element = pycrdt.XmlElement(node_type)
        parent.children.append(element)
        for key, value in attrs.items():
            if value is not None:
                element.attributes[str(key)] = value
        _append_prosemirror_nodes(element, node.get("content"))
        index += 1


def encode_prosemirror_json_to_yjs_state(content: dict[str, Any] | None) -> bytes:
    """Encode ProseMirror JSON into Yjs update bytes.

    REST writes use this to keep `documents.content` and `documents.yjs_state`
    representing the same document tree.
    """
    normalized_content = content or {"type": "doc", "content": []}
    if not isinstance(normalized_content, dict):
        raise ValueError("Document content must be a ProseMirror JSON object")
    if normalized_content.get("type") != "doc":
        raise ValueError("Document content root must be a ProseMirror doc node")

    ydoc = pycrdt.Doc()
    ydoc["prosemirror"] = pycrdt.XmlFragment()
    fragment = ydoc["prosemirror"]
    _append_prosemirror_nodes(fragment, normalized_content.get("content"))
    return bytes(ydoc.get_update())


def _read_varstring(data: bytes, offset: int) -> tuple[str, int]:
    raw, offset = _read_varuint8array(data, offset)
    return raw.decode("utf-8"), offset


def _write_varstring(value: str) -> bytes:
    raw = value.encode("utf-8")
    return _write_varuint8array(raw)


def _decode_awareness_payload(raw: bytes) -> tuple[bytes, int]:
    return _read_varuint8array(raw, 1)


def _parse_awareness_entries(payload: bytes) -> list[tuple[int, int, object | None]]:
    offset = 0
    count, offset = _read_varuint(payload, offset)
    entries: list[tuple[int, int, object | None]] = []
    for _ in range(count):
        client_id, offset = _read_varuint(payload, offset)
        clock, offset = _read_varuint(payload, offset)
        state_json, offset = _read_varstring(payload, offset)
        entries.append((client_id, clock, json.loads(state_json)))
    return entries


def _encode_awareness_update(entries: list[tuple[int, int, object | None]]) -> bytes:
    encoded = bytearray()
    encoded.extend(_write_varuint(len(entries)))
    for client_id, clock, state in entries:
        encoded.extend(_write_varuint(client_id))
        encoded.extend(_write_varuint(clock))
        encoded.extend(_write_varstring(json.dumps(state)))
    return bytes(encoded)


def _encode_awareness_message(entries: list[tuple[int, int, object | None]]) -> bytes:
    payload = _encode_awareness_update(entries)
    return bytes([MSG_AWARENESS]) + _write_varuint8array(payload)


# ── Connection / Room ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Connection:
    """A single client attached to a Room.

    Frozen so the dict slot is swapped wholesale rather than mutated — keeps
    with the project's immutability preference.
    """

    websocket: WebSocket
    user_id: str
    awareness_client_ids: frozenset[int] = frozenset()


class Room:
    """Holds the authoritative pycrdt.Doc and connected clients for one document."""

    __slots__ = (
        "document_id",
        "ydoc",
        "connections",
        "awareness_states",
        "_loaded",
        "_updates_since_flush",
    )

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id
        self.ydoc = pycrdt.Doc()
        # Pre-register the prosemirror XmlFragment so pycrdt knows the type
        self.ydoc["prosemirror"] = pycrdt.XmlFragment()
        self.connections: dict[str, Connection] = {}
        self.awareness_states: dict[int, tuple[int, object | None]] = {}
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

    def encode_awareness_snapshot(self) -> bytes | None:
        active_entries = [
            (client_id, clock, state)
            for client_id, (clock, state) in self.awareness_states.items()
            if state is not None
        ]
        if not active_entries:
            return None
        return _encode_awareness_message(active_entries)


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
        connection = room.connections.get(conn_id)
        if connection is None:
            continue
        try:
            await connection.websocket.close()
        except Exception:
            pass


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
        connection = room.connections.get(conn_id)
        if connection is None:
            continue
        try:
            await connection.websocket.close()
        except Exception:
            pass


async def _send_text_safe(websocket: WebSocket, payload: dict) -> None:
    try:
        await websocket.send_text(json.dumps(payload))
    except Exception:
        pass


def _remember_awareness(room: Room, connection_id: str, raw: bytes) -> None:
    payload, _ = _decode_awareness_payload(raw)
    entries = _parse_awareness_entries(payload)
    connection = room.connections.get(connection_id)
    if connection is None:
        return

    next_client_ids = set(connection.awareness_client_ids)
    for client_id, clock, state in entries:
        if state is None:
            room.awareness_states.pop(client_id, None)
            next_client_ids.discard(client_id)
            continue
        room.awareness_states[client_id] = (clock, state)
        next_client_ids.add(client_id)

    room.connections[connection_id] = replace(
        connection,
        awareness_client_ids=frozenset(next_client_ids),
    )


def _prune_connection_awareness(
    room: Room,
    connection: Connection | None,
) -> list[tuple[int, int, object | None]]:
    if connection is None:
        return []

    removals: list[tuple[int, int, object | None]] = []
    for client_id in connection.awareness_client_ids:
        stored = room.awareness_states.pop(client_id, None)
        if stored is None:
            continue
        clock, _state = stored
        removals.append((client_id, clock, None))
    return removals


async def close_document_sessions_for_user(
    document_id: str,
    user_id: str,
    *,
    close_code: int = CLOSE_FORBIDDEN,
    reason: str = "Access revoked",
) -> int:
    room = _rooms.get(document_id)
    if room is None:
        return 0

    matching_connections = [
        connection
        for connection in room.connections.values()
        if connection.user_id == user_id
    ]
    for connection in matching_connections:
        try:
            await connection.websocket.close(code=close_code, reason=reason)
        except Exception:
            logger.debug("Failed closing revoked websocket", exc_info=True)
    return len(matching_connections)


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
        awareness_snapshot = room.encode_awareness_snapshot()
        if awareness_snapshot is not None:
            await websocket.send_bytes(awareness_snapshot)
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
                try:
                    _remember_awareness(room, connection_id, raw)
                except Exception:
                    logger.debug("Failed to decode awareness payload", exc_info=True)
                await _broadcast_bytes(room, connection_id, raw)

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        logger.exception("WebSocket error for document %s", document_id)
    finally:
        # ── Leave room ──
        leaving = room.connections.pop(connection_id, None)
        awareness_removals = _prune_connection_awareness(room, leaving)

        # Let peers prune awareness for this user immediately.
        if leaving is not None and room.connections:
            if awareness_removals:
                await _broadcast_bytes(
                    room,
                    connection_id,
                    _encode_awareness_message(awareness_removals),
                )
            await _broadcast_text(room, None, {
                "type": "presence_leave",
                "user_id": leaving.user_id,
                "connection_id": connection_id,
                "client_ids": [client_id for client_id, _clock, _state in awareness_removals],
            })

        # If room is empty, persist and clean up
        if not room.connections:
            try:
                await room.persist_to_db()
            except Exception:
                logger.exception("Failed to persist room state for %s", document_id)
            _rooms.pop(document_id, None)
