# Collaborative Document Editor

## Abstract

This repository is the Assignment 2 implementation of a real-time collaborative document editor with an AI writing assistant. The shipped PoC uses FastAPI, SQLite, React 19, Tiptap, Yjs, and WebSocket-based collaboration, with AI suggestions streamed over Server-Sent Events. As of April 19, 2026, the repo reflects a three-person delivery story: Percy owns backend, auth, sharing, tooling, and most submission plumbing; CDuongg owns the editor, collaboration UX, offline/reconnect behavior, and frontend tests; Giorgi owns AI streaming/history/prompt work plus the late-stage hardening branches in the forked workspace.

## Table of Contents

1. [Assignment 2 Snapshot](#assignment-2-snapshot)
2. [Team and Ownership](#team-and-ownership)
3. [Branch and PR Evidence](#branch-and-pr-evidence)
4. [Shipped Scope](#shipped-scope)
5. [Quick Start](#quick-start)
6. [Environment and Secrets](#environment-and-secrets)
7. [Testing and Verification](#testing-and-verification)
8. [Report Index](#report-index)
9. [Known PoC Limits](#known-poc-limits)

## Assignment 2 Snapshot

- Course context: AI1220 Software Engineering, Spring 2026.
- Submission tip used for evidence: the local `main` HEAD at hand-in time. Branch-level evidence below records the important feature slices without assuming one fixed final hash.
- Upstream remote: `origin = https://github.com/TheCYPER/SoftProject1-OpenDoc.git`.
- Contribution evidence from `git shortlog -sn --all`: Percy 39 commits, CDuongg 16 commits, Giorgi31 11 commits.
- The authoritative implementation/status cross-check is split across:
  - [TASKS.md](./TASKS.md) for shipped status by rubric item
  - [DEVIATIONS.md](./DEVIATIONS.md) for design-vs-implementation differences
  - [Part 1.md](./Part%201.md), [Part 2.md](./Part%202.md), and [Part 3.md](./Part%203.md) for the report set

## Team and Ownership

| Member | Primary scope | Concrete evidence |
| --- | --- | --- |
| Percy | Backend API, auth, permissions, share-links, tooling, run scripts, root documentation | PRs #7-10 on `origin/*`, plus merge ownership on `origin/main` |
| CDuongg | Rich-text editor, Yjs collaboration UX, reconnect/offline flow, remote presence, frontend unit tests | PRs #1-4 and #12-18 on `origin/*`, plus review branch `review/pr-19-revoke-enforcement` |
| Giorgi | AI streaming/history/prompts, partial acceptance, late-stage hardening, local submission alignment in the fork | Local branches `feat/pr19-tooling-ci-baseline`, `feat/pr20-ai-streaming-history`, `feat/pr21-collab-hardening-bonuses`, `feat/pr22-backend-integrity`, `feat/pr23-partial-acceptance` |

## Branch and PR Evidence

| Date | Evidence | Owner(s) | What it shipped |
| --- | --- | --- | --- |
| March 25, 2026 | PR #1 and PR #2 on `origin` | Percy + CDuongg | Rich-text editor baseline and editor stabilization |
| March 31, 2026 | PR #3 `origin/feat/realtime-collaboration` | CDuongg | Yjs real-time sync |
| April 1, 2026 | PR #4 `origin/fix-viewer-readonly-enforcement` | CDuongg | Viewer read-only enforcement in UI and realtime path |
| April 15, 2026 | PRs #7-10 on `origin/*` | Percy | Refresh tokens, permission audit, share-by-link, backend tests, Makefile/run.sh, doc tooling |
| April 16-18, 2026 | PRs #12-18 on `origin/*` | CDuongg | Frontend refresh interceptor, autosave, headings/code blocks, suggestion comparison/edit/undo, reconnect hardening, frontend tests, offline editing |
| April 19, 2026 | `feat/pr19-tooling-ci-baseline` | Giorgi | Fresh-clone bootstrap and local CI targets |
| April 19, 2026 | `feat/pr20-ai-streaming-history` (`fa0ee0a`) | Giorgi | SSE AI streaming, cancel/status handling, AI history endpoint, prompt version capture |
| April 19, 2026 | `feat/pr21-collab-hardening-bonuses` (`3498345`) | Giorgi | Remote cursors plus revoke/session hardening |
| April 19, 2026 | `feat/pr22-backend-integrity` (`3237973`) | Giorgi | Sharing/collaboration state hardening |
| April 19, 2026 | `feat/pr23-partial-acceptance` (`ff1806b`) merged into local `main` | Giorgi | Partial AI suggestion acceptance in the editor |

## Shipped Scope

### Backend and Infrastructure

- JWT login plus refresh-token flow with access/refresh token separation.
- Document CRUD, sharing, share-by-link redemption, version listing/restore, export, and audit trail.
- Server-enforced permissions on document, version, sharing, AI, and workspace AI-policy routes.
- Single-process WebSocket collaboration server with Yjs sync, explicit close codes, `presence_leave`, periodic persistence, and read-only error frames.
- One-command local workflow via `run.sh`, `make install`, `make migrate`, and `make dev`.

### Frontend and Collaboration

- Tiptap editor with headings, inline code, code blocks, lists, bold, and italic.
- Debounced autosave with status indicator plus manual retry/save button.
- Presence chips, remote cursor rendering, reconnect/backoff behavior, and IndexedDB-backed offline persistence.
- Share modal, version panel, audit panel, HTML/text export actions, and viewer read-only state.
- Frontend unit tests for login, token storage, toast notifications, and the AI panel.

### AI and Giorgi Scope

- Four AI actions: rewrite, summarize, translate, and restructure.
- Server-Sent Events streaming endpoint at `/api/documents/{id}/ai-jobs/stream`.
- Progressive rendering in the AI sidebar, user cancellation, stale/partial badges, and AI history preview.
- Diff view, side-by-side comparison, editable suggestion mode, undo after apply, and partial-accept block selection.
- Prompt templates externalized to `backend/app/services/ai/prompts/templates.json` with truncation metadata and provider/model capture in history.

## Quick Start

### Local

```bash
cp .env.example .env
./run.sh
```

`./run.sh` copies `.env.example` if needed, installs dependencies, initializes the database, and starts backend plus frontend together.

### Make Targets

```bash
make install
make migrate
make dev
```

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Swagger/OpenAPI: `http://localhost:8000/docs`

### Docker

```bash
cp .env.example .env
make docker
```

Current `docker-compose.yml` starts only `backend` and `frontend`. It does not start an Ollama container.

## Environment and Secrets

`.env.example` is the source of truth for the root environment file. Copy it to `.env`, keep secrets local, and do not commit `.env`.

| Variable | Default in `.env.example` | When to set it |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./collab_editor.db` | Change only if you want a different DB path/driver |
| `SECRET_KEY` | `change-me-in-production` | Always replace outside local PoC/dev use |
| `AI_DEFAULT_PROVIDER` | `ollama` | Set to `openai`, `groq`, `claude`, or `ollama` |
| `OPENAI_API_KEY` | *(empty)* | Needed only when using OpenAI |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Override only for compatible proxies/endpoints |
| `OPENAI_MODEL` | `gpt-4o-mini` | Optional OpenAI model override |
| `GROQ_API_KEY` | *(empty)* | Needed only when using Groq |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Normally leave as-is |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Optional Groq model override |
| `ANTHROPIC_API_KEY` | *(empty)* | Needed only when using Claude |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Normally leave as-is |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Optional Claude model override |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Override for your actual Ollama host |
| `OLLAMA_MODEL` | `qwen2.5:8b` | Optional Ollama model override |

Secret-handling notes:

- The committed `SECRET_KEY` value is a placeholder for local use only. Any shared deployment must override it.
- Only one provider credential set is required. Leaving unused API keys blank is expected.
- For non-Docker local runs with a host Ollama daemon, `OLLAMA_BASE_URL=http://localhost:11434` is the usual value.
- For the current Docker setup, if Ollama runs on the host machine, use `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

## Testing and Verification

Verified during this documentation pass on April 19, 2026:

- `make test-cov`: 81 backend tests passed, 75% overall coverage.
- `cd frontend && npm test -- --run`: 21 frontend tests passed.

Notes:

- The frontend test run emits React `act(...)` warnings from `AIPanel.test.tsx`, but the suite still passes.
- A Playwright e2e scenario exists at `frontend/tests/e2e/login-edit-ai-accept.spec.ts`.
- `cd frontend && npm run test:e2e` passed locally on April 19, 2026 after fixing the Playwright web-server readiness probe.

## Report Index

- [Part 1.md](./Part%201.md): requirements engineering baseline
- [Part 2.md](./Part%202.md): system architecture and data model
- [Part 3.md](./Part%203.md): project management, ownership, workflow, and milestone evidence
- [TASKS.md](./TASKS.md): rubric-to-shipped-status matrix
- [DEVIATIONS.md](./DEVIATIONS.md): design-vs-implementation gap log

## Known PoC Limits

- SQLite and in-memory WebSocket rooms keep the stack easy to grade, but they are not horizontally scalable.
- AI apply/reject endpoints record disposition and audit metadata; the actual content mutation is performed in the editor and then persisted through normal save/autosave.
- Workspace AI-policy data exists, but workspace membership seeding is still incomplete, so that path remains mostly administrative scaffolding.
- For the full design-vs-implementation discussion, see [DEVIATIONS.md](./DEVIATIONS.md).
