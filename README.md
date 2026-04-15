# Collaborative Document Editor

Real-time collaborative document editor with an AI writing assistant, built as a university assignment PoC (Part 4 implementation based on Parts 1 & 2).

## What This Demonstrates

- **Real-time collaboration** -- Multiple users editing the same document simultaneously via Yjs CRDT over WebSocket, with live cursor/presence tracking.
- **AI writing assistant** -- Four actions (rewrite, summarize, translate, restructure) backed by a pluggable provider system supporting OpenAI, Anthropic Claude, and Ollama (local).
- **Document management** -- Create, list, search, update, and delete documents with workspace-level organization.
- **Sharing & permissions** -- Role-based access (owner / editor / viewer) with optional expiration dates.
- **Version history** -- Snapshot-based versioning with restore-to-previous-version support.
- **Audit trail** -- Event logging for all document operations.
- **Export** -- Download documents as HTML or plain text.
- **Authentication** -- JWT-based stateless auth with registration and login.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Database | SQLite (aiosqlite) |
| Frontend | React 19, TypeScript, Vite, Tiptap (ProseMirror) |
| Realtime | Yjs + y-protocols over FastAPI WebSocket, pycrdt on server |
| AI | httpx calls to OpenAI / Anthropic / Ollama APIs |
| Infra | Docker Compose |

## Prerequisites

- **Docker & Docker Compose** (recommended), or
- **Python 3.12+** and **Node.js 18+** for running locally without Docker

