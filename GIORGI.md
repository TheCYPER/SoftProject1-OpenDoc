# Giorgi Scope Summary

## Overview

Giorgi's Assignment 2 contribution is centered on the AI path and the late-stage hardening work needed to push the repo toward the top rubric band.

## What Giorgi Implemented

- **AI streaming backend**
  - Added the SSE AI job flow in `backend/app/api/ai_jobs.py`.
  - Added streamed status lifecycle, cancellation, history persistence, and prompt/provider/model metadata capture.
  - Added the in-process AI job cancellation registry in `backend/app/services/ai/job_registry.py`.

- **AI provider and prompt layer**
  - Extended the provider abstraction in `backend/app/services/ai/ai_service.py` and `backend/app/services/ai/providers/`.
  - Added Groq support through the OpenAI-compatible API path.
  - Externalized prompt templates to `backend/app/services/ai/prompts/templates.json`.

- **AI frontend UX**
  - Reworked `frontend/src/components/AIPanel.tsx` for progressive streamed rendering.
  - Added cancel handling, recent AI history, editable suggestions, and partial acceptance of diff blocks.
  - Added the frontend AI transport layer in `frontend/src/api/ai.ts`.

- **Collaboration and permission hardening**
  - Added remote cursor and selection rendering on top of the existing Yjs awareness layer.
  - Hardened active-session revoke behavior so share changes can terminate stale websocket sessions.
  - Added late-stage collaboration state fixes in `frontend/src/lib/collaboration.ts`, `frontend/src/lib/collaborationPresence.ts`, and `backend/app/realtime/websocket.py`.

- **Backend integrity fixes**
  - Removed duplicate-share failure paths and tightened share validation.
  - Improved document/audit consistency, including deleted-document audit access for owners.
  - Synced REST-side ProseMirror updates back into `yjs_state` on create/update/restore paths.

- **Testing and submission alignment**
  - Added and updated backend AI tests, realtime tests, and sharing/audit edge-case tests.
  - Added Playwright E2E coverage for login → document creation → AI rewrite → acceptance.
  - Completed the final submission-alignment pass across `README.md`, `TASKS.md`, `DEVIATIONS.md`, and `Part 1-3.md`.

## Main Branch Evidence

- `feat/pr19-tooling-ci-baseline`
- `feat/pr20-ai-streaming-history`
- `feat/pr21-collab-hardening-bonuses`
- `feat/pr22-backend-integrity`
- `feat/pr23-partial-acceptance`
- `feat/pr24-e2e-tests`
- `feat/pr25-e2e-polish`

## Verification

The final workspace was verified with:

- `cd backend && .venv/bin/python -m pytest app/tests/ -q`
- `cd frontend && npm test`
- `cd frontend && npm run build`
- `cd frontend && npm run test:e2e`

## Scope Boundary

Giorgi did **not** replace the whole project architecture. The work was layered onto the existing repo and focused on:

- AI implementation quality
- collaboration/permission hardening where it blocked grading quality
- final repository alignment for submission
