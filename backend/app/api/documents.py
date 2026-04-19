import html
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.document_share import DocumentShare
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.realtime.websocket import encode_prosemirror_json_to_yjs_state
from app.schemas.document import (
    DocumentCreate,
    DocumentListItem,
    DocumentResponse,
    DocumentUpdate,
)
from app.services.permissions import check_document_access

router = APIRouter(tags=["documents"])


@router.post(
    "/api/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new document",
    responses={401: {"description": "Not authenticated"}},
)
async def create_document(
    body: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a document owned by the caller with an initial version snapshot."""
    initial_revision = f"rev_{uuid.uuid4().hex[:8]}"
    initial_content = body.initial_content or {"type": "doc", "content": []}
    try:
        initial_yjs_state = encode_prosemirror_json_to_yjs_state(initial_content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    doc = Document(
        workspace_id=body.workspace_id,
        created_by=current_user.user_id,
        title=body.title,
        content=initial_content,
        yjs_state=initial_yjs_state,
        current_revision_id=initial_revision,
    )
    db.add(doc)
    await db.flush()

    version = DocumentVersion(
        document_id=doc.document_id,
        snapshot=doc.content,
        base_revision_id=initial_revision,
        reason="initial",
        created_by=current_user.user_id,
    )
    db.add(version)
    db.add(AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=doc.document_id,
        actor_user_id=current_user.user_id,
        event_type="document.created",
        target_ref=doc.document_id,
        metadata_json={"title": doc.title},
    ))
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get(
    "/api/documents",
    response_model=list[DocumentListItem],
    summary="List documents the caller can see",
)
async def list_documents(
    workspace_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns documents owned by the caller or shared with them (non-expired),
    excluding soft-deleted documents. Optional `workspace_id` filter."""
    now = datetime.now(timezone.utc)
    accessible_via_share = (
        select(DocumentShare.document_id)
        .where(
            DocumentShare.grantee_type == "USER",
            DocumentShare.grantee_ref == current_user.email,
            or_(
                DocumentShare.expires_at.is_(None),
                DocumentShare.expires_at > now,
            ),
        )
        .scalar_subquery()
    )
    query = (
        select(Document)
        .where(
            Document.status != "deleted",
            or_(
                Document.created_by == current_user.user_id,
                Document.document_id.in_(accessible_via_share),
            ),
        )
        .order_by(Document.updated_at.desc())
    )
    if workspace_id:
        query = query.where(Document.workspace_id == workspace_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/api/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Fetch a document",
    responses={403: {"description": "Access denied"}, 404: {"description": "Not found"}},
)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Requires viewer role. Response includes the caller's effective role."""
    return await check_document_access(db, document_id, current_user, required_role="viewer")


@router.patch(
    "/api/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Update a document (title/content/status)",
    responses={403: {"description": "Access denied"}, 404: {"description": "Not found"}},
)
async def update_document(
    document_id: str,
    body: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Requires editor role. A content change also creates a new version snapshot."""
    doc = await check_document_access(db, document_id, current_user, required_role="editor")

    update_data = body.model_dump(exclude_unset=True)
    version_reason = None
    next_yjs_state: bytes | None = None
    if "content" in update_data:
        try:
            next_yjs_state = encode_prosemirror_json_to_yjs_state(update_data["content"])
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        new_revision = f"rev_{uuid.uuid4().hex[:8]}"
        doc.current_revision_id = new_revision
        version_reason = "update"
    for field, value in update_data.items():
        setattr(doc, field, value)
    if next_yjs_state is not None:
        doc.yjs_state = next_yjs_state

    if version_reason is not None:
        db.add(DocumentVersion(
            document_id=doc.document_id,
            snapshot=doc.content,
            base_revision_id=doc.current_revision_id,
            reason=version_reason,
            created_by=current_user.user_id,
        ))
    if update_data:
        db.add(AuditEvent(
            workspace_id=doc.workspace_id,
            document_id=doc.document_id,
            actor_user_id=current_user.user_id,
            event_type="document.updated",
            target_ref=doc.document_id,
            metadata_json={"fields": sorted(update_data.keys())},
        ))

    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete(
    "/api/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a document (owner only)",
    responses={403: {"description": "Access denied"}, 404: {"description": "Not found"}},
)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marks status='deleted'; rows remain in the DB for audit."""
    doc = await check_document_access(db, document_id, current_user, required_role="owner")
    doc.status = "deleted"
    db.add(AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=doc.document_id,
        actor_user_id=current_user.user_id,
        event_type="document.deleted",
        target_ref=doc.document_id,
        metadata_json=None,
    ))
    await db.commit()


@router.get(
    "/api/documents/{document_id}/export",
    response_class=HTMLResponse,
    summary="Export a document as HTML or plain text",
)
async def export_document(
    document_id: str,
    format: str = Query(default="html", pattern="^(html|txt)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Renders the prosemirror-json content. `format=html` (default) or `txt`."""
    doc = await check_document_access(db, document_id, current_user, required_role="viewer")
    title = html.escape(doc.title)
    content = doc.content or {"type": "doc", "content": []}

    def node_to_html(node: dict) -> str:
        node_type = node.get("type", "")
        children = "".join(node_to_html(c) for c in node.get("content", []))
        text = html.escape(node.get("text", ""))
        marks = {m["type"] for m in node.get("marks", [])}
        if node_type == "text":
            if "bold" in marks:
                text = f"<strong>{text}</strong>"
            if "italic" in marks:
                text = f"<em>{text}</em>"
            if "code" in marks:
                text = f"<code>{text}</code>"
            return text
        if node_type == "paragraph":
            return f"<p>{children}</p>"
        if node_type == "heading":
            level = node.get("attrs", {}).get("level", 1)
            return f"<h{level}>{children}</h{level}>"
        if node_type == "bulletList":
            return f"<ul>{children}</ul>"
        if node_type == "orderedList":
            return f"<ol>{children}</ol>"
        if node_type == "listItem":
            return f"<li>{children}</li>"
        if node_type == "blockquote":
            return f"<blockquote>{children}</blockquote>"
        if node_type == "codeBlock":
            return f"<pre><code>{children}</code></pre>"
        if node_type == "horizontalRule":
            return "<hr/>"
        return children

    body_html = node_to_html(content)

    if format == "txt":
        import re
        plain = re.sub(r"<[^>]+>", "", body_html)
        return HTMLResponse(
            content=plain,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{doc.title}.txt"'},
        )

    page = (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        f"<style>body{{font-family:sans-serif;max-width:800px;margin:40px auto;padding:0 20px}}"
        f"</style></head><body><h1>{title}</h1>{body_html}</body></html>"
    )
    return HTMLResponse(
        content=page,
        headers={"Content-Disposition": f'attachment; filename="{doc.title}.html"'},
    )
