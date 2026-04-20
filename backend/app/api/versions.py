import uuid

import pycrdt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.audit_event import AuditEvent
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.realtime.websocket import (
    MSG_SYNC,
    SYNC_UPDATE,
    _append_prosemirror_nodes,
    _rooms,
    _write_varuint8array,
    encode_prosemirror_json_to_yjs_state,
)
from app.schemas.document import VersionResponse
from app.services.permissions import check_document_access

router = APIRouter(tags=["versions"])


@router.get(
    "/api/documents/{document_id}/versions",
    response_model=list[VersionResponse],
    summary="List a document's version snapshots (newest first)",
)
async def list_versions(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Viewer role required (see RBAC matrix in README)."""
    await check_document_access(db, document_id, current_user, required_role="viewer")
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.created_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/api/documents/{document_id}/versions/{version_id}/restore",
    response_model=VersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Restore a previous version as a new snapshot",
)
async def restore_version(
    document_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Editor role required. Creates a new DocumentVersion row with
    reason='restore' linked to the original via `restored_from_version_id`.

    If a live CRDT room exists for this document, the restore is applied as a
    Yjs delete+insert on the authoritative room state and the resulting delta
    is broadcast to every connected WebSocket client. Without this step, REST
    writes to `documents.yjs_state` are invisible to clients — and the room's
    own `persist_to_db()` on disconnect would overwrite the restore.
    """
    doc = await check_document_access(
        db, document_id, current_user, required_role="editor"
    )

    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.version_id == version_id,
            DocumentVersion.document_id == document_id,
        )
    )
    old_version = result.scalar_one_or_none()
    if old_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    new_revision = f"rev_{uuid.uuid4().hex[:8]}"
    new_version = DocumentVersion(
        document_id=document_id,
        snapshot=old_version.snapshot,
        base_revision_id=new_revision,
        reason="restore",
        created_by=current_user.user_id,
        restored_from_version_id=version_id,
    )
    db.add(new_version)

    snapshot_content = (old_version.snapshot or {}).get("content")

    room = _rooms.get(document_id)
    update_delta = b""
    if room is not None:
        # Active collaboration session — edit the live ydoc, compute delta,
        # persist the post-edit full state so the DB stays in sync with the
        # room (the room.persist_to_db() on teardown writes the room's state).
        await room.load_from_db(db)
        fragment = room.ydoc["prosemirror"]
        state_before = bytes(room.ydoc.get_state())
        try:
            with room.ydoc.transaction():
                if len(fragment.children) > 0:
                    del fragment.children[:]
                _append_prosemirror_nodes(fragment, snapshot_content)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid snapshot: {exc}",
            ) from exc
        doc.yjs_state = bytes(room.ydoc.get_update())
        update_delta = bytes(room.ydoc.get_update(state_before))
    else:
        # No live room — DB is the only state we need to update. Encode the
        # snapshot into a fresh ydoc just like create/update do.
        try:
            doc.yjs_state = encode_prosemirror_json_to_yjs_state(old_version.snapshot)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Invalid snapshot: {exc}",
            ) from exc

    doc.content = old_version.snapshot
    doc.current_revision_id = new_revision

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=document_id,
        actor_user_id=current_user.user_id,
        event_type="version.restored",
        target_ref=version_id,
        metadata_json={"new_version_id": new_version.version_id, "new_revision": new_revision},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(new_version)

    # Broadcast AFTER commit so we never advertise a state we haven't
    # durably persisted. Clients that miss the broadcast (e.g. network
    # blip) will sync the restored state on their next reconnect.
    if update_delta and room is not None:
        message = bytes([MSG_SYNC, SYNC_UPDATE]) + _write_varuint8array(update_delta)
        dead: list[str] = []
        for conn_id, conn in list(room.connections.items()):
            try:
                await conn.websocket.send_bytes(message)
            except Exception:
                dead.append(conn_id)
        for conn_id in dead:
            room.connections.pop(conn_id, None)

    return new_version
