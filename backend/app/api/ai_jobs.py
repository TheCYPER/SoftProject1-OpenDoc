import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.ai_interaction import AIInteraction
from app.models.ai_suggestion import AISuggestion
from app.models.audit_event import AuditEvent
from app.models.document import Document
from app.models.document_share import DocumentShare
from app.models.user import User
from app.schemas.ai import (
    AIHistoryItem,
    AIHistoryResponse,
    AIJobApply,
    AIJobCancelResponse,
    AIJobCreate,
    AIJobResponse,
    AISuggestionResponse,
    SelectionRange,
)
from app.services.ai.ai_service import AIExecutionPlan, run_ai_job, stream_ai_job
from app.services.ai.job_registry import ai_job_registry
from app.services.permissions import check_document_access

router = APIRouter(tags=["ai"])
limiter = Limiter(key_func=get_remote_address)

AI_JOB_QUOTA = 50
TERMINAL_STATUSES = {"ready", "stale", "failed", "quota_exceeded", "cancelled"}


@dataclass(frozen=True)
class InitializedAIJob:
    document: Document
    interaction: AIInteraction
    source_text: str | None
    is_stale: bool
    quota_exceeded: bool = False


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _extract_text_from_content(
    content: dict[str, Any] | None,
    sel_from: int | None,
    sel_to: int | None,
) -> str:
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


def _build_job_response(interaction: AIInteraction) -> AIJobResponse:
    return AIJobResponse(
        job_id=interaction.interaction_id,
        status=interaction.status,
        created_at=interaction.created_at,
        completed_at=interaction.completed_at,
        provider_name=interaction.provider_name,
        model_name=interaction.model_name,
        prompt_template_version=interaction.prompt_template_version,
        error_code=interaction.error_code,
        error_message=interaction.error_message,
    )


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


async def _check_quota(db: AsyncSession, user_id: str) -> bool:
    result = await db.execute(
        select(func.count()).select_from(AIInteraction).where(AIInteraction.requested_by == user_id)
    )
    count = result.scalar_one()
    return count < AI_JOB_QUOTA


async def _ensure_ai_allowed_for_share(
    db: AsyncSession,
    document_id: str,
    user: User,
    document: Document,
) -> None:
    if document.created_by == user.user_id:
        return

    result = await db.execute(
        select(DocumentShare).where(
            DocumentShare.document_id == document_id,
            DocumentShare.grantee_type == "USER",
            DocumentShare.grantee_ref == user.email,
        )
    )
    share = result.scalar_one_or_none()
    if share is not None and not share.allow_ai:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI usage is disabled for this share.",
        )


async def _load_interaction_with_access(
    db: AsyncSession,
    job_id: str,
    user: User,
    required_role: str,
) -> AIInteraction:
    result = await db.execute(
        select(AIInteraction).where(AIInteraction.interaction_id == job_id)
    )
    interaction = result.scalar_one_or_none()
    if interaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")

    await check_document_access(
        db,
        interaction.document_id,
        user,
        required_role=required_role,
    )
    return interaction


async def _initialize_ai_job(
    db: AsyncSession,
    document_id: str,
    body: AIJobCreate,
    current_user: User,
) -> InitializedAIJob:
    document = await check_document_access(
        db,
        document_id,
        current_user,
        required_role="editor",
    )
    await _ensure_ai_allowed_for_share(db, document_id, current_user, document)

    resolved_provider_name = (body.provider or settings.AI_DEFAULT_PROVIDER).lower()
    resolved_model_profile = (
        f"{resolved_provider_name}:{body.model}" if body.model else resolved_provider_name
    )

    if not await _check_quota(db, current_user.user_id):
        interaction = AIInteraction(
            document_id=document_id,
            requested_by=current_user.user_id,
            action_type=body.action,
            scope_type=body.scope,
            base_revision_id=body.base_revision_id or document.current_revision_id,
            provider_name=resolved_provider_name,
            model_name=body.model,
            model_profile=resolved_model_profile,
            status="quota_exceeded",
            error_code="quota_exceeded",
            error_message="AI job quota exceeded.",
            completed_at=_now_utc(),
        )
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)
        return InitializedAIJob(
            document=document,
            interaction=interaction,
            source_text=None,
            is_stale=False,
            quota_exceeded=True,
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
        base_revision_id=body.base_revision_id or document.current_revision_id,
        provider_name=resolved_provider_name,
        model_name=body.model,
        model_profile=resolved_model_profile,
        status="running",
    )
    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)

    source_text = body.selected_text or _extract_text_from_content(document.content, sel_from, sel_to)
    if not source_text.strip():
        interaction.status = "failed"
        interaction.error_code = "empty_input"
        interaction.error_message = (
            "No text found. Write some text or select text in the editor first."
        )
        interaction.completed_at = _now_utc()
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=interaction.error_message,
        )

    is_stale = (
        body.base_revision_id is not None
        and document.current_revision_id is not None
        and body.base_revision_id != document.current_revision_id
    )
    return InitializedAIJob(
        document=document,
        interaction=interaction,
        source_text=source_text,
        is_stale=is_stale,
    )


