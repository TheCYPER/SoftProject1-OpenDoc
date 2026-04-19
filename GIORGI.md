# Giorgi Scope Summary

## Purpose of This File

This file explains, in simple technical language, what Giorgi implemented for Assignment 2, why those changes matter, and where they live in the codebase. It is written for a reader who may not already know the project structure.

## High-Level Summary

Giorgi's work is mainly about making the AI assistant and the late-stage system hardening good enough for the top grading band.

In practical terms, that means:

- making AI responses stream live instead of waiting for one big reply
- making AI usage safer and easier to review
- adding AI history and prompt/version tracking
- adding partial acceptance of AI suggestions
- adding remote collaborator cursors and stronger session revoke behavior
- fixing several backend consistency bugs that could hurt the demo or grading
- helping align the repo, tests, and report set with what actually ships

## Beginner-Friendly View of the Contribution

If you are new to the codebase, think of Giorgi's work as happening in five layers.

### 1. The AI backend layer

This is the code that talks to the language model and decides how an AI request should run.

Main files:

- `backend/app/api/ai_jobs.py`
- `backend/app/services/ai/ai_service.py`
- `backend/app/services/ai/providers/`
- `backend/app/services/ai/prompts/templates.py`
- `backend/app/services/ai/prompts/templates.json`
- `backend/app/services/ai/job_registry.py`

What changed:

- Added **streaming AI jobs** over Server-Sent Events (SSE).
- Added **job lifecycle states** such as running, streaming, ready, failed, and cancelled.
- Added **cancel support** for in-progress generations.
- Added **history capture** so the backend stores provider, model, prompt version, prompt text, system prompt, result status, and disposition.
- Added **Groq** as a provider using the OpenAI-compatible API path.
- Moved prompts into a JSON file so prompts are no longer hardcoded in route handlers.

Why this matters:

- The assignment PDF says streaming is a hard requirement.
- The assignment PDF also says prompts must be configurable and providers must be swappable in one place.

### 2. The AI frontend layer

This is the UI the user sees in the editor sidebar.

Main files:

- `frontend/src/components/AIPanel.tsx`
- `frontend/src/api/ai.ts`
- `frontend/src/api/client.ts`
- `frontend/src/types/index.ts`

What changed:

- Reworked the AI panel so text appears **progressively** while the model is generating.
- Added a **Cancel Generation** button.
- Added **recent AI history** in the sidebar.
- Added **diff view**, **side-by-side view**, and **editable suggestion mode**.
- Added **partial acceptance** of AI suggestions by selecting changed diff blocks.
- Added **backend-backed apply/reject recording** so AI actions are not just local UI events.

Why this matters:

- This is the visible proof that the AI path is not fake or blocking.
- It directly supports the Assignment 2 requirements for streaming, suggestion UX, and history UI.

### 3. Collaboration and permission hardening

This is the work that improves the collaborative editor beyond just "two people can type."

Main files:

- `frontend/src/lib/collaboration.ts`
- `frontend/src/lib/collaborationPresence.ts`
- `frontend/src/components/PresenceBar.tsx`
- `frontend/src/index.css`
- `backend/app/realtime/websocket.py`
- `backend/app/api/shares.py`

What changed:

- Added **remote cursors and remote selections** with labeled colors.
- Added **presence cleanup** so ghost collaborators disappear correctly after disconnects.
- Added stronger **session revoke handling** so active websocket sessions can be closed when sharing permissions change.
- Improved the collaboration client so it reacts more cleanly to presence and connection lifecycle events.

Why this matters:

- Remote cursor/selection tracking is one of the bonus items in the PDF.
- Share revoke behavior is important for the "server-side permissions, not just hidden buttons" expectation.

### 4. Backend integrity and consistency fixes

These are not flashy demo features, but they protect the system from hidden failures.

Main files:

- `backend/app/api/documents.py`
- `backend/app/api/versions.py`
- `backend/app/api/audit.py`
- `backend/app/api/shares.py`
- `backend/app/services/permissions.py`
- `backend/app/models/document_share.py`
- `backend/app/database.py`
- `backend/alembic/versions/20260419_0001_ai_streaming_metadata.py`
- `backend/alembic/versions/20260419_0002_ai_prompt_text_columns.py`

What changed:

- Fixed duplicate-share behavior so repeated sharing does not create broken permission states.
- Tightened share input validation.
- Improved audit behavior so owners can still inspect audit records for deleted documents.
- Added document mutation audit records for create/update/delete flows.
- Synced REST-side ProseMirror writes back into `yjs_state` on create/update/restore so document state is more consistent between REST and collaboration paths.
- Added follow-up migration handling for missing AI metadata columns.

Why this matters:

- These are the kinds of issues that often break demos in subtle ways.
- They also strengthen the "Testing & Quality" part of the rubric.

### 5. Tooling, E2E, and submission alignment

This is the final polish layer that helps the repo behave like a real submission and not just a pile of code.

Main files:

- `Makefile`
- `run.sh`
- `frontend/playwright.config.ts`
- `frontend/tests/e2e/login-edit-ai-accept.spec.ts`
- `README.md`
- `TASKS.md`
- `DEVIATIONS.md`
- `Part 1.md`
- `Part 2.md`
- `Part 3.md`

What changed:

- Added and improved local run/bootstrap commands.
- Added a **tmux-based Groq launch path** for local manual testing.
- Added a **Playwright E2E** scenario covering login → create document → AI rewrite → accept.
- Updated the written report set so it reflects the actual shipped repo instead of an old two-person or pre-implementation story.

Why this matters:

- The assignment explicitly grades setup, docs, and deviations.
- E2E coverage is one of the listed bonus items.

## Concrete Branch Evidence

Giorgi's work is visible in these local branches and merged slices:

- `feat/pr19-tooling-ci-baseline`
- `feat/pr20-ai-streaming-history`
- `feat/pr21-collab-hardening-bonuses`
- `feat/pr22-backend-integrity`
- `feat/pr23-partial-acceptance`
- `feat/pr24-e2e-tests`
- `feat/pr25-e2e-polish`

Representative commits include:

- `fa0ee0a` — AI streaming/history
- `3498345` — remote cursors and revoke enforcement
- `3237973` — backend integrity hardening
- `ff1806b` — partial AI suggestion acceptance
- `13f0606` and `47ea452` — docs/E2E alignment and test-boundary polish

## Validation Against TASKS.md

The Giorgi-owned items in `TASKS.md` are now present and working as follows:

### 3.2a Backend AI streaming

Status: present and working

Evidence:

- `backend/app/api/ai_jobs.py`
- `backend/app/services/ai/ai_service.py`
- `backend/app/tests/test_ai.py`

What to manually check:

- start an AI action on selected text
- text should appear progressively, not all at once
- cancel should stop the request
- backend should record the job in history

### 3.4a Context handling, prompts, provider abstraction

Status: present and working

Evidence:

- `backend/app/services/ai/prompts/templates.json`
- `backend/app/services/ai/prompts/templates.py`
- `backend/app/services/ai/ai_service.py`

What to manually check:

- provider can be switched to Groq in `.env`
- prompts are loaded from the prompt config files
- long text should not be blindly passed without truncation handling

### 3.5a AI interaction history backend

Status: present and working

Evidence:

- `/api/documents/{id}/ai-history`
- `backend/app/tests/test_ai.py`

What to manually check:

- after using AI, the history list should show the new entry
- the entry should include status/provider/model information

### 4.1b Backend AI tests

Status: present and passing

Evidence:

- `backend/app/tests/test_ai.py`
- `backend/app/tests/test_ai_jobs_permissions.py`

What to manually check:

- run `cd backend && .venv/bin/python -m pytest app/tests/test_ai.py app/tests/test_ai_jobs_permissions.py -q`

### 4.3c API docs for AI endpoints

Status: present

Evidence:

- backend Swagger docs at `/docs`

What to manually check:

- open `http://127.0.0.1:8000/docs`
- confirm AI endpoints are listed and described

### 4.3d AI-related deviations

Status: present

Evidence:

- `DEVIATIONS.md` AI section

What to manually check:

- the document should explain what changed from the design baseline and why

### Bonus B4 Partial acceptance

Status: present and working

Evidence:

- `frontend/src/components/AIPanel.tsx`
- `frontend/src/components/AIPanel.test.tsx`

What to manually check:

- generate a suggestion
- in Diff view, use the block checkboxes
- choose only some changed blocks
- click `Accept selected`
- only the chosen changes should be applied

## Validation Against AI1220_assignment2.pdf

The AI-related requirements from the Assignment 2 PDF map to the shipped implementation like this:

### PDF 3.2 Streaming

PDF requirement:

- stream token-by-token
- allow cancel
- show clear mid-stream errors
- preserve or clearly discard partial output

Shipped:

- SSE streaming in `backend/app/api/ai_jobs.py`
- progressive frontend rendering in `frontend/src/components/AIPanel.tsx`
- cancel path in backend and frontend
- partial output support recorded in backend history

### PDF 3.3 Suggestion UX

PDF requirement:

- compare original vs suggestion
- accept/reject/edit
- undo after acceptance

Shipped:

- diff mode
- side-by-side mode
- editable suggestion textarea
- accept/reject actions
- undo banner after apply
- partial acceptance on diff blocks

### PDF 3.4 Context and Prompts

PDF requirement:

- do not blindly send the whole document
- handle truncation/chunking
- prompts configurable, not hardcoded
- provider abstraction in one place

Shipped:

- prompt config in `templates.json`
- prompt rendering/truncation in `templates.py`
- provider abstraction in `ai_service.py`
- provider implementations split in `providers/`

### PDF 3.5 AI Interaction History

PDF requirement:

- log input/prompt/model/response/accept-reject status
- provide a history UI per document

Shipped:

- backend history endpoint with provider/model/prompt metadata
- frontend recent history list in the AI panel

### PDF 4.1 Backend Testing

PDF requirement:

- unit/API tests for AI invocation
- mocked LLM path

Shipped:

- backend tests covering buffered AI, streaming, cancellation, history, and permissions

### PDF Bonus Items

Relevant bonus items for Giorgi:

- remote cursor/selection tracking
- partial acceptance of AI suggestions
- E2E tests covering login through AI suggestion acceptance

Shipped:

- remote cursor/selection support
- partial AI acceptance
- Playwright end-to-end flow

## Manual Demo Checklist for Giorgi Scope

Use this exact checklist when you want to manually validate Giorgi's deliverables.

### AI streaming

1. Select text in the editor.
2. Click `Rewrite` or `Translate`.
3. Click the run button.
4. Expected:
   - a suggestion panel opens
   - text appears progressively
   - the UI should not just freeze and then show one final answer

### AI cancel

1. Start a long AI generation.
2. Click `Cancel Generation`.
3. Expected:
   - generation stops
   - the current active suggestion is cleared or marked appropriately
   - the job should not continue to stream forever

### AI history

1. Run several AI actions.
2. Look at the recent history list in the AI panel.
3. Expected:
   - recent jobs are listed
   - clicking a history item should reopen that suggestion for review

### Suggestion UX

1. Run AI on selected text.
2. Check all three views:
   - Diff
   - Side-by-side
   - Edit
3. Expected:
   - all views show the same suggestion in different forms
   - editing the suggestion should work

### Accept / reject / undo

1. Accept a suggestion.
2. Expected:
   - text is inserted into the editor
   - undo banner appears
3. Click `Undo`.
4. Expected:
   - original text returns
5. Run AI again and click `Reject`.
6. Expected:
   - suggestion closes without mutating the document

### Partial acceptance

1. Generate a suggestion with multiple changed diff blocks.
2. In Diff view, use the checkboxes.
3. Click `Accept selected`.
4. Expected:
   - only selected changed blocks are applied

### Groq provider

1. Ensure `.env` contains:
   - `AI_DEFAULT_PROVIDER=groq`
   - `GROQ_API_KEY=...`
2. Restart backend.
3. Run an AI action.
4. Expected:
   - request succeeds through Groq
   - no client-side API key prompt is needed

## Final Verification Commands

These are the final validation commands used for the shipped workspace:

- `cd backend && .venv/bin/python -m pytest app/tests/ -q`
- `cd frontend && npm test`
- `cd frontend && npm run build`
- `cd frontend && npm run test:e2e`

## Scope Boundary

Giorgi did not rewrite the whole system. The work was layered onto the existing codebase and focused on:

- AI implementation quality
- collaboration and permission hardening where it affected the grading outcome
- testability and submission alignment for the final deliverable
