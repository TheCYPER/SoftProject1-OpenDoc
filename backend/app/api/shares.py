from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.document_share import DocumentShare
from app.models.user import User
from app.schemas.document import ShareCreate, ShareResponse
from app.services.permissions import check_document_access

router = APIRouter(tags=["shares"])


@router.get("/api/documents/{document_id}/shares", response_model=list[ShareResponse])
async def list_shares(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await check_document_access(db, document_id, current_user, required_role="owner")
    result = await db.execute(
        select(DocumentShare).where(DocumentShare.document_id == document_id)
    )
    return result.scalars().all()


@router.post(
    "/api/documents/{document_id}/shares",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_share(
    document_id: str,
    body: ShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await check_document_access(db, document_id, current_user, required_role="owner")
    share = DocumentShare(
        document_id=document_id,
        grantee_type=body.grantee_type,
        grantee_ref=body.grantee_ref,
        role=body.role,
        allow_ai=body.allow_ai,
        expires_at=body.expires_at,
        created_by=current_user.user_id,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


@router.delete(
    "/api/documents/{document_id}/shares/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_share(
    document_id: str,
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await check_document_access(db, document_id, current_user, required_role="owner")
    result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.share_id == share_id,
            DocumentShare.document_id == document_id,
        )
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
    await db.delete(share)
    await db.commit()