def _apply_execution_plan(interaction: AIInteraction, execution_plan: AIExecutionPlan) -> None:
    interaction.prompt_template_version = execution_plan.prompt_render.prompt_version
    interaction.provider_name = execution_plan.provider_name
    interaction.model_name = execution_plan.model_name
    interaction.model_profile = execution_plan.model_profile
    interaction.prompt_text = execution_plan.prompt
    interaction.system_prompt_text = execution_plan.system_prompt


async def _mark_interaction_failed(
    db: AsyncSession,
    interaction: AIInteraction,
    *,
    error_code: str,
    error_message: str,
) -> None:
    interaction.status = "failed"
    interaction.error_code = error_code
    interaction.error_message = error_message
    interaction.completed_at = _now_utc()
    await db.commit()


async def _get_or_create_suggestion(
    db: AsyncSession,
    interaction_id: str,
) -> AISuggestion:
    result = await db.execute(
        select(AISuggestion).where(AISuggestion.interaction_id == interaction_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        suggestion = AISuggestion(interaction_id=interaction_id)
        db.add(suggestion)
        await db.flush()
    return suggestion


async def _persist_suggestion(
    db: AsyncSession,
    interaction: AIInteraction,
    *,
    source_text: str,
    suggested_text: str,
    is_stale: bool,
    partial_output_available: bool,
) -> AISuggestion:
    suggestion = await _get_or_create_suggestion(db, interaction.interaction_id)
    suggestion.original_text = source_text
    suggestion.suggested_text = suggested_text
    suggestion.stale = is_stale
    suggestion.partial_output_available = partial_output_available
    return suggestion


async def _finalize_success(
    db: AsyncSession,
    interaction: AIInteraction,
    *,
    source_text: str,
    suggested_text: str,
    is_stale: bool,
) -> AISuggestion:
    suggestion = await _persist_suggestion(
        db,
        interaction,
        source_text=source_text,
        suggested_text=suggested_text,
        is_stale=is_stale,
        partial_output_available=False,
    )
    interaction.status = "stale" if is_stale else "ready"
    interaction.completed_at = _now_utc()
    interaction.error_code = None
    interaction.error_message = None
    await db.commit()
    await db.refresh(interaction)
    await db.refresh(suggestion)
    return suggestion


async def _finalize_cancelled_or_failed(
    db: AsyncSession,
    interaction: AIInteraction,
    *,
    status_value: str,
    error_code: str,
    error_message: str,
    source_text: str,
    partial_text: str,
    is_stale: bool,
) -> AISuggestion | None:
    suggestion: AISuggestion | None = None
    if partial_text:
        suggestion = await _persist_suggestion(
            db,
            interaction,
            source_text=source_text,
            suggested_text=partial_text,
            is_stale=is_stale,
            partial_output_available=True,
        )

    interaction.status = status_value
    interaction.error_code = error_code
    interaction.error_message = error_message
    interaction.completed_at = _now_utc()
    await db.commit()
    await db.refresh(interaction)
    if suggestion is not None:
        await db.refresh(suggestion)
    return suggestion


async def _produce_streamed_job(
    session_factory: async_sessionmaker[AsyncSession],
    interaction_id: str,
    stream: AsyncIterator[str],
    *,
    source_text: str,
    is_stale: bool,
    event_queue: asyncio.Queue[tuple[str, dict[str, Any]] | None],
) -> None:
    partial_chunks: list[str] = []
    try:
        async for chunk in stream:
            if not chunk:
                continue
            partial_chunks.append(chunk)
            await event_queue.put(
                ("delta", {"job_id": interaction_id, "delta": chunk})
            )

        async with session_factory() as db:
            interaction = await db.get(AIInteraction, interaction_id)
            if interaction is None:
                return

            suggestion = await _finalize_success(
                db,
                interaction,
                source_text=source_text,
                suggested_text="".join(partial_chunks),
                is_stale=is_stale,
            )
            await event_queue.put(
                (
                    "suggestion",
                    {
                        "job_id": interaction_id,
                        "suggestion_id": suggestion.suggestion_id,
                        "original_text": suggestion.original_text,
                        "suggested_text": suggestion.suggested_text,
                        "stale": suggestion.stale,
                        "disposition": suggestion.disposition,
                        "partial_output_available": suggestion.partial_output_available,
                    },
                )
            )
            await event_queue.put(
                (
                    "status",
                    _build_job_response(interaction).model_dump(mode="json"),
                )
            )
    except asyncio.CancelledError:
        partial_text = "".join(partial_chunks)
        cancel_reason = await ai_job_registry.get_cancel_reason(interaction_id)
        async with session_factory() as db:
            interaction = await db.get(AIInteraction, interaction_id)
            if interaction is not None:
                suggestion = await _finalize_cancelled_or_failed(
                    db,
                    interaction,
                    status_value="cancelled",
                    error_code="cancelled",
                    error_message=cancel_reason or "AI generation cancelled.",
                    source_text=source_text,
                    partial_text=partial_text,
                    is_stale=is_stale,
                )
                if suggestion is not None:
                    await event_queue.put(
                        (
                            "suggestion",
                            {
                                "job_id": interaction_id,
                                "suggestion_id": suggestion.suggestion_id,
                                "original_text": suggestion.original_text,
                                "suggested_text": suggestion.suggested_text,
                                "stale": suggestion.stale,
                                "disposition": suggestion.disposition,
                                "partial_output_available": suggestion.partial_output_available,
                            },
                        )
                    )
                await event_queue.put(
                    ("status", _build_job_response(interaction).model_dump(mode="json"))
                )
        raise
    except Exception as exc:
        partial_text = "".join(partial_chunks)
        async with session_factory() as db:
            interaction = await db.get(AIInteraction, interaction_id)
            if interaction is not None:
                suggestion = await _finalize_cancelled_or_failed(
                    db,
                    interaction,
                    status_value="failed",
                    error_code="provider_error",
                    error_message=f"AI provider error: {exc}",
                    source_text=source_text,
                    partial_text=partial_text,
                    is_stale=is_stale,
                )
                if suggestion is not None:
                    await event_queue.put(
                        (
                            "suggestion",
                            {
                                "job_id": interaction_id,
                                "suggestion_id": suggestion.suggestion_id,
                                "original_text": suggestion.original_text,
                                "suggested_text": suggestion.suggested_text,
                                "stale": suggestion.stale,
                                "disposition": suggestion.disposition,
                                "partial_output_available": suggestion.partial_output_available,
                            },
                        )
                    )
                await event_queue.put(
                    ("status", _build_job_response(interaction).model_dump(mode="json"))
                )
    finally:
        await ai_job_registry.unregister(interaction_id)
        await event_queue.put(None)


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
    initialized_job = await _initialize_ai_job(db, document_id, body, current_user)
    interaction = initialized_job.interaction

    if initialized_job.quota_exceeded:
        return _build_job_response(interaction)

    assert initialized_job.source_text is not None

    try:
        execution_plan, suggested_text = await run_ai_job(
            action=body.action,
            text=initialized_job.source_text,
            options=body.options,
            provider_name=body.provider,
            model=body.model,
        )
    except Exception as exc:
        await _mark_interaction_failed(
            db,
            interaction,
            error_code="provider_error",
            error_message=f"AI provider error: {exc}",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=interaction.error_message,
        ) from exc

    _apply_execution_plan(interaction, execution_plan)
    await _finalize_success(
        db,
        interaction,
        source_text=initialized_job.source_text,
        suggested_text=suggested_text,
        is_stale=initialized_job.is_stale,
    )
    return _build_job_response(interaction)


@router.post(
    "/api/documents/{document_id}/ai-jobs/stream",
    summary="Stream an AI job over server-sent events",
)
@limiter.limit("20/minute")
async def stream_ai_job_sse(
    request: Request,
    document_id: str,
    body: AIJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    initialized_job = await _initialize_ai_job(db, document_id, body, current_user)
    interaction = initialized_job.interaction
    initial_payload = _build_job_response(interaction).model_dump(mode="json")

    if initialized_job.quota_exceeded:
        async def quota_stream() -> AsyncIterator[str]:
            yield _sse_event("job", initial_payload)
            yield _sse_event("status", initial_payload)

        return StreamingResponse(
            quota_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    assert initialized_job.source_text is not None

    try:
        execution_plan, provider_stream = await stream_ai_job(
            action=body.action,
            text=initialized_job.source_text,
            options=body.options,
            provider_name=body.provider,
            model=body.model,
        )
    except Exception as exc:
        await _mark_interaction_failed(
            db,
            interaction,
            error_code="provider_error",
            error_message=f"AI provider error: {exc}",
        )
        failed_payload = _build_job_response(interaction).model_dump(mode="json")

        async def failed_stream() -> AsyncIterator[str]:
            yield _sse_event("job", failed_payload)
            yield _sse_event("status", failed_payload)

        return StreamingResponse(
            failed_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    _apply_execution_plan(interaction, execution_plan)
    await db.commit()
    await db.refresh(interaction)
    initial_payload = _build_job_response(interaction).model_dump(mode="json")

    bind = db.bind
    if bind is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI streaming database binding is unavailable.",
        )
    session_factory = async_sessionmaker(bind=bind, class_=AsyncSession, expire_on_commit=False)

    event_queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    producer_task = asyncio.create_task(
        _produce_streamed_job(
            session_factory,
            interaction.interaction_id,
            provider_stream,
            source_text=initialized_job.source_text,
            is_stale=initialized_job.is_stale,
            event_queue=event_queue,
        )
    )
    await ai_job_registry.register(interaction.interaction_id, producer_task)

    async def event_stream() -> AsyncIterator[str]:
        try:
            yield _sse_event("job", initial_payload)
            while True:
                if await request.is_disconnected():
                    await ai_job_registry.cancel(
                        interaction.interaction_id,
                        reason="Client disconnected during AI stream.",
                    )
                    break

                try:
                    item = await asyncio.wait_for(event_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                if item is None:
                    break

                event_name, payload = item
                yield _sse_event(event_name, payload)
        finally:
            if not producer_task.done():
                await ai_job_registry.cancel(
                    interaction.interaction_id,
                    reason="AI stream closed before completion.",
                )
            with suppress(asyncio.CancelledError):
                await producer_task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/api/ai-jobs/{job_id}",
    response_model=AIJobResponse,
    summary="Fetch AI job status",
)
async def get_ai_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    interaction = await _load_interaction_with_access(
        db,
        job_id,
        current_user,
        required_role="viewer",
    )
    return _build_job_response(interaction)


@router.post(
    "/api/ai-jobs/{job_id}/cancel",
    response_model=AIJobCancelResponse,
    summary="Cancel an in-flight AI job",
)
async def cancel_ai_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    interaction = await _load_interaction_with_access(
        db,
        job_id,
        current_user,
        required_role="editor",
    )

    if interaction.status in TERMINAL_STATUSES:
        return AIJobCancelResponse(
            job_id=interaction.interaction_id,
            status=interaction.status,
            completed_at=interaction.completed_at,
        )

    interaction.status = "cancelling"
    interaction.error_code = "cancelled"
    interaction.error_message = "Cancellation requested."
    await db.commit()
    cancelled = await ai_job_registry.cancel(job_id, reason="Cancelled by user request.")
    if not cancelled:
        interaction.status = "cancelled"
        interaction.completed_at = _now_utc()
        await db.commit()
    await db.refresh(interaction)
    return AIJobCancelResponse(
        job_id=interaction.interaction_id,
        status=interaction.status,
        completed_at=interaction.completed_at,
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
    await _load_interaction_with_access(db, job_id, current_user, required_role="viewer")
    result = await db.execute(
        select(AISuggestion).join(AIInteraction).where(AIInteraction.interaction_id == job_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return suggestion


@router.post(
    "/api/ai-jobs/{job_id}/apply",
    status_code=status.HTTP_200_OK,
    summary="Accept an AI suggestion",
)
async def apply_suggestion(
    job_id: str,
    body: AIJobApply,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    interaction = await _load_interaction_with_access(
        db,
        job_id,
        current_user,
        required_role="editor",
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
    document = doc_result.scalar_one()

    suggestion.disposition = "accepted" if body.mode == "full" else "partially_applied"
    suggestion.applied_by = current_user.user_id
    suggestion.applied_at = _now_utc()
    if body.selected_diff_blocks:
        suggestion.accepted_segments_json = {"blocks": body.selected_diff_blocks}

    audit = AuditEvent(
        workspace_id=document.workspace_id,
        document_id=document.document_id,
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
        db,
        job_id,
        current_user,
        required_role="editor",
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
    document = doc_result.scalar_one()

    suggestion.disposition = "rejected"

    audit = AuditEvent(
        workspace_id=document.workspace_id,
        document_id=document.document_id,
        actor_user_id=current_user.user_id,
        event_type="ai.suggestion.rejected",
        target_ref=str(suggestion.suggestion_id),
        metadata_json={"job_id": job_id, "action_type": interaction.action_type},
    )
    db.add(audit)
    await db.commit()
    return {"status": "rejected"}


@router.get(
    "/api/documents/{document_id}/ai-history",
    response_model=AIHistoryResponse,
    summary="List AI interaction history for a document",
)
async def get_document_ai_history(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await check_document_access(db, document_id, current_user, required_role="owner")

    result = await db.execute(
        select(AIInteraction, AISuggestion, User)
        .join(User, User.user_id == AIInteraction.requested_by)
        .outerjoin(AISuggestion, AISuggestion.interaction_id == AIInteraction.interaction_id)
        .where(AIInteraction.document_id == document_id)
        .order_by(AIInteraction.created_at.desc())
    )

    items: list[AIHistoryItem] = []
    for interaction, suggestion, user in result.all():
        selection_range = None
        if interaction.selection_from is not None and interaction.selection_to is not None:
            selection_range = SelectionRange(
                from_=interaction.selection_from,
                to=interaction.selection_to,
            )

        items.append(
            AIHistoryItem(
                job_id=interaction.interaction_id,
                suggestion_id=None if suggestion is None else suggestion.suggestion_id,
                action=interaction.action_type,
                scope=interaction.scope_type,
                status=interaction.status,
                disposition=None if suggestion is None else suggestion.disposition,
                stale=False if suggestion is None else suggestion.stale,
                original_text=None if suggestion is None else suggestion.original_text,
                suggested_text=None if suggestion is None else suggestion.suggested_text,
                partial_output_available=(
                    False if suggestion is None else suggestion.partial_output_available
                ),
                prompt_template_version=interaction.prompt_template_version,
                provider_name=interaction.provider_name,
                model_name=interaction.model_name,
                prompt_text=interaction.prompt_text,
                system_prompt_text=interaction.system_prompt_text,
                requested_by_user_id=user.user_id,
                requested_by_display_name=user.display_name,
                requested_by_email=user.email,
                selection_range=selection_range,
                error_code=interaction.error_code,
                error_message=interaction.error_message,
                created_at=interaction.created_at,
                completed_at=interaction.completed_at,
            )
        )

    return AIHistoryResponse(items=items)
