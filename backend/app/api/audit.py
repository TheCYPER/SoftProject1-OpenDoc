from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.audit_event import AuditEvent
from app.models.user import User
from app.schemas.document import AuditEventResponse
from app.services.permissions import check_document_access

router = APIRouter(tags=["audit"])


@router.get(
    "/api/documents/{document_id}/audit",
    response_model=list[AuditEventResponse],
)
async def get_audit_trail(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the audit trail for a document. Requires owner access."""
    await check_document_access(db, document_id, current_user, required_role="owner")
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.document_id == document_id)
        .order_by(AuditEvent.created_at.desc())
    )
    return result.scalars().all()
