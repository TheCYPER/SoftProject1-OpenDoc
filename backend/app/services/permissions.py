"""Document access control helpers.

All access decisions for documents go through `check_document_access`.
Roles (viewer < editor < admin < owner) are checked against DocumentShare entries.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_share import DocumentShare
from app.models.user import User

# Role hierarchy — higher index means more permissions
_ROLE_LEVEL: dict[str, int] = {"viewer": 0, "editor": 1, "admin": 2}


async def check_document_access(
    db: AsyncSession,
    document_id: str,
    user: User,
    required_role: str = "viewer",
) -> Document:
    """Return the Document if `user` has at least `required_role` access.

    Pass ``required_role="owner"`` to restrict to the document creator only.

    Raises:
        404 — document does not exist or is deleted.
        403 — user lacks sufficient permissions.
    """
    result = await db.execute(select(Document).where(Document.document_id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if doc.created_by == user.user_id:
        return doc

    if required_role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the document owner can perform this action",
        )

    share_result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.document_id == document_id,
            DocumentShare.grantee_type == "USER",
            DocumentShare.grantee_ref == user.email,
        )
    )
    share = share_result.scalar_one_or_none()

    if share is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if share.expires_at is not None:
        expires = share.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Share has expired")

    if _ROLE_LEVEL.get(share.role, 0) < _ROLE_LEVEL.get(required_role, 0):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    return doc


async def check_document_access_by_user_id(
    db: AsyncSession,
    document_id: str,
    user_id: str,
) -> bool:
    """Boolean check used by the WebSocket handler (no User object available)."""
    user_result = await db.execute(select(User).where(User.user_id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return False
    try:
        await check_document_access(db, document_id, user, required_role="viewer")
        return True
    except HTTPException:
        return False
