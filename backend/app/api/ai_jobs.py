from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.ai_interaction import AIInteraction
from app.models.ai_suggestion import AISuggestion
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.user import User
from app.schemas.ai import AIJobApply, AIJobCreate, AIJobResponse, AISuggestionResponse
from app.services.ai.ai_service import run_ai_job
from app.services.permissions import check_document_access


async def _load_interaction_with_access(
    db: AsyncSession,
    job_id: str,
    user: User,
    required_role: str,
) -> AIInteraction:
    """Fetch an AIInteraction and ensure `user` has the role on its document.

    Raises 404 if the job does not exist, 403 if the caller lacks access.
    """
    result = await db.execute(
        select(AIInteraction).where(AIInteraction.interaction_id == job_id)
    )
    interaction = result.scalar_one_or_none()
    if interaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")
    await check_document_access(db, interaction.document_id, user, required_role=required_role)
    return interaction

router = APIRouter(tags=["ai"])
limiter = Limiter(key_func=get_remote_address)

# Per-user AI job quota (PoC: 50 jobs per user)
AI_JOB_QUOTA = 50


def _extract_text_from_content(content: dict | None, sel_from: int | None, sel_to: int | None) -> str:
    """Extract plain text from prosemirror-json content, optionally slicing by char range."""
    if not content:
        return ""
    parts: list[str] = []
    for node in content.get("content", []):
        for child in node.get("content", []):
            if child.get("type") == "text":
                parts.append(child.get("text", ""))
    full_text = "\n".join(parts)
    if sel_from is not None and sel_to is not None:
        return full_text[sel_from:sel_to]
    return full_text


async def _check_quota(db: AsyncSession, user_id: str) -> bool:
    """Return True if user is within their AI job quota."""
    result = await db.execute(
        select(func.count()).select_from(AIInteraction).where(
            AIInteraction.requested_by == user_id
        )
    )
    count = result.scalar_one()
    return count < AI_JOB_QUOTA


