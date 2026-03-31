from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.ai_interaction import AIInteraction
from app.models.ai_suggestion import AISuggestion
from app.models.document import Document
from app.models.user import User
from app.schemas.ai import AIJobApply, AIJobCreate, AIJobResponse, AISuggestionResponse
from app.services.ai.ai_service import run_ai_job

router = APIRouter(tags=["ai"])


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


@router.post(
    "/api/documents/{document_id}/ai-jobs",
    response_model=AIJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_ai_job(
    document_id: str,
    body: AIJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc_result = await db.execute(
        select(Document).where(Document.document_id == document_id)
    )
    doc = doc_result.scalar_one_or_none()
    if doc is None or doc.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

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
    )
    db.add(suggestion)
    interaction.status = "ready"
    interaction.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(interaction)

    return AIJobResponse(
        job_id=interaction.interaction_id,
        status=interaction.status,
        created_at=interaction.created_at,
    )


@router.get("/api/ai-jobs/{job_id}", response_model=AIJobResponse)
async def get_ai_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AIInteraction).where(AIInteraction.interaction_id == job_id)
    )
    interaction = result.scalar_one_or_none()
    if interaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")
    return AIJobResponse(
        job_id=interaction.interaction_id,
        status=interaction.status,
        created_at=interaction.created_at,
    )


@router.get("/api/ai-jobs/{job_id}/suggestion", response_model=AISuggestionResponse)
async def get_suggestion(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AISuggestion)
        .join(AIInteraction)
        .where(AIInteraction.interaction_id == job_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return suggestion


@router.post("/api/ai-jobs/{job_id}/apply", status_code=status.HTTP_200_OK)
async def apply_suggestion(
    job_id: str,
    body: AIJobApply,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AISuggestion)
        .join(AIInteraction)
        .where(AIInteraction.interaction_id == job_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")

    suggestion.disposition = "accepted" if body.mode == "full" else "partially_applied"
    suggestion.applied_by = current_user.user_id
    suggestion.applied_at = datetime.now(timezone.utc)
    if body.selected_diff_blocks:
        suggestion.accepted_segments_json = {"blocks": body.selected_diff_blocks}

    await db.commit()
    return {"status": "applied", "suggestion_id": str(suggestion.suggestion_id)}


@router.post("/api/ai-jobs/{job_id}/reject", status_code=status.HTTP_200_OK)
async def reject_suggestion(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AISuggestion)
        .join(AIInteraction)
        .where(AIInteraction.interaction_id == job_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")

    suggestion.disposition = "rejected"
    await db.commit()
    return {"status": "rejected"}
