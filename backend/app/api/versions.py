import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.audit_event import AuditEvent
from app.models.document_version import DocumentVersion
from app.models.user import User
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
    reason='restore' linked to the original via `restored_from_version_id`."""
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
    return new_version
