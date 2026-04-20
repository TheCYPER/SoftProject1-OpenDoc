# Assignment 2 Task Status

## Abstract

This file is the shipped-status ledger for the forked workspace as inspected on April 19, 2026. It replaces the old "planned work" view with a rubric-aligned status map tied to the code now present in the repo, including the fork-local April 19 branches owned by Giorgi.

## Table of Contents

1. [Team Ownership](#team-ownership)
2. [Status Legend](#status-legend)
3. [Part 1 Core Application](#part-1-core-application)
4. [Part 2 Real-Time Collaboration](#part-2-real-time-collaboration)
5. [Part 3 AI Writing Assistant](#part-3-ai-writing-assistant)
6. [Part 4 Testing and Quality](#part-4-testing-and-quality)
7. [Bonus Items](#bonus-items)
8. [Open Caveats](#open-caveats)

## Team Ownership

| Member | Primary ownership |
| --- | --- |
| Percy | Backend API, auth, permissions, sharing, tooling, root docs, submission plumbing |
| CDuongg | Frontend editor, collaboration UX, offline/reconnect behavior, frontend tests |
| Giorgi | AI streaming/history/prompts, fork-local hardening branches, partial acceptance, documentation alignment for AI scope |

## Status Legend

- `DONE`: shipped and evidenced in the current workspace.
- `DONE*`: shipped, with a documented PoC caveat in `DEVIATIONS.md`.
- `PARTIAL`: code exists or the path is started, but it is not fully verified as a submission-safe deliverable.

## Part 1 Core Application

| Item | Status | Owner(s) | Evidence | Notes |
| --- | --- | --- | --- | --- |
| 1.1a JWT refresh token backend | `DONE` | Percy | PR #7 / `fc12ae1` | 15-minute access + 7-day refresh tokens |
| 1.1b Frontend silent token refresh | `DONE` | CDuongg | PR #12 / `f4208da` | Axios + fetch refresh handling |
| 1.2a Rich-text headings and code blocks | `DONE` | CDuongg | PR #14 / `14cd53e` | Headings, inline code, code blocks in toolbar |
| 1.2b Debounced autosave | `DONE` | CDuongg | PR #13 / `50c7200` | Autosave plus save-status indicator |
| 1.3a Server-side permission enforcement audit | `DONE*` | Percy + CDuongg + Giorgi | `fc12ae1`, `f1898ce`, `3237973` | Core routes are server-enforced; remaining infra-grade hardening is tracked as deviations |

## Part 2 Real-Time Collaboration

| Item | Status | Owner(s) | Evidence | Notes |
| --- | --- | --- | --- | --- |
| 2.1a Connection lifecycle and reconnect hardening | `DONE*` | Percy + CDuongg + Giorgi | `96c7295`, `3e0ce6f`, `3237973` | Reconnect/backoff, close codes, revoke handling, and lifecycle hardening shipped |
| 2.2a Presence: who is online | `DONE` | CDuongg | `PresenceBar.tsx`, Yjs awareness wiring | Presence chips render active collaborators |
| 2.2b Bonus: remote cursors and selections | `DONE` | Giorgi + CDuongg | `3498345` | Custom cursor builders and remote caret styling shipped |
| 2.3a WebSocket auth | `DONE` | Percy | PR #7 / backend realtime auth checks | Invalid/expired/wrong-role users are rejected |
| 2.3b Offline editing and sync on reconnect | `DONE*` | CDuongg | PR #18 / `f91cf34` | IndexedDB-backed offline persistence is shipped; see caveats in `DEVIATIONS.md` |

## Part 3 AI Writing Assistant

| Item | Status | Owner(s) | Evidence | Notes |
| --- | --- | --- | --- | --- |
| 3.1a At least two AI features end-to-end | `DONE` | Giorgi | `backend/app/services/ai/prompts/templates.json`, `AIPanel.tsx` | Rewrite, summarize, translate, restructure are wired |
| 3.2a Backend AI streaming | `DONE` | Giorgi | `feat/pr20-ai-streaming-history` / `fa0ee0a` | SSE endpoint, delta events, cancel path, status updates |
| 3.2b Frontend AI streaming and cancel | `DONE` | Giorgi + CDuongg | `AIPanel.tsx`, `frontend/src/api/ai.ts` | Progressive render plus cancel button shipped |
| 3.3a Suggestion UX | `DONE*` | CDuongg + Giorgi | PR #15 / `24587b1`, local `feat/pr23-partial-acceptance` / `ff1806b` | Diff, side-by-side, editable suggestion, undo, and partial accept shipped |
| 3.4a Context handling, prompt templates, provider abstraction | `DONE` | Giorgi | `templates.json`, `templates.py`, `ai_service.py` | Prompts externalized and truncated; provider abstraction supports OpenAI/Groq/Claude/Ollama |
| 3.5a AI interaction history backend | `DONE` | Giorgi | `fa0ee0a`, `/api/documents/{id}/ai-history` | History includes provider/model/prompt/disposition metadata |
| 3.5b AI interaction history frontend | `DONE` | Giorgi + CDuongg | `AIPanel.tsx` recent history list | Last few AI jobs can be reopened in the sidebar |

## Part 4 Testing and Quality

| Item | Status | Owner(s) | Evidence | Notes |
| --- | --- | --- | --- | --- |
| 4.1a Backend core tests | `DONE` | Percy | `backend/app/tests/`, 81 collected tests | Auth, documents, sharing, realtime, versions, export, audit covered |
| 4.1b Backend AI tests | `DONE` | Giorgi | `backend/app/tests/test_ai.py`, `test_ai_jobs_permissions.py` | Streaming, cancellation, history, and permission paths covered |
| 4.2a Frontend tests | `DONE` | CDuongg | 21 passing Vitest tests | Login, tokens, toast, AI panel flows covered |
| 4.3a One-command run script / Makefile | `DONE` | Percy | `run.sh`, `Makefile` | Local bootstrap and local CI targets exist |
| 4.3b README | `DONE` | Percy + CDuongg + Giorgi | Root `README.md` | Updated in this documentation pass to match shipped scope |
| 4.3c API docs / OpenAPI summaries | `DONE` | Percy + Giorgi | FastAPI `/docs`, endpoint summaries in route decorators | AI endpoints are included |
| 4.3d `DEVIATIONS.md` | `DONE` | Percy + CDuongg + Giorgi | Root `DEVIATIONS.md` | Completed in this documentation pass across backend/frontend/AI |

## Bonus Items

| Bonus item | Status | Owner(s) | Evidence | Notes |
| --- | --- | --- | --- | --- |
| B1 CRDT conflict resolution via Yjs | `DONE` | CDuongg | Yjs collaboration path since PR #3 | Core collaboration model |
| B2 Remote cursor/selection tracking | `DONE` | Giorgi + CDuongg | `3498345` | Distinct user cursor colors and labels |
| B3 Share-by-link with revocation | `DONE` | Percy | `96c7295`, `test_share_links.py` | Authenticated redemption flow shipped |
| B4 Partial acceptance of AI suggestions | `DONE*` | Giorgi + CDuongg | `ff1806b` | Client-side partial apply plus backend disposition recording |
| B5 E2E tests covering login through AI acceptance | `DONE*` | Giorgi | `frontend/tests/e2e/login-edit-ai-accept.spec.ts` | Playwright scenario passes locally; it is still not wired into `make ci` |

## Open Caveats

- The main PoC caveats are documented in [DEVIATIONS.md](./DEVIATIONS.md), not repeated in full here.
- Bonus B5 is counted as shipped with the caveat that Playwright is a focused scenario and is still not part of `make ci`.
- Local `main` contains the April 19 fork-only branches that are not visible as GitHub PR numbers on `origin`, so branch names and commit hashes are used as evidence where PR numbers do not exist.
