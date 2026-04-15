# DEVIATIONS.md

What actually ships versus what the Part 1 / Part 2 design documents describe, and why. This file is organised by ownership: Percy owns the backend/infrastructure section below; CDuongg and Giorgi fill in the frontend and AI sections respectively.

> Scope of this document: **backend + infra only**. Frontend UI and AI-provider specifics are captured by their owners in separate sections of this file.

---

## Backend & infrastructure — Percy

### 1. Single-process backend (no separate AI worker)

**Part 2 design:** AI jobs run in a dedicated worker service with an async job queue (Celery/RQ/similar).
**Shipped:** AI jobs run inline in the FastAPI process via `app/services/ai/ai_service.py`. The request is held until the provider call completes, then the response returns synchronously with an `interaction_id`.
**Reason:** PoC scope. A single process keeps infra overhead minimal (no broker, no worker containers, no DLQ tuning). Splitting the AI worker into a separate service is a straightforward follow-up — the `ai_service.run_ai_job()` entry point is already the seam.
**Impact:** Long AI jobs block a request slot; no retry logic; no backpressure beyond slowapi rate limiting.

### 2. SQLite instead of PostgreSQL

**Part 2 design:** PostgreSQL with JSONB columns for document content.
**Shipped:** SQLite via `aiosqlite`. JSONB columns are stored as SQLite JSON (`sqlalchemy.JSON`).
**Reason:** Zero-setup local dev; tests run without a DB service; the assignment grader can clone and run without provisioning Postgres.
**Impact:** No real concurrent writers; `SELECT ... FOR UPDATE` not exercised; JSONB query operators unavailable (we only do full-column equality/null). Migration to Postgres is mostly a `DATABASE_URL` change plus type review for `JSON` vs `JSONB`.

### 3. JWT stateless auth without refresh-token rotation

