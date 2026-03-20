# Current State Report — Collaborative Document Editor PoC

## Project Overview

This is a real-time collaborative document editor with an integrated AI writing assistant, built as a proof-of-concept for the AI1220 Software Engineering assignment (Part 4). The system is designed to function like a simplified Google Docs with embedded LLM-powered features.

## What Has Been Implemented

### Backend (FastAPI + SQLAlchemy + SQLite)

| Area | Status | Details |
|------|--------|---------|
| Project structure | Done | Clean separation: `app/api`, `app/models`, `app/schemas`, `app/services`, `app/realtime` |
| Database models | Done | 11 SQLAlchemy models matching the Part 2 ER diagram (users, workspaces, documents, shares, versions, AI interactions, AI suggestions, audit events, teams) |
| Authentication | Done | JWT-based register/login with PBKDF2-SHA256 password hashing (stdlib, no external dependency issues) |
| Document CRUD | Done | Create, list, get, update (PATCH), soft-delete — all matching Part 2 API contracts |
| Version history | Done | List versions, restore to a previous version (non-destructive, creates new version entry) |
| Document sharing | Done | Create and revoke share rules (USER, TEAM, LINK grantee types with role-based access) |
| AI job lifecycle | Done | Create job → run AI → store suggestion → accept/reject/partial apply |
| AI provider abstraction | Done | Unified interface with three providers: OpenAI, Anthropic Claude, Ollama (local) |
| Prompt templates | Done | Versioned, template-based prompts for rewrite, summarize, translate, restructure |
| User-provided AI keys | Done | Users can supply their own API key and base URL per request; falls back to Ollama (free) |
| WebSocket stub | Done | Message relay between connected clients per document room, JWT-authenticated |
| Health endpoint | Done | `GET /api/health` for liveness checks |
| Automated tests | Done | **13 passing tests** covering health, auth (register, login, duplicate, wrong password, no token), document CRUD (create, get, list, update, delete, 404, unauthorized), versions (list + restore), shares (create + delete), AI jobs (lifecycle, reject, empty text) |

### Frontend (React + TypeScript + Vite)

| Area | Status | Details |
|------|--------|---------|
| Login / Register | Done | Single page with toggle, JWT stored in localStorage |
| Document list | Done | Lists all documents, create new document with title + workspace ID |
| Document editor | Done | Textarea-based editor with save (converts to prosemirror-json for storage) |
| AI panel | Done | Select action (rewrite/summarize/translate/restructure), optional provider config, accept/reject suggestions |
| Text selection support | Done | Textarea selection detection — AI processes only selected text or full document |
| API client | Done | Axios wrapper with JWT interceptor, configurable base URL |
| Type definitions | Done | TypeScript interfaces matching all backend response schemas |

### Infrastructure

| Area | Status | Details |
|------|--------|---------|
| Docker Compose | Done | Backend, Ollama (with healthcheck + auto model pull), frontend services |
| Environment config | Done | `.env.example` with all config vars, pydantic-settings for validation |
| CLAUDE.md | Done | Project guide for AI-assisted development |

### API Endpoints Implemented

All endpoints follow the Part 2 API design:

```
POST   /api/auth/register          — Register new user
POST   /api/auth/login             — Login, returns JWT
GET    /api/me                     — Current user profile
POST   /api/documents              — Create document
GET    /api/documents              — List documents
GET    /api/documents/{id}         — Get document
PATCH  /api/documents/{id}         — Update document
DELETE /api/documents/{id}         — Soft-delete document
GET    /api/documents/{id}/versions              — List versions
POST   /api/documents/{id}/versions/{vid}/restore — Restore version
POST   /api/documents/{id}/shares  — Share document
DELETE /api/documents/{id}/shares/{sid} — Revoke share
POST   /api/documents/{id}/ai-jobs — Create AI job
GET    /api/ai-jobs/{id}           — Get job status
GET    /api/ai-jobs/{id}/suggestion — Get suggestion
POST   /api/ai-jobs/{id}/apply     — Apply suggestion
POST   /api/ai-jobs/{id}/reject    — Reject suggestion
GET    /api/health                 — Health check
WS     /ws/documents/{id}?token=   — WebSocket (stub)
```

