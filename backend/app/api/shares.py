from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.audit_event import AuditEvent
from app.models.document_share import DocumentShare
from app.models.user import User
from app.schemas.document import ShareCreate, ShareResponse, ShareUpdate
from app.services.permissions import check_document_access

router = APIRouter(tags=["shares"])


@router.get(
    "/api/documents/{document_id}/shares",
    response_model=list[ShareResponse],
    summary="List all shares for a document (owner only)",
)
async def list_shares(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner role required. Returns USER and LINK grants alike."""
    await check_document_access(db, document_id, current_user, required_role="owner")
    result = await db.execute(
        select(DocumentShare).where(DocumentShare.document_id == document_id)
    )
    return result.scalars().all()


@router.post(
    "/api/documents/{document_id}/shares",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a user access to a document (owner only)",
)
async def create_share(
    document_id: str,
    body: ShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Creates a USER share keyed by email. Use the share-link endpoints for
    link-based sharing (grantee_type=LINK)."""
    doc = await check_document_access(db, document_id, current_user, required_role="owner")
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
    await db.flush()

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=document_id,
        actor_user_id=current_user.user_id,
        event_type="share.created",
        target_ref=body.grantee_ref,
        metadata_json={"role": body.role, "grantee_type": body.grantee_type},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(share)
    return share


@router.patch(
    "/api/documents/{document_id}/shares/{share_id}",
    response_model=ShareResponse,
    summary="Update a share's role / expiry / AI flag (owner only)",
)
async def update_share(
    document_id: str,
    share_id: str,
    body: ShareUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Any non-null field is applied. Changes recorded in `audit_events`."""
    doc = await check_document_access(db, document_id, current_user, required_role="owner")
    result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.share_id == share_id,
            DocumentShare.document_id == document_id,
        )
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")

    changes: dict = {}
    if body.role is not None:
        changes["role"] = {"from": share.role, "to": body.role}
        share.role = body.role
    if body.allow_ai is not None:
        share.allow_ai = body.allow_ai
    if body.expires_at is not None:
        share.expires_at = body.expires_at

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=document_id,
        actor_user_id=current_user.user_id,
        event_type="share.updated",
        target_ref=share.grantee_ref,
        metadata_json={"share_id": share_id, "changes": changes},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(share)
    return share


@router.delete(
    "/api/documents/{document_id}/shares/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a share (owner only)",
)
async def delete_share(
    document_id: str,
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hard-deletes the share row; the grantee immediately loses access."""
    doc = await check_document_access(db, document_id, current_user, required_role="owner")
    result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.share_id == share_id,
            DocumentShare.document_id == document_id,
        )
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")

    grantee_ref = share.grantee_ref
    await db.delete(share)

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=document_id,
        actor_user_id=current_user.user_id,
        event_type="share.deleted",
        target_ref=grantee_ref,
        metadata_json={"share_id": share_id},
    )
    db.add(audit)
    await db.commit()
