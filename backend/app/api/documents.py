import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.schemas.document import (
    DocumentCreate,
    DocumentListItem,
    DocumentResponse,
    DocumentUpdate,
)

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
    query = select(Document).where(Document.status != "deleted")
    if workspace_id:
        query = query.where(Document.workspace_id == workspace_id)
    query = query.order_by(Document.updated_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/api/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.document_id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.patch("/api/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    body: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.document_id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(doc, field, value)

    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.document_id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    doc.status = "deleted"
    await db.commit()
