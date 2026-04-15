"""Permission tests for /api/ai-jobs/* — a non-member must never reach the job."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _seed_job(client: AsyncClient, owner_headers: dict, workspace_id: str) -> tuple[str, str]:
    """Create a doc + completed AI job as owner; return (doc_id, job_id)."""
    resp = await client.post("/api/documents", json={
        "title": "AI perm doc",
        "workspace_id": workspace_id,
        "initial_content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "Some text to rewrite here."}
            ]}
        ]},
    }, headers=owner_headers)
    assert resp.status_code == 201
    doc_id = resp.json()["document_id"]

    with patch("app.api.ai_jobs.run_ai_job", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "Rewritten text."
        resp = await client.post(f"/api/documents/{doc_id}/ai-jobs", json={
            "action": "rewrite",
        }, headers=owner_headers)
        assert resp.status_code == 202
    return doc_id, resp.json()["job_id"]


@pytest.mark.asyncio
async def test_create_ai_job_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    resp = await client.post("/api/documents", json={
        "title": "Owner doc",
        "workspace_id": workspace_id,
        "initial_content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "hi"}]}
        ]},
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    resp = await client.post(f"/api/documents/{doc_id}/ai-jobs", json={
        "action": "rewrite",
    }, headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_ai_job_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    _, job_id = await _seed_job(client, auth_headers, workspace_id)

    resp = await client.get(f"/api/ai-jobs/{job_id}", headers=user_bob["headers"])
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_suggestion_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    _, job_id = await _seed_job(client, auth_headers, workspace_id)

    resp = await client.get(
        f"/api/ai-jobs/{job_id}/suggestion", headers=user_bob["headers"]
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_apply_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    _, job_id = await _seed_job(client, auth_headers, workspace_id)

    resp = await client.post(
        f"/api/ai-jobs/{job_id}/apply",
        json={"mode": "full"},
        headers=user_bob["headers"],
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reject_denied_for_non_member(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    _, job_id = await _seed_job(client, auth_headers, workspace_id)

    resp = await client.post(
        f"/api/ai-jobs/{job_id}/reject", headers=user_bob["headers"]
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_can_read_but_not_apply(
    client: AsyncClient, auth_headers: dict, user_bob: dict, workspace_id: str
):
    doc_id, job_id = await _seed_job(client, auth_headers, workspace_id)
    # Share doc with Bob as viewer
    await client.post(f"/api/documents/{doc_id}/shares", json={
        "grantee_type": "USER",
        "grantee_ref": user_bob["email"],
        "role": "viewer",
        "allow_ai": True,
    }, headers=auth_headers)

    # Viewer can read the job + suggestion
    resp = await client.get(f"/api/ai-jobs/{job_id}", headers=user_bob["headers"])
    assert resp.status_code == 200
    resp = await client.get(
        f"/api/ai-jobs/{job_id}/suggestion", headers=user_bob["headers"]
    )
    assert resp.status_code == 200

    # But cannot apply (editor required)
    resp = await client.post(
        f"/api/ai-jobs/{job_id}/apply",
        json={"mode": "full"},
        headers=user_bob["headers"],
    )
    assert resp.status_code == 403
    # And cannot reject
    resp = await client.post(
        f"/api/ai-jobs/{job_id}/reject", headers=user_bob["headers"]
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_missing_job_returns_404(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/ai-jobs/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404