## What Remains To Be Done

### High Priority (Core PoC Requirements)

| Task | Description | Effort |
|------|-------------|--------|
| Real-time collaboration (CRDT) | Replace the WebSocket message relay stub with actual CRDT-based synchronization (e.g., Yjs). Currently the WebSocket only relays raw JSON messages — there is no conflict resolution or document state merging. | Large |
| Rich text editor | Replace the plain `<textarea>` with a proper rich-text editor (e.g., TipTap/ProseMirror) that supports formatting, cursors, and collaborative editing. | Large |
| Presence awareness | Show collaborator cursors, names, and online indicators in the editor. The WebSocket stub broadcasts presence events but the frontend does not render them. | Medium |
| Permission enforcement | The sharing and role model exists in the database, but API endpoints do not yet check permissions (e.g., a viewer can currently edit). Need middleware or dependency-based authorization checks. | Medium |

### Medium Priority (Polish & Completeness)

| Task | Description | Effort |
|------|-------------|--------|
| Workspace management | No UI or API for creating/managing workspaces. Currently workspace IDs must be entered manually. | Small |
| Auto-save | The editor requires manual save. Should auto-save periodically or on idle. | Small |
| Document export | Part 2 design includes export to common formats (PDF, Markdown). Not yet implemented. | Medium |
| Audit trail | The `audit_events` table exists but no events are being written. Need to emit audit events on key actions (share, version restore, AI usage). | Small |
| AI quota / rate limiting | Part 2 design includes per-user quotas and organization-level budgets. Not yet implemented. | Medium |
| Error handling UX | Frontend error handling is minimal (alert/console.log). Should show toast notifications and handle edge cases gracefully. | Small |

### Low Priority (Nice to Have)

| Task | Description | Effort |
|------|-------------|--------|
| AI suggestion diff view | Show a proper diff between original and suggested text, with partial accept per block. Currently shows full replacement only. | Medium |
| Offline support | Part 1 requirements include offline editing with reconnection. Not addressed in the PoC. | Large |
| Alembic migrations | Migration infrastructure is set up but no migration files have been generated. Currently using `create_all()` at startup. | Small |
| Production Dockerfile | Current Dockerfiles are dev-oriented (hot reload). Need production builds (multi-stage, nginx for frontend). | Small |
| CI/CD pipeline | No automated testing or deployment pipeline. | Medium |

## Test Coverage

```
13 tests passing across 6 test files:
  - test_health.py      (1 test)   — health endpoint
  - test_auth.py        (4 tests)  — register, login, duplicate email, wrong password, no token
  - test_documents.py   (3 tests)  — CRUD lifecycle, 404, unauthorized access
  - test_versions.py    (1 test)   — version list and restore flow
  - test_shares.py      (1 test)   — share create and delete
  - test_ai.py          (3 tests)  — AI job lifecycle, reject, empty text handling
```

## Git History

```
55d24a3 fix: Ollama connection in Docker — add depends_on, healthcheck, auto-pull
d3b9feb fix: support text selection for AI assistant
72134e9 fix: replace passlib/bcrypt with stdlib pbkdf2_hmac for password hashing
61272ed feat: scaffold React frontend with login, document list, editor, and AI panel
747eeaf feat: add backend framework with FastAPI, SQLAlchemy, AI service, and tests
9ce9855 part1 & part 2
```

## How to Run

```bash
# Option 1: Docker (recommended)
cp .env.example .env
docker-compose up --build
# Frontend: http://localhost:5173
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs

# Option 2: Local development
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

cd frontend && npm install && npm run dev

# Run tests
cd backend && source .venv/bin/activate && pytest app/tests/ -v
```
