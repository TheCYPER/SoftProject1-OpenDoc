import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.document_share import DocumentShare
from app.models.user import User
from app.realtime.websocket import (
    CLOSE_FORBIDDEN,
    CLOSE_PERMISSION_REFRESH,
    close_document_sessions_for_user,
)
from app.schemas.document import (
    ShareCreate,
    ShareLinkCreate,
    ShareLinkCreateResponse,
    ShareLinkRedeemRequest,
    ShareLinkRedeemResponse,
    ShareResponse,
    ShareUpdate,
)
from app.services.permissions import check_document_access

router = APIRouter(tags=["shares"])

_USER_ROLES = {"viewer", "editor", "admin"}
_LINK_ROLES = {"viewer", "editor"}
_ROLE_LEVEL = {"viewer": 0, "editor": 1, "admin": 2}


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_user_share_ref(grantee_ref: str | None) -> str:
    if grantee_ref is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="grantee_ref is required for USER shares",
        )
    normalized = grantee_ref.strip()
    if (
        not normalized
        or " " in normalized
        or normalized.count("@") != 1
        or normalized.startswith("@")
        or normalized.endswith("@")
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="grantee_ref must be a valid email address",
        )
    return normalized


def _normalize_share_role(role: str, *, allow_admin: bool) -> str:
    normalized = role.strip().lower()
    allowed_roles = _USER_ROLES if allow_admin else _LINK_ROLES
    if normalized not in allowed_roles:
        expected = "'viewer' or 'editor'" if not allow_admin else "'viewer', 'editor', or 'admin'"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"role must be {expected}",
        )
    return normalized


def _normalize_future_expiry(expires_at: datetime | None) -> datetime | None:
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expires_at must be in the future",
        )
    return expires_at


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _pick_canonical_share(shares: list[DocumentShare]) -> DocumentShare:
    now = datetime.now(timezone.utc)

    def sort_key(share: DocumentShare) -> tuple[int, int, datetime, str]:
        expires_at = share.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        is_active = expires_at is None or expires_at > now
        created_at = share.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return (
            1 if is_active else 0,
            _ROLE_LEVEL.get(share.role, 0),
            created_at,
            share.share_id,
        )

    return max(shares, key=sort_key)


async def _find_user_shares(
    db: AsyncSession,
    *,
    document_id: str,
    grantee_ref: str,
) -> list[DocumentShare]:
    result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.document_id == document_id,
            DocumentShare.grantee_type == "USER",
            DocumentShare.grantee_ref == grantee_ref,
        )
    )
    return list(result.scalars().all())


async def _collapse_duplicate_user_shares(
    db: AsyncSession,
    shares: list[DocumentShare],
) -> DocumentShare | None:
    if not shares:
        return None
    canonical_share = _pick_canonical_share(shares)
    for duplicate_share in shares:
        if duplicate_share.share_id != canonical_share.share_id:
            await db.delete(duplicate_share)
    return canonical_share


async def _resolve_share_user_id(db: AsyncSession, share: DocumentShare) -> str | None:
    if share.grantee_type != "USER" or share.grantee_ref is None:
        return None
    result = await db.execute(select(User.user_id).where(User.email == share.grantee_ref))
    return result.scalar_one_or_none()


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
    if body.grantee_type.strip().upper() != "USER":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="grantee_type must be USER",
        )
    grantee_ref = _normalize_user_share_ref(body.grantee_ref)
    role = _normalize_share_role(body.role, allow_admin=True)
    expires_at = _normalize_future_expiry(body.expires_at)

    share = await _collapse_duplicate_user_shares(
        db,
        await _find_user_shares(
            db,
            document_id=document_id,
            grantee_ref=grantee_ref,
        ),
    )
    event_type = "share.created"
    previous_role = share.role if share is not None else None
    if share is None:
        share = DocumentShare(
            document_id=document_id,
            grantee_type="USER",
            grantee_ref=grantee_ref,
            role=role,
            allow_ai=body.allow_ai,
            expires_at=expires_at,
            created_by=current_user.user_id,
        )
        db.add(share)
        await db.flush()
    else:
        share.role = role
        share.allow_ai = body.allow_ai
        share.expires_at = expires_at
        event_type = "share.updated"

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=document_id,
        actor_user_id=current_user.user_id,
        event_type=event_type,
        target_ref=grantee_ref,
        metadata_json={"role": role, "grantee_type": "USER"},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(share)
    target_user_id = await _resolve_share_user_id(db, share)
    permissions_changed = event_type == "share.updated" and role != previous_role
    if target_user_id is not None and permissions_changed:
        await close_document_sessions_for_user(
            document_id,
            target_user_id,
            close_code=CLOSE_PERMISSION_REFRESH,
            reason="Share permissions updated",
        )
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

    if body.role is None and body.allow_ai is None and body.expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one share field to update",
        )

    previous_role = share.role
    changes: dict[str, dict[str, object | None]] = {}
    if body.role is not None:
        normalized_role = _normalize_share_role(
            body.role,
            allow_admin=share.grantee_type != "LINK",
        )
        if normalized_role != share.role:
            changes["role"] = {"from": share.role, "to": normalized_role}
            share.role = normalized_role
    if body.allow_ai is not None and body.allow_ai != share.allow_ai:
        changes["allow_ai"] = {"from": share.allow_ai, "to": body.allow_ai}
        share.allow_ai = body.allow_ai
    if body.expires_at is not None:
        normalized_expiry = _normalize_future_expiry(body.expires_at)
        if normalized_expiry != share.expires_at:
            changes["expires_at"] = {"from": share.expires_at, "to": normalized_expiry}
            share.expires_at = normalized_expiry

    if not changes:
        return share

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

    target_user_id = await _resolve_share_user_id(db, share)
    permissions_changed = body.role is not None and share.role != previous_role
    if target_user_id is not None and permissions_changed:
        await close_document_sessions_for_user(
            document_id,
            target_user_id,
            close_code=CLOSE_PERMISSION_REFRESH,
            reason="Share permissions updated",
        )
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
    target_user_id = await _resolve_share_user_id(db, share)
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
    if target_user_id is not None:
        await close_document_sessions_for_user(
            document_id,
            target_user_id,
            close_code=CLOSE_FORBIDDEN,
            reason="Share revoked",
        )


