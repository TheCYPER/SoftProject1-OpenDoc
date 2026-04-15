# Assignment 2 — Task Breakdown & Work Distribution

Based on a full scan of the current codebase against Assignment 2 requirements.

## Team & Ownership

| Member | Primary Area |
|--------|--------------|
| **Percy** | Backend — auth, documents, permissions, infrastructure, DevOps |
| **CDuongg** | Frontend & Testing — UI, rich-text editor, real-time collab UI, component/E2E tests |
| **Giorgi** | AI Agent — AI streaming, prompt templates, LLM provider abstraction, interaction history |

---

## Part 1: Core Application (25%)

| # | Task | Status | Owner | Priority |
|---|------|--------|-------|----------|
| 1.1a | **JWT Refresh Token (backend)** — Short-lived access token (15–30 min) + refresh token for silent re-auth | ❌ Currently 24h access token, no refresh | Percy | High |
| 1.1b | **Frontend token refresh** — Axios 401 interceptor to auto-refresh; no raw 401 errors during editing | ❌ No interceptor | CDuongg | High |
| 1.2a | **Rich-text editor extensions** — Add headings and code blocks (requirement: at minimum headings, bold, italic, lists, code blocks) | ⚠️ Only bold/italic/bullet/ordered list | CDuongg | Medium |
| 1.2b | **Auto-save** — Debounced auto-save on content change with status indicator | ❌ Manual save button only | CDuongg | High |
| 1.3a | **Server-side permission enforcement audit** — Ensure a viewer crafting direct API requests is still blocked on every endpoint (not just hidden buttons) | ⚠️ Partially done, needs full review | Percy | High |

## Part 2: Real-Time Collaboration (20%)

| # | Task | Status | Owner | Priority |
|---|------|--------|-------|----------|
| 2.1a | **Connection lifecycle** — Initial load, joining active sessions, disconnect/reconnect, state reconciliation; target <500ms propagation | ⚠️ Basic Yjs works; reconnect + offline sync need hardening | Percy (server) + CDuongg (client) | High |
| 2.2a | **Presence: who is online** — Active user indicator list (baseline requirement) | ✅ PresenceBar exists | — | Done |
| 2.2b | **[Bonus] Remote cursor & selection tracking** — Render other users' cursors/selections with distinct colors | ❌ | CDuongg | Low |
| 2.3a | **WebSocket auth** — No valid token = no session | ✅ Implemented | — | Done |
| 2.3b | **Offline editing + sync on reconnect** — Graceful degradation: continue editing offline, sync when back | ⚠️ Reconnect logic exists but offline editing untested | CDuongg | Medium |

## Part 3: AI Writing Assistant (25%) — Streaming is non-negotiable

| # | Task | Status | Owner | Priority |
|---|------|--------|-------|----------|
| 3.1a | **AI features (≥2)** — Ensure at least 2 features work end-to-end (rewrite, summarize, translate, etc.) | ⚠️ Backend has 4 templates; frontend has UI but no streaming | Giorgi | High |
| 3.2a | **AI Streaming — backend** — FastAPI `StreamingResponse` (SSE) or WebSocket; token-by-token delivery; handle mid-stream errors | ❌ Currently blocking full-response | Giorgi | **Critical** |
| 3.2b | **AI Streaming — frontend** — Render text progressively as chunks arrive; cancel button to abort generation | ❌ | CDuongg (with Giorgi on contract) | **Critical** |
| 3.3a | **Suggestion UX** — Compare original vs. suggestion before applying (side panel, inline diff, etc.); accept/reject/edit; undo after acceptance | ⚠️ Basic accept/reject exists, no comparison view, no undo | CDuongg | High |
| 3.4a | **Context & Prompts** — Send appropriate context (not full document blindly); truncation for long docs; prompt templates in config files (not hardcoded); LLM provider abstraction | ⚠️ Provider abstraction done; prompts are hardcoded dicts | Giorgi | High |
| 3.5a | **AI Interaction History — backend** — Log every interaction (input, prompt, model, response, accept/reject); history query endpoint | ⚠️ Backend models exist, missing query endpoint | Giorgi | Medium |
| 3.5b | **AI Interaction History — frontend** — Per-document history UI | ❌ | CDuongg | Medium |

## Part 4: Testing & Quality (20%)

