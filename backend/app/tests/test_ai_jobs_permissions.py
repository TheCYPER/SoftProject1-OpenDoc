"""Permission tests for /api/ai-jobs/* and document AI history."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.ai.ai_service import AIExecutionPlan
from app.services.ai.prompts.templates import PromptRender


def _build_execution_plan() -> AIExecutionPlan:
    return AIExecutionPlan(
        provider_name="groq",
        model_name="llama-3.3-70b-versatile",
        model_profile="groq:llama-3.3-70b-versatile",
        prompt="Rendered prompt",
        prompt_render=PromptRender(
            prompt="Rendered prompt",
            prompt_version="v2",
            truncated=False,
            original_length=24,
            rendered_length=24,
        ),
        system_prompt="System prompt",
    )


async def _seed_job(
    client: AsyncClient,
    owner_headers: dict,
    workspace_id: str,
) -> tuple[str, str]:
    response = await client.post(
        "/api/documents",
        json={
            "title": "AI perm doc",
            "workspace_id": workspace_id,
            "initial_content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Some text to rewrite here."}],
                    }
                ],
            },
        },
        headers=owner_headers,
    )
    assert response.status_code == 201
    document_id = response.json()["document_id"]

    with patch("app.api.ai_jobs.run_ai_job", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = (_build_execution_plan(), "Rewritten text.")
        response = await client.post(
            f"/api/documents/{document_id}/ai-jobs",
            json={"action": "rewrite"},
            headers=owner_headers,
        )
        assert response.status_code == 202

    return document_id, response.json()["job_id"]


@pytest.mark.asyncio
async def test_create_ai_job_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    response = await client.post(
        "/api/documents",
        json={
            "title": "Owner doc",
            "workspace_id": workspace_id,
            "initial_content": {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "hi"}]}
                ],
            },
        },
        headers=auth_headers,
    )
    document_id = response.json()["document_id"]

    response = await client.post(
        f"/api/documents/{document_id}/ai-jobs",
        json={"action": "rewrite"},
        headers=user_bob["headers"],
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_editor_with_allow_ai_disabled_cannot_invoke_ai(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    response = await client.post(
        "/api/documents",
        json={
            "title": "Owner doc",
            "workspace_id": workspace_id,
            "initial_content": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "share no ai"}],
                    }
                ],
            },
        },
        headers=auth_headers,
    )
    document_id = response.json()["document_id"]

    response = await client.post(
        f"/api/documents/{document_id}/shares",
        json={
            "grantee_type": "USER",
            "grantee_ref": user_bob["email"],
            "role": "editor",
            "allow_ai": False,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    response = await client.post(
        f"/api/documents/{document_id}/ai-jobs",
        json={"action": "rewrite"},
        headers=user_bob["headers"],
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "AI usage is disabled for this share."


@pytest.mark.asyncio
async def test_get_ai_job_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    _, job_id = await _seed_job(client, auth_headers, workspace_id)

    response = await client.get(f"/api/ai-jobs/{job_id}", headers=user_bob["headers"])
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_suggestion_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    _, job_id = await _seed_job(client, auth_headers, workspace_id)

    response = await client.get(
        f"/api/ai-jobs/{job_id}/suggestion",
        headers=user_bob["headers"],
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_apply_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    _, job_id = await _seed_job(client, auth_headers, workspace_id)

    response = await client.post(
        f"/api/ai-jobs/{job_id}/apply",
        json={"mode": "full"},
        headers=user_bob["headers"],
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reject_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    _, job_id = await _seed_job(client, auth_headers, workspace_id)

    response = await client.post(f"/api/ai-jobs/{job_id}/reject", headers=user_bob["headers"])
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_viewer_can_read_but_not_apply_or_review_history(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    document_id, job_id = await _seed_job(client, auth_headers, workspace_id)
    response = await client.post(
        f"/api/documents/{document_id}/shares",
        json={
            "grantee_type": "USER",
            "grantee_ref": user_bob["email"],
            "role": "viewer",
            "allow_ai": True,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    response = await client.get(f"/api/ai-jobs/{job_id}", headers=user_bob["headers"])
    assert response.status_code == 200

    response = await client.get(
        f"/api/ai-jobs/{job_id}/suggestion",
        headers=user_bob["headers"],
    )
    assert response.status_code == 200

    response = await client.post(
        f"/api/ai-jobs/{job_id}/apply",
        json={"mode": "full"},
        headers=user_bob["headers"],
    )
    assert response.status_code == 403

    response = await client.post(f"/api/ai-jobs/{job_id}/reject", headers=user_bob["headers"])
    assert response.status_code == 403

    response = await client.get(
        f"/api/documents/{document_id}/ai-history",
        headers=user_bob["headers"],
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_missing_job_returns_404(
    client: AsyncClient, auth_headers: dict
):
    response = await client.get("/api/ai-jobs/does-not-exist", headers=auth_headers)
    assert response.status_code == 404