For AI features, you need at least one of:
- [Ollama](https://ollama.com) running locally (default, no API key needed)
- An OpenAI API key
- An Anthropic API key

## Quick Start — one command

After cloning and copying the env template:

```bash
cp .env.example .env          # adjust AI provider / API keys if needed
make install && make migrate  # first time only
make dev                      # or: ./run.sh
```

`make dev` starts backend (:8000) and frontend (:5173) together; `Ctrl-C` stops both. See `make help` for all targets (test, coverage, docker, clean, etc.).

## Quick Start (Docker)

```bash
cp .env.example .env
make docker    # wraps: docker-compose up --build
```

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API docs (Swagger)**: http://localhost:8000/docs

## Quick Start (Local, no Docker, manual)

If you'd rather not use `make`:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./collab_editor.db` | Database connection string |
| `SECRET_KEY` | `change-me-in-production` | JWT signing secret |
| `AI_DEFAULT_PROVIDER` | `ollama` | Default AI provider (`ollama`, `openai`, or `claude`) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:8b` | Ollama model name |
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key (optional) |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key (optional) |

## Running Tests

```bash
make test           # pytest -v
make test-cov       # pytest --cov=app --cov-report=term-missing
```

Tests use an in-memory SQLite database — no external services required. The suite is 65 tests; coverage target is **≥80 %** on `app/api/` and `app/services/permissions.py` (AI provider wire paths are excluded — they need live LLM backends). Current coverage: ~88 % overall.

## Architecture at a glance

For the full design, see `Part 2.md` (C4 diagrams, architectural drivers, component responsibilities). The short version:

| Driver (Part 2 priority order) | How the PoC addresses it |
|---|---|
| 1. Low-latency collab | pycrdt server authoritative doc + Yjs binary sync + awareness relay |
| 2. Failure isolation | AI jobs recorded in DB with their own status lifecycle; backend survives provider failures |
| 3. Security & audit | JWT access/refresh tokens, role-based access via `DocumentShare`, `audit_events` row per mutating action |
| 4. Non-destructive AI | Suggestions are stored separately from content; apply/reject is explicit and logged |
| 5. Horizontal scale | **PoC-limited** — single-process WebSocket, no Redis pub/sub (see DEVIATIONS.md) |
| 6. Team velocity | FastAPI + async SQLAlchemy for the team's Python stack; one repo, one compose file |

C4 diagrams live in `C4-diagram/` (source in `.puml`, pre-rendered PNGs at repo root).

## RBAC matrix

All endpoints below require a valid access token. The role needed comes from the caller's effective role on the target document (owner ≥ editor ≥ viewer). A user has a role if they are the document's `created_by` (=> owner), or hold a non-expired `DocumentShare` row for the document.

| Endpoint | Role required |
|---|---|
| `GET /api/documents/{id}` | viewer |
| `PATCH /api/documents/{id}` | editor |
| `DELETE /api/documents/{id}` | owner |
| `GET /api/documents/{id}/export` | viewer |
| `GET /api/documents/{id}/versions` | viewer |
| `POST /api/documents/{id}/versions/{vid}/restore` | editor |
| `GET /api/documents/{id}/shares` | owner |
| `POST /api/documents/{id}/shares` | owner |
| `PATCH /api/documents/{id}/shares/{sid}` | owner |
| `DELETE /api/documents/{id}/shares/{sid}` | owner |
| `POST /api/documents/{id}/share-links` | owner |
| `DELETE /api/documents/{id}/share-links/{sid}` | owner |
| `POST /api/shares/redeem` | any authenticated |
| `POST /api/documents/{id}/ai-jobs` | editor |
| `GET /api/ai-jobs/{id}` / `/suggestion` | viewer |
| `POST /api/ai-jobs/{id}/apply` / `/reject` | editor |
| `GET /api/documents/{id}/audit` | owner |
| `PATCH /api/workspaces/{id}/ai-policy` | workspace owner/admin (via `WorkspaceMember`) |
| `WS /ws/documents/{id}` | viewer to read, editor to send updates |

## WebSocket protocol

Endpoint: `ws://{host}/ws/documents/{document_id}?token={access_token}` — the token must be an **access** token (refresh tokens are rejected).

Close codes:
- `4401` — authentication required / invalid / wrong token type
- `4403` — authenticated but no access to this document
- `1000` — idle timeout (`WS_IDLE_TIMEOUT_SECONDS`, default 60) or normal close

Binary frames follow the [y-protocols](https://github.com/yjs/y-protocols) wire format:
- `[MSG_SYNC=0][SYNC_STEP1=0][varuint8array(state_vector)]`
- `[MSG_SYNC=0][SYNC_STEP2=1][varuint8array(update)]`
- `[MSG_SYNC=0][SYNC_UPDATE=2][varuint8array(update)]`
- `[MSG_AWARENESS=1][varuint8array(awareness_update)]`

Server-emitted JSON text frames (new in PR #8):
```json
{"type": "presence_leave", "user_id": "...", "connection_id": "..."}
{"type": "error", "code": "READ_ONLY", "detail": "..."}
```

The server applies Yjs updates to its authoritative `pycrdt.Doc`, broadcasts them to peers, and persists `yjs_state` to the DB every `WS_PERSIST_INTERVAL_UPDATES` applied updates (default 50) plus a final flush when the room empties.

## API reference

FastAPI serves interactive docs at **`http://localhost:8000/docs`** (Swagger) and **`/redoc`**. All endpoints have human-readable summaries and response-code annotations. For a flat listing, see the RBAC matrix above.

## Deviations from the Part 1 / Part 2 design

See **[DEVIATIONS.md](./DEVIATIONS.md)** for a per-item log of what shipped vs what the design doc described, with rationale and impact.

## Project Structure

```
backend/
  app/
    main.py              FastAPI application
    config.py            Pydantic Settings (loads .env)
    database.py          Async SQLAlchemy engine + session
    models/              ORM models (11 tables)
    schemas/             Pydantic request/response DTOs
    api/                 Route handlers
      documents.py       Document CRUD + export
      users.py           Register / login
      shares.py          Sharing & permissions
      versions.py        Version history & restore
      ai_jobs.py         AI writing jobs & suggestions
      audit.py           Audit trail
      deps.py            Dependency injection (DB, JWT auth)
    services/ai/         AI service layer
      providers/         OpenAI, Claude, Ollama implementations
      prompts/           Versioned prompt templates
    realtime/
      websocket.py       Yjs sync + awareness over WebSocket
  alembic/               Database migrations

frontend/
  src/
    pages/
      LoginPage.tsx      Auth (login + register)
      DocumentListPage.tsx  Document browser
      EditorPage.tsx     Editor with collaboration
    components/
      AIPanel.tsx        AI assistant sidebar
      PresenceBar.tsx    Active collaborators indicator
      ShareModal.tsx     Sharing dialog
      VersionPanel.tsx   Version history sidebar
      Toast.tsx          Notifications
```

## What This Does NOT Implement (Yet)

These are scoped out of the PoC intentionally; see DEVIATIONS.md for the full backend/infra list with rationale.

- **Operational Transform / full CRDT conflict resolution** — Yjs handles basic CRDT, no bespoke merge strategy beyond storing the binary Yjs state.
- **Workspace & team management UI** — Backend models exist, `WorkspaceMember` rows are checked on the AI-policy endpoint, but nothing in the running system seeds memberships (see DEVIATIONS #5).
- **Production auth hardening** — Access+refresh tokens ship, but no rotation, no revocation list, no OAuth/SSO, no email verification, no password reset.
- **Horizontal scaling** — Single-process WebSocket; no Redis pub/sub or sticky sessions.
- **Object storage for large documents** — Content is stored in the database (JSON column), not in S3/GCS.
- **Offline support / local-first sync** — Server emits `presence_leave` control frames and flushes state periodically, but the frontend doesn't yet queue edits while offline.
- **CI/CD pipeline** — No GitHub Actions. `make test-cov` is the canonical local gate before opening a PR.
- **Rate limiting on all endpoints** — Only AI job creation is rate-limited (20/min, 50 jobs/user).
- **Comprehensive E2E tests** — Backend has 65 unit+integration tests at ~88 % coverage; no Playwright/Cypress suite yet.

## License

University assignment -- not licensed for redistribution.
