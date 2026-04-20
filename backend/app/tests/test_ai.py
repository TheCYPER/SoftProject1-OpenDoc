"""Tests for AI job endpoints — buffered flow, streaming, cancellation, and history."""

import asyncio
import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response

from app.services.ai.ai_service import AIExecutionPlan
from app.services.ai.job_registry import ai_job_registry
from app.services.ai.prompts.templates import PromptRender
from app.services.ai.providers.base import AIProvider


def _build_execution_plan(
    *,
    provider_name: str = "ollama",
    model_name: str = "qwen-test",
    prompt_text: str = "Rendered prompt",
    prompt_version: str = "v2",
) -> AIExecutionPlan:
    return AIExecutionPlan(
        provider_name=provider_name,
        model_name=model_name,
        model_profile=f"{provider_name}:{model_name}",
        prompt=prompt_text,
        prompt_render=PromptRender(
            prompt=prompt_text,
            prompt_version=prompt_version,
            truncated=False,
            original_length=43,
            rendered_length=43,
        ),
        system_prompt="System prompt",
    )


class FakeStreamingProvider(AIProvider):
    def __init__(self, chunks: tuple[str, ...], pause_after_first: bool = False):
        self._chunks = chunks
        self._pause_after_first = pause_after_first

    async def stream(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> AsyncIterator[str]:
        for index, chunk in enumerate(self._chunks):
            yield chunk
            if self._pause_after_first and index == 0:
                await asyncio.sleep(30)


async def _create_document(
    client: AsyncClient,
    auth_headers: dict,
    workspace_id: str,
    *,
    title: str,
    text: str | None = None,
) -> str:
    payload: dict[str, object] = {"title": title, "workspace_id": workspace_id}
    if text is not None:
        payload["initial_content"] = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }

    response = await client.post("/api/documents", json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text
    return response.json()["document_id"]


async def _iter_sse_events(response: Response) -> AsyncIterator[dict[str, object]]:
    event_name = "message"
    data_lines: list[str] = []

    async for line in response.aiter_lines():
        if not line:
            if data_lines:
                yield {
                    "event": event_name,
                    "data": json.loads("\n".join(data_lines)),
                }
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())