@router.post(
    "/api/documents/{document_id}/ai-jobs",
    response_model=AIJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an AI job against a document's content",
)
@limiter.limit("20/minute")
async def create_ai_job(
    request: Request,
    document_id: str,
    body: AIJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accepts actions such as rewrite/summarize/translate/restructure.
    Rate-limited to 20/min per client IP + 50 total jobs per user.
    Returns 202 with a `job_id` even when the suggestion is produced inline."""
    doc_result = await db.execute(
        select(Document).where(Document.document_id == document_id)
    doc = await check_document_access(
        db, document_id, current_user, required_role="editor"
    )

    # Quota check
    if not await _check_quota(db, current_user.user_id):
        interaction = AIInteraction(
            document_id=document_id,
            requested_by=current_user.user_id,
            action_type=body.action,
            scope_type=body.scope,
            base_revision_id=body.base_revision_id or doc.current_revision_id,
            model_profile=body.provider or "default",
            status="quota_exceeded",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)
        return AIJobResponse(
            job_id=interaction.interaction_id,
            status="quota_exceeded",
            created_at=interaction.created_at,
        )

    sel_from = body.selection_range.from_ if body.selection_range else None
    sel_to = body.selection_range.to if body.selection_range else None

    interaction = AIInteraction(
        document_id=document_id,
        requested_by=current_user.user_id,
        action_type=body.action,
        scope_type=body.scope,
        selection_from=sel_from,
        selection_to=sel_to,
        base_revision_id=body.base_revision_id or doc.current_revision_id,
        model_profile=body.provider or "default",
        status="running",
    )
    db.add(interaction)
    await db.flush()

    # Prefer text sent directly from the editor over extracting from saved content
    source_text = body.selected_text or _extract_text_from_content(doc.content, sel_from, sel_to)
    if not source_text.strip():
        interaction.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text found. Write some text or select text in the editor first.",
        )

    # Stale detection: if caller provided a base_revision_id that differs from current
    is_stale = (
        body.base_revision_id is not None
        and doc.current_revision_id is not None
        and body.base_revision_id != doc.current_revision_id
    )

    try:
        suggested_text = await run_ai_job(
            action=body.action,
            text=source_text,
            options=body.options,
            provider_name=body.provider,
            api_key=body.api_key,
            base_url=body.base_url,
        )
    except Exception as exc:
        interaction.status = "failed"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI provider error: {exc}",
        )

    suggestion = AISuggestion(
        interaction_id=interaction.interaction_id,
        original_text=source_text,
        suggested_text=suggested_text,
        disposition="pending",
        stale=is_stale,
    )
    db.add(suggestion)
    interaction.status = "stale" if is_stale else "ready"
    interaction.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(interaction)

    return AIJobResponse(
        job_id=interaction.interaction_id,
        status=interaction.status,
        created_at=interaction.created_at,
    )


@router.get(
    "/api/ai-jobs/{job_id}",
    response_model=AIJobResponse,
    summary="Fetch AI job status (running / ready / stale / failed)",
)
async def get_ai_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Viewer role on the job's document required."""
    result = await db.execute(
        select(AIInteraction).where(AIInteraction.interaction_id == job_id)
    interaction = await _load_interaction_with_access(
        db, job_id, current_user, required_role="viewer"
    )
    return AIJobResponse(
        job_id=interaction.interaction_id,
        status=interaction.status,
        created_at=interaction.created_at,
    )


@router.get(
    "/api/ai-jobs/{job_id}/suggestion",
    response_model=AISuggestionResponse,
    summary="Get the suggestion produced by an AI job",
)
async def get_suggestion(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Viewer role required. Includes original vs suggested text for diff UIs."""
    await _load_interaction_with_access(db, job_id, current_user, required_role="viewer")
    result = await db.execute(
        select(AISuggestion)
        .join(AIInteraction)
        .where(AIInteraction.interaction_id == job_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return suggestion


@router.post(
    "/api/ai-jobs/{job_id}/apply",
    status_code=status.HTTP_200_OK,
    summary="Accept an AI suggestion (full or partial)",
)
async def apply_suggestion(
    job_id: str,
    body: AIJobApply,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    interaction = await _load_interaction_with_access(
        db, job_id, current_user, required_role="editor"
    )
    result = await db.execute(
        select(AISuggestion).where(AISuggestion.interaction_id == interaction.interaction_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")

    doc_result = await db.execute(
        select(Document).where(Document.document_id == interaction.document_id)
    )
    doc = doc_result.scalar_one()

    suggestion.disposition = "accepted" if body.mode == "full" else "partially_applied"
    suggestion.applied_by = current_user.user_id
    suggestion.applied_at = datetime.now(timezone.utc)
    if body.selected_diff_blocks:
        suggestion.accepted_segments_json = {"blocks": body.selected_diff_blocks}

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=doc.document_id,
        actor_user_id=current_user.user_id,
        event_type="ai.suggestion.applied",
        target_ref=str(suggestion.suggestion_id),
        metadata_json={
            "job_id": job_id,
            "mode": body.mode,
            "action_type": interaction.action_type,
        },
    )
    db.add(audit)
    await db.commit()
    return {"status": "applied", "suggestion_id": str(suggestion.suggestion_id)}


@router.post(
    "/api/ai-jobs/{job_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="Reject an AI suggestion",
)
async def reject_suggestion(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    interaction = await _load_interaction_with_access(
        db, job_id, current_user, required_role="editor"
    )
    result = await db.execute(
        select(AISuggestion).where(AISuggestion.interaction_id == interaction.interaction_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")

    doc_result = await db.execute(
        select(Document).where(Document.document_id == interaction.document_id)
    )
    doc = doc_result.scalar_one()

    suggestion.disposition = "rejected"

    audit = AuditEvent(
        workspace_id=doc.workspace_id,
        document_id=doc.document_id,
        actor_user_id=current_user.user_id,
        event_type="ai.suggestion.rejected",
        target_ref=str(suggestion.suggestion_id),
        metadata_json={"job_id": job_id, "action_type": interaction.action_type},
    )
    db.add(audit)
    await db.commit()
    return {"status": "rejected"}