| # | Task | Status | Owner | Priority |
|---|------|--------|-------|----------|
| 4.1a | **Backend tests — core** — auth (incl. refresh), document CRUD with permissions, WebSocket auth + message exchange | ⚠️ Basic tests exist, need coverage for refresh & new endpoints | Percy | Medium |
| 4.1b | **Backend tests — AI** — AI invocation (mock LLM), streaming, prompt templates, interaction history | ⚠️ Current AI tests mock non-streaming only | Giorgi | Medium |
| 4.2a | **Frontend tests** — Component tests (Vitest / React Testing Library) for auth flow, document UI, AI suggestion UI | ❌ No frontend tests | CDuongg | Medium |
| 4.3a | **Run script** — `run.sh` or `Makefile` to start both backend and frontend with one command | ❌ | Percy | Low |
| 4.3b | **README** — Setup, running, tests, architecture overview; comprehensive | ⚠️ Basic README exists | Percy (overall) + CDuongg (frontend section) + Giorgi (AI section) | Low |
| 4.3c | **API docs** — FastAPI auto-generated OpenAPI with meaningful descriptions and schemas | ⚠️ Auto-generated but descriptions may be sparse | Percy (core) + Giorgi (AI endpoints) | Low |
| 4.3d | **DEVIATIONS.md** — Document every difference from Assignment 1 design: what changed, why, improvement or compromise | ❌ | All three (each on their area) | Low |

## Part 5: Demo & Presentation (10%)

| # | Task | Owner |
|---|------|-------|
| 5.1 | **Live demo script** (5 min): register/login → rich-text editing + auto-save → sharing with roles → real-time collab in 2 windows → AI streaming + suggestion UX + cancel → version restore | All three (Percy: auth/docs, CDuongg: editor/collab, Giorgi: AI streaming) |
| 5.2 | **Q&A prep** — Each member must answer in depth about the parts they personally implemented; all members should handle general architecture questions | Each on their own parts |

## Bonus Items (up to +10 pts, each worth ≤2)

| # | Task | Status | Owner |
|---|------|--------|-------|
| B1 | **CRDT conflict resolution** (Yjs) — No data loss under adversarial conditions | ✅ Already using Yjs | — |
| B2 | **Remote cursor/selection tracking** with distinct colors/labels | ❌ | CDuongg |
| B3 | **Share-by-link** with configurable permissions and revocation | ❌ Schema exists, not implemented | Percy |
| B4 | **Partial acceptance of AI suggestions** (accept/reject individual parts) | ❌ | CDuongg (UI) + Giorgi (diff segmentation) |
| B5 | **E2E tests** (Playwright/Cypress) covering login through AI suggestion acceptance | ❌ | CDuongg |

---

## Ownership Summary

### Percy — Backend & Infrastructure

1. JWT refresh token mechanism (1.1a)
2. Server-side permission audit across all endpoints (1.3a)
3. WebSocket server-side lifecycle improvements (2.1a — server side)
4. Backend core tests — auth, documents, permissions, WebSocket (4.1a)
5. `run.sh` / Makefile (4.3a)
6. README core + API docs (4.3b, 4.3c)
7. DEVIATIONS.md — backend/infra sections (4.3d)
8. *[Bonus]* Share-by-link with revocation (B3)

### CDuongg — Frontend & Testing

1. Frontend token refresh interceptor (1.1b)
2. Rich-text: headings + code blocks (1.2a)
3. Auto-save with debounce and status indicator (1.2b)
4. WebSocket client-side lifecycle + reconnect (2.1a — client side)
5. Offline editing + reconnect hardening (2.3b)
6. **AI streaming frontend rendering + cancel button** (3.2b) — **TOP PRIORITY**
7. Suggestion UX: comparison view + accept/reject + undo (3.3a)
8. AI interaction history UI (3.5b)
9. Frontend component tests with Vitest + RTL (4.2a)
10. README frontend section + DEVIATIONS frontend section
11. *[Bonus]* Remote cursor tracking (B2), partial-accept UI (B4-UI), E2E tests (B5)

### Giorgi — AI Agent

1. **AI Streaming backend — FastAPI StreamingResponse (SSE) / WebSocket** (3.2a) — **TOP PRIORITY**
2. AI feature end-to-end validation (≥2 features) (3.1a)
3. Prompt templates externalization (config files, not hardcoded) + long document truncation (3.4a)
4. LLM provider abstraction review (swapping providers should require changes in one place only) (3.4a)
5. AI interaction history endpoint — query log of inputs/prompts/models/responses/accept-reject (3.5a)
6. Backend AI tests — streaming, mocked LLM, prompt rendering, interaction history (4.1b)
7. API docs for AI endpoints (4.3c)
8. DEVIATIONS.md — AI section (4.3d)
9. *[Bonus]* Partial-accept suggestion segmentation on backend (B4-backend)

---

## Coordination Notes

- **Streaming is non-negotiable** — A blocking AI call with a loading spinner will not pass. This is the single highest-priority item and requires tight coordination between Giorgi (backend stream) and CDuongg (frontend consumption).
- **AI contract review** — Any change to AI request/response schema (especially streaming chunk format) requires joint review by Giorgi + CDuongg. Document the contract in `backend/app/schemas/ai.py` + matching frontend types.
- **Permission model** — If Giorgi adds new AI endpoints, Percy must review to ensure they go through the same permission layer used by document endpoints (no AI bypass for viewers).
- **Every team member must contribute code** — Git attribution is checked. No commits = individual grade adjustment.
- **Meaningful commits & feature branches** — A single "final commit" is a red flag. Use feature branches and PRs with reviews.
