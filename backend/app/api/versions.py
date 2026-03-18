import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.schemas.document import VersionResponse

router = APIRouter(tags=["versions"])


@router.get(
    "/api/documents/{document_id}/versions",
    response_model=list[VersionResponse],
)
async def list_versions(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
)
async def restore_version(
    document_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.version_id == version_id,
            DocumentVersion.document_id == document_id,
        )
    )
    old_version = result.scalar_one_or_none()
    if old_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    doc_result = await db.execute(
        select(Document).where(Document.document_id == document_id)
    )
    doc = doc_result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

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
    await db.commit()
    await db.refresh(new_version)
    return new_version
