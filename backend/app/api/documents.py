import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.document import Document
from app.models.document_share import DocumentShare
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.schemas.document import (
    DocumentCreate,
    DocumentListItem,
    DocumentResponse,
    DocumentUpdate,
)
from app.services.permissions import check_document_access

router = APIRouter(tags=["documents"])


@router.post("/api/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    body: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    initial_revision = f"rev_{uuid.uuid4().hex[:8]}"
    doc = Document(
        workspace_id=body.workspace_id,
        created_by=current_user.user_id,
        title=body.title,
        content=body.initial_content or {"type": "doc", "content": []},
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
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/api/documents", response_model=list[DocumentListItem])
async def list_documents(
    workspace_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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


@router.get("/api/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await check_document_access(db, document_id, current_user, required_role="viewer")


@router.patch("/api/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    body: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await check_document_access(db, document_id, current_user, required_role="editor")

    update_data = body.model_dump(exclude_unset=True)
    version_reason = None
    if "content" in update_data:
        new_revision = f"rev_{uuid.uuid4().hex[:8]}"
        doc.current_revision_id = new_revision
        version_reason = "update"
    for field, value in update_data.items():
        setattr(doc, field, value)

    if version_reason is not None:
        db.add(DocumentVersion(
            document_id=doc.document_id,
            snapshot=doc.content,
            base_revision_id=doc.current_revision_id,
            reason=version_reason,
            created_by=current_user.user_id,
        ))

    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = await check_document_access(db, document_id, current_user, required_role="owner")
    doc.status = "deleted"
    await db.commit()
