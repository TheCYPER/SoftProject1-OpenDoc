"""Tests for AI job endpoints — mocked AI provider."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ai_job_lifecycle(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    # Create a document with text content
    resp = await client.post("/api/documents", json={
        "title": "AI Test Doc",
        "workspace_id": workspace_id,
        "initial_content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "The quick brown fox jumps over the lazy dog."}
            ]}
        ]},
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    with patch("app.api.ai_jobs.run_ai_job", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "The swift brown fox leaps over the lazy dog."

        resp = await client.post(f"/api/documents/{doc_id}/ai-jobs", json={
            "action": "rewrite",
            "scope": "selection",
            "selection_range": {"from": 0, "to": 44},
        }, headers=auth_headers)
        assert resp.status_code == 202
        job = resp.json()
        job_id = job["job_id"]
        assert job["status"] == "ready"

    # Get job status
    resp = await client.get(f"/api/ai-jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

    # Get suggestion
    resp = await client.get(f"/api/ai-jobs/{job_id}/suggestion", headers=auth_headers)
    assert resp.status_code == 200
    suggestion = resp.json()
    assert suggestion["original_text"] == "The quick brown fox jumps over the lazy dog."
    assert suggestion["suggested_text"] == "The swift brown fox leaps over the lazy dog."
    assert suggestion["disposition"] == "pending"

    # Apply suggestion
    resp = await client.post(f"/api/ai-jobs/{job_id}/apply", json={
        "mode": "full",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"


@pytest.mark.asyncio
async def test_ai_job_reject(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    resp = await client.post("/api/documents", json={
        "title": "AI Reject Test",
        "workspace_id": workspace_id,
        "initial_content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "Some text to rewrite."}
            ]}
        ]},
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    with patch("app.api.ai_jobs.run_ai_job", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = "Rewritten text."
        resp = await client.post(f"/api/documents/{doc_id}/ai-jobs", json={
            "action": "rewrite",
        }, headers=auth_headers)
        job_id = resp.json()["job_id"]

    resp = await client.post(f"/api/ai-jobs/{job_id}/reject", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_ai_job_empty_text(
    client: AsyncClient, auth_headers: dict, workspace_id: str
):
    resp = await client.post("/api/documents", json={
        "title": "Empty Doc",
        "workspace_id": workspace_id,
    }, headers=auth_headers)
    doc_id = resp.json()["document_id"]

    with patch("app.api.ai_jobs.run_ai_job", new_callable=AsyncMock):
        resp = await client.post(f"/api/documents/{doc_id}/ai-jobs", json={
            "action": "summarize",
        }, headers=auth_headers)
        assert resp.status_code == 422
