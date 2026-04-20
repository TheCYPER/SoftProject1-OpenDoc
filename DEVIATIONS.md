# Assignment 2 Deviations

## Abstract

This file logs the meaningful differences between the Part 1 / Part 2 design baseline and the shipped Assignment 2 workspace as inspected on April 19, 2026. Ownership is explicit: Percy covers backend and infrastructure, CDuongg covers frontend and collaboration UX, and Giorgi covers AI implementation and late-stage AI-related hardening.

## Table of Contents

1. [Backend and Infrastructure](#backend-and-infrastructure)
2. [Frontend and Collaboration UX](#frontend-and-collaboration-ux)
3. [AI Implementation](#ai-implementation)

## Backend and Infrastructure

### 1. Single FastAPI process instead of a separate AI worker

**Design baseline:** Part 2 described AI orchestration as a separable asynchronous service with queue-like behavior.

**Shipped:** AI jobs run inside the FastAPI application process. The streaming path uses SSE and in-process task management rather than a broker/worker pair.

**Reason:** This keeps the PoC easy to run and grade without Redis, Celery, or a second Python service.

**Impact:** Long-running AI work still shares backend capacity with the REST API. This is acceptable for PoC scale but not a production isolation strategy.

**Classification:** PoC compromise.

### 2. SQLite instead of PostgreSQL

**Design baseline:** Part 2 assumed PostgreSQL as the primary durable store.

**Shipped:** Root `.env.example` defaults to SQLite via `sqlite+aiosqlite:///./collab_editor.db`.

**Reason:** Zero-setup local development and simpler grading. The backend and tests run without provisioning a separate database service.

**Impact:** The system does not exercise production-grade concurrency or PostgreSQL-specific features such as JSONB semantics.

**Classification:** Improvement for local DX, compromise for scale realism.

### 3. Refresh tokens exist, but there is no rotation or revocation store

**Design baseline:** Short-lived access tokens plus refresh-token rotation and server-side invalidation.

**Shipped:** Access/refresh token separation is implemented, but the same refresh token remains valid until expiry and there is no revocation list.

**Reason:** Rotation and revocation would add persistent token-state management that was out of scope for the grading path.

**Impact:** A leaked refresh token remains usable until it expires. This is explicitly acceptable only for the PoC threat model.

**Classification:** PoC compromise.

### 4. Real-time collaboration is single-process and in-memory

**Design baseline:** Horizontal scale via a shared pub/sub layer and multi-instance realtime nodes.

**Shipped:** `backend/app/realtime/websocket.py` holds an authoritative `pycrdt.Doc` per document in an in-memory room registry and merges client updates into it before fan-out. There is no Redis fan-out or cross-node state sharing.

**Reason:** The assignment demo workload does not require multi-instance deployment, and keeping the CRDT in-process removes one moving part for grading.

**Impact:** Character-level merges are real (bonus: CRDT), but the collaboration server is bounded to one process. A real deployment would need shared presence/update fan-out plus document ownership coordination.

**Classification:** Known PoC limit.

### 5. Share-by-link requires authentication before redemption

**Design baseline:** Anonymous link-holders could potentially reach a document directly through a share link.

**Shipped:** Link redemption is authenticated. The token is redeemed into a normal `DocumentShare` row for the current user.

**Reason:** This reuses the existing auth and permission model and avoids introducing anonymous session tokens into every downstream route.

**Impact:** The UX is slightly stricter than the original idea, but authorization is simpler and safer.

**Classification:** Intentional security simplification.

### 6. Workspace AI policy is configurable but not runtime-enforced

**Design baseline:** Workspace membership would be part of the normal onboarding path and AI policy (per-role allowed features, monthly budget, per-user quota) would gate AI job creation.

**Shipped:** `WorkspaceMember` and the `PATCH /api/workspaces/{id}/ai-policy` endpoint exist (`backend/app/api/workspaces.py`), and the policy JSON is persisted, but `backend/app/api/ai_jobs.py` does not consult `workspace.ai_policy_json` before creating a job. Registration also does not auto-seed workspace membership for new users.

**Reason:** Document-level sharing covered the main grader-visible flows first, and the AI provider/streaming layer was prioritized over workspace-level governance.

**Impact:** Workspace AI policy is an administrative scaffold today: policy can be stored, but it does not yet block AI jobs in practice.

**Classification:** Partial implementation.

### 7. Docker Compose does not include an Ollama service

**Design baseline:** A bundled local AI provider was part of the aspirational all-in-one development story.

**Shipped:** `docker-compose.yml` starts only `backend` and `frontend`. Ollama must run separately if it is the selected provider.

**Reason:** Shipping a multi-GB model image was disproportionate for the assignment workflow.

**Impact:** The root `.env.example` default `OLLAMA_BASE_URL=http://ollama:11434` must often be overridden in real local setups.

**Classification:** PoC compromise.

### 8. CI pipeline covers backend and frontend only

**Design baseline:** The process expected PR evidence and automated quality checks.

**Shipped:** `.github/workflows/ci.yml` runs `make install-backend`, `make migrate`, `make test-cov`, `make frontend-test`, and `make frontend-build` on every push and pull request. It does not yet run the Playwright E2E suite.

**Reason:** The unit-test layer was stabilized first; the E2E suite still requires a browser runtime and is left to local runs to keep PR feedback fast.

**Impact:** Remote CI verifies 81 backend tests and 21 frontend tests on every PR, but the bonus E2E scenario is only verified locally.

**Classification:** Partial CI coverage.

## Frontend and Collaboration UX

### 1. Offline editing is browser-local via IndexedDB, not a generalized cross-device queue

**Design baseline:** Offline recovery was described functionally, without locking into a storage strategy.

**Shipped:** The editor uses `y-indexeddb` to cache Yjs state in the current browser profile.

**Reason:** This gives low-friction offline persistence and reconnect merge behavior with very little custom code.

**Impact:** Offline drafts survive reloads in the same browser, but this is not a portable offline queue that can move across devices or profiles.

**Classification:** Good PoC implementation with bounded scope.

### 2. Presence and remote cursors use lightweight Yjs awareness UX

**Design baseline:** Presence would remain readable even in crowded collaboration sessions.

**Shipped:** Presence chips show up to four collaborators plus an overflow count, and remote cursors use custom awareness builders and CSS labels.

**Reason:** The goal was to satisfy presence and cursor visibility requirements without building a separate crowded-session design system.

**Impact:** The current UI is strong for small-group collaboration but would need richer crowd handling for larger rooms.

**Classification:** PoC simplification.

### 3. Full-document AI apply is blocked for richly formatted documents

**Design baseline:** AI suggestions could be accepted as document mutations while preserving editor trust.

**Shipped:** The editor refuses full-document AI apply when rich formatting is present; selection-based apply is the safe path.

**Reason:** Converting an arbitrary formatted ProseMirror document to plain text and back would risk destructive formatting loss.

**Impact:** The shipped UX prefers correctness over convenience: full-document apply works only when the document is effectively plain text.

**Classification:** Intentional safety restriction.

### 4. Partial AI acceptance is composed on the client

**Design baseline:** Partial acceptance was described as a structured, revision-aware suggestion operation.

**Shipped:** The AI panel computes diff blocks client-side, lets the user choose blocks, applies the composed text in the editor, and then records the selected block ids through `/apply`.

**Reason:** This avoided building a server-side ProseMirror patch engine for the assignment.

**Impact:** The visible feature is present, but the backend records the choice rather than reconstructing the document delta itself.

**Classification:** Useful feature compromise.

### 5. The e2e path is a focused Playwright scenario, not a full regression suite

**Design baseline:** End-to-end testing was listed as a bonus capability.

**Shipped:** `frontend/tests/e2e/login-edit-ai-accept.spec.ts` covers register/login, edit, AI streaming, accept, save, and reload.

**Reason:** The team implemented one representative high-value scenario rather than a broad browser suite.

**Impact:** The repo contains bonus evidence, but e2e coverage is narrow and is not wired into `make ci`.

**Classification:** Partial bonus implementation.

## AI Implementation

### 1. Streaming uses SSE from the API service, not a separate queue-backed worker

**Design baseline:** Part 2 allowed for asynchronous AI handling with stronger service separation.

**Shipped:** `/api/documents/{id}/ai-jobs/stream` streams `job`, `delta`, `suggestion`, and `status` events directly from FastAPI.

**Reason:** SSE is simpler than a separate orchestration runtime and still satisfies the assignment's streaming requirement.

**Impact:** The streamed UX is correct, but AI throughput and API isolation are still bounded by the main backend process.

**Classification:** Pragmatic PoC choice.

### 2. Prompt templates are externalized to JSON plus Python rendering, not a database-backed prompt registry

**Design baseline:** Prompt templates should be configurable and versioned.

**Shipped:** Prompts live in `backend/app/services/ai/prompts/templates.json` and are rendered by `templates.py`, with a version string stored in history.

**Reason:** This makes prompts reviewable, centralized, and versioned without adding an admin UI or database configuration layer.

**Impact:** Template changes still require a code change and redeploy, but prompt sprawl in route handlers was avoided.

**Classification:** Improvement over hardcoded inline prompts, but less dynamic than the target architecture.

### 3. Provider settings are controlled server-side only

**Design baseline:** Part 2 discussed provider abstraction and flexible provider selection.

**Shipped:** Provider choice and model overrides are supported, but API keys and base URLs come only from server configuration. Legacy client-side secret/base-url fields are ignored by the backend schema.

**Reason:** Allowing raw provider secrets from the browser would be a security regression.

**Impact:** Provider switching remains possible, but only through server-controlled configuration.

**Classification:** Security improvement.

### 4. Cancelled or failed jobs can persist partial output in history

**Design baseline:** Earlier UX discussion implied that cancellation might simply discard the in-flight result.

**Shipped:** If a provider already emitted text before cancellation or failure, the backend can persist that partial output with `partial_output_available=true`.

**Reason:** This preserves auditability and makes debugging or manual recovery easier.

**Impact:** The live panel clears the active suggestion on cancel, but history may still show the partial output later.

**Classification:** Intentional behavioral deviation.

### 5. AI history visibility is owner-only

**Design baseline:** AI history was framed as something broader reviewers or admins might inspect.

**Shipped:** `/api/documents/{id}/ai-history` requires owner access.

**Reason:** This is the safest default while the broader review model remains under-specified.

**Impact:** Editors and viewers can use AI, but only owners can browse the full AI history list.

**Classification:** Conservative permission choice.

### 6. Apply and reject record disposition, but document mutation is not transactional on the backend

**Design baseline:** Suggestion application was described as a revision-aware server-side flow.

**Shipped:** The backend records suggestion disposition, partial block ids, and audit events. The actual text replacement happens in the editor and then reaches persistence through the normal save/autosave path.

**Reason:** Implementing safe ProseMirror-aware server-side patching was out of scope for the assignment.

**Impact:** The user-facing feature works, but the final mutation path is client-driven rather than a single backend transaction.

**Classification:** Cross-cutting PoC compromise.