@pytest.mark.asyncio
async def test_ai_job_lifecycle_and_history(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    document_id = await _create_document(
        client,
        auth_headers,
        workspace_id,
        title="AI Test Doc",
        text="The quick brown fox jumps over the lazy dog.",
    )

    with patch("app.api.ai_jobs.run_ai_job", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = (
            _build_execution_plan(provider_name="ollama", model_name="qwen-test"),
            "The swift brown fox leaps over the lazy dog.",
        )

        response = await client.post(
            f"/api/documents/{document_id}/ai-jobs",
            json={
                "action": "rewrite",
                "scope": "selection",
                "selection_range": {"from": 0, "to": 44},
                "provider": "ollama",
                "model": "qwen-test",
            },
            headers=auth_headers,
        )

    assert response.status_code == 202
    job = response.json()
    job_id = job["job_id"]
    assert job["status"] == "ready"
    assert job["provider_name"] == "ollama"
    assert job["model_name"] == "qwen-test"

    response = await client.get(f"/api/ai-jobs/{job_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

    response = await client.get(f"/api/ai-jobs/{job_id}/suggestion", headers=auth_headers)
    assert response.status_code == 200
    suggestion = response.json()
    assert suggestion["original_text"] == "The quick brown fox jumps over the lazy dog."
    assert suggestion["suggested_text"] == "The swift brown fox leaps over the lazy dog."
    assert suggestion["partial_output_available"] is False

    response = await client.get(
        f"/api/documents/{document_id}/ai-history",
        headers=auth_headers,
    )
    assert response.status_code == 200
    history = response.json()["items"]
    assert len(history) == 1
    assert history[0]["job_id"] == job_id
    assert history[0]["provider_name"] == "ollama"
    assert history[0]["model_name"] == "qwen-test"
    assert history[0]["prompt_template_version"] == "v2"

    response = await client.post(
        f"/api/ai-jobs/{job_id}/apply",
        json={"mode": "full"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "applied"


@pytest.mark.asyncio
async def test_ai_job_stream_emits_sse_and_persists_suggestion(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    document_id = await _create_document(
        client,
        auth_headers,
        workspace_id,
        title="AI Stream Doc",
        text="The quick brown fox jumps over the lazy dog.",
    )
    execution_plan = _build_execution_plan(provider_name="ollama", model_name="qwen-test")

    with patch("app.api.ai_jobs.stream_ai_job", new_callable=AsyncMock) as mock_stream:
        mock_stream.return_value = (
            execution_plan,
            FakeStreamingProvider(("The ", "swift ", "brown fox")).stream("", ""),
        )

        async with client.stream(
            "POST",
            f"/api/documents/{document_id}/ai-jobs/stream",
            json={
                "action": "rewrite",
                "selected_text": "The quick brown fox",
                "provider": "ollama",
                "model": "qwen-test",
            },
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200
            events = [event async for event in _iter_sse_events(response)]

    job_event = next(event for event in events if event["event"] == "job")
    status_event = next(event for event in events if event["event"] == "status")
    suggestion_event = next(event for event in events if event["event"] == "suggestion")
    delta_events = [event for event in events if event["event"] == "delta"]

    assert job_event["data"]["provider_name"] == "ollama"
    assert len(delta_events) == 3
    assert [event["data"]["delta"] for event in delta_events] == ["The ", "swift ", "brown fox"]
    assert suggestion_event["data"]["suggested_text"] == "The swift brown fox"
    assert status_event["data"]["status"] == "ready"

    job_id = job_event["data"]["job_id"]
    response = await client.get(f"/api/ai-jobs/{job_id}/suggestion", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["suggested_text"] == "The swift brown fox"


@pytest.mark.asyncio
async def test_ai_job_cancel_discards_partial_output(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    document_id = await _create_document(
        client,
        auth_headers,
        workspace_id,
        title="AI Cancel Doc",
        text="Some text to rewrite.",
    )
    execution_plan = _build_execution_plan(provider_name="ollama", model_name="qwen-test")

    async def fake_stream() -> AsyncIterator[str]:
        yield "Partial "
        await asyncio.sleep(30)

    async def consume_stream() -> list[dict[str, object]]:
        collected: list[dict[str, object]] = []
        async with client.stream(
            "POST",
            f"/api/documents/{document_id}/ai-jobs/stream",
            json={
                "action": "rewrite",
                "selected_text": "Some text to rewrite.",
                "provider": "ollama",
                "model": "qwen-test",
            },
            headers=auth_headers,
            ) as response:
                assert response.status_code == 200
                async for event in _iter_sse_events(response):
                    collected.append(event)
                    if event["event"] == "status" and event["data"]["status"] == "cancelled":
                        break
        return collected

    with patch("app.api.ai_jobs.stream_ai_job", new_callable=AsyncMock) as mock_stream:
        mock_stream.return_value = (execution_plan, fake_stream())

        consumer_task = asyncio.create_task(consume_stream())
        async def _wait_for_job_id() -> str:
            while not ai_job_registry._jobs:
                await asyncio.sleep(0.01)
            return next(iter(ai_job_registry._jobs))

        job_id = await asyncio.wait_for(_wait_for_job_id(), timeout=2.0)

        cancel_response = await client.post(
            f"/api/ai-jobs/{job_id}/cancel",
            headers=auth_headers,
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["status"] in {"cancelling", "cancelled"}

        events = await asyncio.wait_for(consumer_task, timeout=2.0)

    final_status = [event for event in events if event["event"] == "status"][-1]
    assert final_status["data"]["status"] == "cancelled"

    response = await client.get(f"/api/ai-jobs/{job_id}/suggestion", headers=auth_headers)
    assert response.status_code == 200
    suggestion = response.json()
    assert suggestion["suggested_text"] == "Partial "
    assert suggestion["partial_output_available"] is True


@pytest.mark.asyncio
async def test_ai_job_reject(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    document_id = await _create_document(
        client,
        auth_headers,
        workspace_id,
        title="AI Reject Test",
        text="Some text to rewrite.",
    )

    with patch("app.api.ai_jobs.run_ai_job", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = (
            _build_execution_plan(provider_name="ollama", model_name="qwen-test"),
            "Rewritten text.",
        )
        response = await client.post(
            f"/api/documents/{document_id}/ai-jobs",
            json={"action": "rewrite", "provider": "ollama", "model": "qwen-test"},
            headers=auth_headers,
        )
        job_id = response.json()["job_id"]

    response = await client.post(f"/api/ai-jobs/{job_id}/reject", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_ai_job_empty_text(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    document_id = await _create_document(
        client,
        auth_headers,
        workspace_id,
        title="Empty Doc",
    )

    response = await client.post(
        f"/api/documents/{document_id}/ai-jobs",
        json={"action": "summarize", "provider": "ollama"},
        headers=auth_headers,
    )
    assert response.status_code == 422