**Part 2 design:** Short-lived access tokens + refresh tokens with rotation and revocation list.
**Shipped (PR #7):** 15-min access tokens, 7-day refresh tokens distinguished by a `type` claim. Refresh tokens are **not** rotated on exchange, and there is no revocation store.
**Reason:** PoC skip — rotation + revocation requires persistent state and key rolling that is disproportionate for a grade-able PoC. The `type` claim discriminator means adding rotation later is additive (store `jti` in Redis, reject on reuse).
**Impact:** A leaked refresh token is valid for its full 7 days; there is no server-side "log out everywhere". Acceptable for a PoC; flagged for production.

### 4. WebSocket: single-process, no Redis pub/sub

**Part 2 design:** WebSocket tier scales horizontally via Redis pub/sub fanout; sticky sessions optional.
**Shipped:** In-memory `_rooms: dict[document_id, Room]` in `realtime/websocket.py`. A single uvicorn process is the hard scaling limit.
**Reason:** PoC driver #5 (horizontal scale) was explicitly lower-priority in Part 2.
**Impact:** Multi-instance deployment requires Redis pub/sub fan-out and an election/lock for "who owns the authoritative `pycrdt.Doc` for doc X". Not done.

### 5. Permission surface — document-scoped, not workspace-seeded

**Part 2 design:** Users join a workspace, workspace membership rolls up to team-level and document-level grants.
**Shipped:** `DocumentShare` is the fully-enforced layer. `WorkspaceMember` rows exist in the schema, and PR #7 checks them for the AI-policy endpoint, but **nothing in the running system seeds workspace memberships**. A freshly-registered user has no workspace affiliation; they can only reach documents they personally created or were explicitly `DocumentShare`-granted.
**Reason:** Sharing covers every day-to-day flow in the PoC. Workspace seeding is a self-contained follow-up (registration → auto-create-personal-workspace + `WorkspaceMember(owner)` row).
**Impact:** `PATCH /api/workspaces/{id}/ai-policy` returns 403 for everybody until a member row is seeded. That is the correct safe default — it's documented here so the grader doesn't think it's a bug.

### 6. Permission audit — what was fixed vs. what's still loose

**Fixed in PR #7:**
- `POST /api/documents/{id}/ai-jobs` — editor required (was: any authenticated user could spend quota against any doc).
- `GET /api/ai-jobs/{id}` and `/suggestion` — viewer required.
- `POST /api/ai-jobs/{id}/apply` / `/reject` — editor required.
- `GET /api/documents/{id}/versions` — viewer required.
- `POST /api/documents/{id}/versions/{vid}/restore` — editor required.
- `PATCH /api/workspaces/{id}/ai-policy` — workspace owner/admin required.

**Still loose (known, accepted for PoC):**
- No rate limiting on non-AI endpoints.
- No CSRF tokens — the API is stateless bearer-token only; browser cookies are not used for auth.
- No per-share `allow_ai` enforcement — the flag is stored but the AI job creation path doesn't yet read it.

### 7. Reconnect / offline — server-side scope only

**Part 2 design:** Target <500 ms propagation, graceful reconnect with state reconciliation, offline edit queue with sync-on-reconnect.
**Shipped server-side (PR #8):**
- `presence_leave` JSON control frame emitted on disconnect so peers prune awareness without waiting for Yjs timeout.
- `asyncio.wait_for` idle timeout (60 s default) closes silent connections cleanly.
- Explicit close codes (4401 auth, 4403 forbidden, 1000 normal) so the client can distinguish reconnect-worthy from terminal errors.
- Viewer edit attempts receive a `{"type":"error","code":"READ_ONLY"}` JSON frame instead of being silently dropped.
- Periodic flush (every 50 applied updates) so a server crash mid-session doesn't drop in-flight edits.

**Out of scope for backend:** offline edit queue, reconciliation UI, reconnect backoff — those are client concerns tracked by CDuongg under TASKS 2.3b.

### 8. Share-by-link (Bonus B3)

**Shipped (PR #8):**
- Owner creates a link via `POST /api/documents/{id}/share-links` — `secrets.token_urlsafe(32)` returned exactly once; server stores only the sha256 hash.
- Owner revokes via `DELETE /api/documents/{id}/share-links/{share_id}`.
- Anyone authenticated redeems via `POST /api/shares/redeem {token}` — creates a `USER` share row for the caller; downstream checks reuse the existing `check_document_access` path.
- Redemption is idempotent; revoked/expired/invalid tokens return a generic 404 so token existence doesn't leak.

**Deviation:** the spec allowed link-holders to access a document without being registered. Shipped version requires authentication first, then redeem. This is a deliberate simplification — anonymous access would need a separate "link session" token type and new auth paths in every endpoint.

### 9. Committed `.env` file

**Issue:** `.env` is tracked in git with dev-only values (secret key `change-me-in-production`).
**Status:** Known, not fixed in this sprint. The secret is obviously a non-secret placeholder; production deployment would override via real env vars. `.env` will be moved to `.gitignore` as a follow-up.

### 10. No CI pipeline

**Status:** No GitHub Actions / equivalent. The `Makefile` `test-cov` target is the canonical "does it still work?" check and is intended to be run locally before every PR. Wiring to GitHub Actions is a one-file follow-up.

### 11. No ollama service in docker-compose

**Part 2 design:** Bundled local LLM for offline/airgap demos.
**Shipped:** `docker-compose.yml` only runs backend + frontend; ollama is expected to be running on the host (`host.docker.internal:11434`) or accessed via a cloud provider API key.
**Reason:** The ollama image is multi-GB and pulls a model on first start — disproportionate for the PoC grading path. Users who want it can run `ollama serve` on the host.

---

## Frontend — CDuongg

_[Owner: CDuongg. Covers frontend rich-text editor, collaboration client, AI UI, testing — see TASKS.md §91-103.]_

## AI — Giorgi

_[Owner: Giorgi. Covers AI streaming implementation, prompt externalisation, provider abstraction, interaction history — see TASKS.md §105-115.]_