# ── Share by link — create / revoke / redeem ─────────────────────────────────


@router.post(
    "/api/documents/{document_id}/share-links",
    response_model=ShareLinkCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_share_link(
    document_id: str,
    body: ShareLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a one-time-display share link for this document.

    Only the document owner can create a link. The raw token is returned
    exactly once — the server only persists its sha256 hash, so revoked or
    lost tokens cannot be recovered.
    """
    doc = await check_document_access(
        db, document_id, current_user, required_role="owner"
    )
    role = _normalize_share_role(body.role, allow_admin=False)

    raw_token = secrets.token_urlsafe(32)
    expires_at = None
    if body.expires_in_hours is not None:
        if body.expires_in_hours <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expires_in_hours must be positive",
            )
        expires_at = datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)

    share = DocumentShare(
        document_id=document_id,
        grantee_type="LINK",
        grantee_ref=None,
        role=role,
        allow_ai=body.allow_ai,
        link_token_hash=_hash_token(raw_token),
        expires_at=expires_at,
        created_by=current_user.user_id,
    )
    db.add(share)
    await db.flush()

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=document_id,
        actor_user_id=current_user.user_id,
        event_type="share_link.created",
        target_ref=share.share_id,
        metadata_json={"role": role, "expires_in_hours": body.expires_in_hours},
    )
    db.add(audit)
    await db.commit()
    await db.refresh(share)

    return ShareLinkCreateResponse(
        share_id=share.share_id,
        token=raw_token,
        role=share.role,
        expires_at=share.expires_at,
    )


@router.delete(
    "/api/documents/{document_id}/share-links/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_share_link(
    document_id: str,
    share_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke a share link. Subsequent redeem attempts with the same token fail."""
    doc = await check_document_access(
        db, document_id, current_user, required_role="owner"
    )

    result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.share_id == share_id,
            DocumentShare.document_id == document_id,
            DocumentShare.grantee_type == "LINK",
        )
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found"
        )

    await db.delete(share)
    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=document_id,
        actor_user_id=current_user.user_id,
        event_type="share_link.revoked",
        target_ref=share_id,
        metadata_json=None,
    )
    db.add(audit)
    await db.commit()


@router.post("/api/shares/redeem", response_model=ShareLinkRedeemResponse)
async def redeem_share_link(
    body: ShareLinkRedeemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Claim a share link. Grants the calling user the link's role on the
    document by creating a USER share row so all downstream permission checks
    go through the existing `check_document_access` path unchanged.

    Deliberately returns a generic 404 for unknown/expired/revoked tokens so
    we don't leak whether a given token ever existed.
    """
    token_hash = _hash_token(body.token)
    result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.grantee_type == "LINK",
            DocumentShare.link_token_hash == token_hash,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share link invalid or revoked"
        )

    if link.expires_at is not None:
        expires = link.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Share link invalid or revoked",
            )

    # Fetch the document so we can attach the audit row to its workspace
    doc_result = await db.execute(
        select(Document).where(Document.document_id == link.document_id)
    )
    doc = doc_result.scalar_one_or_none()
    if doc is None or doc.status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share link invalid or revoked"
        )

    existing = await _collapse_duplicate_user_shares(
        db,
        await _find_user_shares(
            db,
            document_id=link.document_id,
            grantee_ref=current_user.email,
        ),
    )
    effective_role = link.role
    if existing is None:
        existing = DocumentShare(
            document_id=link.document_id,
            grantee_type="USER",
            grantee_ref=current_user.email,
            role=link.role,
            allow_ai=link.allow_ai,
            expires_at=link.expires_at,
            created_by=link.created_by,
        )
        db.add(existing)
    elif _is_expired(existing.expires_at):
        existing.role = link.role
        existing.allow_ai = link.allow_ai
        existing.expires_at = link.expires_at
    else:
        if _ROLE_LEVEL.get(link.role, 0) > _ROLE_LEVEL.get(existing.role, 0):
            existing.role = link.role
        existing.allow_ai = existing.allow_ai or link.allow_ai
        if existing.expires_at is None or link.expires_at is None:
            existing.expires_at = None
        elif link.expires_at > existing.expires_at:
            existing.expires_at = link.expires_at
    effective_role = existing.role

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=link.document_id,
        actor_user_id=current_user.user_id,
        event_type="share_link.redeemed",
        target_ref=link.share_id,
        metadata_json={"role": effective_role, "link_role": link.role},
    )
    db.add(audit)
    await db.commit()

    return ShareLinkRedeemResponse(document_id=link.document_id, role=effective_role)
