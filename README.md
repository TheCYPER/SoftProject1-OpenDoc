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

## Quick Start (Docker)

```bash
# 1. Clone and enter the project
git clone <repo-url> && cd SoftAssignment1

# 2. Create your .env from the template
cp .env.example .env
# Edit .env if you want to change the AI provider or add API keys

# 3. Start everything
docker-compose up --build
```

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API docs (Swagger)**: http://localhost:8000/docs

## Quick Start (Local, no Docker)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload --port 8000
```

### Frontend

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
cd backend
source .venv/bin/activate
pytest app/tests/ -v
```

Tests use an in-memory SQLite database -- no external services required.

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

These are scoped out of the PoC intentionally:

- **Operational Transform / full CRDT conflict resolution** -- The Yjs layer handles basic CRDT, but there is no server-side merge strategy beyond storing the binary Yjs state.
- **Workspace & team management UI** -- Backend models exist, but the frontend only exposes a single implicit workspace.
- **Granular permission enforcement** -- Sharing roles are stored, but backend route guards do not enforce editor-vs-viewer restrictions on every endpoint.
- **Production auth hardening** -- No refresh tokens, no OAuth/SSO, no email verification, no password reset.
- **Horizontal scaling** -- Single-process WebSocket; no Redis pub/sub or sticky sessions for multi-instance deployment.
- **Object storage for large documents** -- Content is stored in the database (JSON column), not in S3/GCS.
- **Offline support / local-first sync** -- No service worker, no IndexedDB persistence.
- **CI/CD pipeline** -- No GitHub Actions or similar automation.
- **Rate limiting on all endpoints** -- Only AI job creation is rate-limited (20/min, 50 jobs/user).
- **Comprehensive E2E tests** -- Backend has unit/integration tests; no Playwright or Cypress suite.

## License

University assignment -- not licensed for redistribution.
