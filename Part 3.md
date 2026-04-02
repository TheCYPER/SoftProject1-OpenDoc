# Part 3: Project Management & Team Collaboration

## 3.1 Team Structure & Ownership

### Team Members and Roles

| Member | Role | Ownership Areas |
|--------|------|-----------------|
| **Percy** | Project Lead / Backend & Infrastructure | Backend API (FastAPI), database models & migrations, AI service layer, Docker/DevOps, CI configuration, repo management |
| **CDuongg** | Frontend & Collaboration Lead | React UI components, TipTap rich-text editor, Yjs CRDT integration, real-time presence, UX refinement |

### Codebase Ownership Map

```
backend/
  app/
    main.py, config.py, database.py    → Percy
    models/                             → Percy
    schemas/                            → Percy
    api/                                → Percy
    services/ai/                        → Percy
    realtime/websocket.py               → Percy (initial), CDuongg (Yjs upgrade)
  alembic/                              → Percy
  Dockerfile, requirements.txt          → Percy

frontend/
  src/
    components/EditorPage.tsx           → CDuongg
    components/AIPanel.tsx              → CDuongg (UI), Percy (API contract)
    components/PresenceBar.tsx          → CDuongg
    components/ShareModal.tsx           → CDuongg
    lib/collaboration.ts                → CDuongg
    api/client.ts                       → Percy (initial), CDuongg (extensions)

docker-compose.yml, .env.example        → Percy
```

### Cross-Cutting Feature Handling

Several features span multiple ownership areas. We handle these through explicit coordination:

- **AI Assistant**: Percy owns the backend AI service layer and provider abstraction; CDuongg owns the frontend `AIPanel.tsx` and text-selection UX. The API contract (defined in Part 2, Section 2.2) serves as the interface between the two. Changes to the AI job schema require both members to review the PR.
- **Real-time Collaboration**: Percy built the initial WebSocket relay; CDuongg replaced it with Yjs CRDT sync and y-prosemirror bindings. The WebSocket message protocol is documented in `backend/app/realtime/websocket.py` and any changes require joint review.
- **Document Sharing & Permissions**: Percy owns the backend `permissions.py` service and share API routes; CDuongg enforces read-only constraints in the editor UI. PR #4 (`fix-viewer-readonly-enforcement`) is an example of this coordination — CDuongg implemented the frontend enforcement after Percy defined the permission model.

### Technical Disagreement Resolution

When team members disagree on a technical choice, we follow this process:

1. **Discussion in the PR**: Both members state their position with concrete reasoning (performance data, complexity trade-offs, alignment with Part 2 architecture).
2. **Prototype if ambiguous**: If the trade-off is unclear, the proposer builds a small spike (time-boxed to 2 hours) to demonstrate feasibility.
3. **Owner decides within their domain**: The member who owns the affected area has final say, provided the decision does not contradict the architectural drivers defined in Part 2 (e.g., low-latency collaboration, failure isolation).
4. **Escalate if cross-cutting**: For decisions that affect both frontend and backend (e.g., changing the WebSocket protocol), both members must agree. If consensus cannot be reached, we default to the simpler solution that requires fewer changes.

---

## 3.2 Development Workflow

### Branching Strategy

We use a **feature-branch model** with `main` as the single production-ready branch.

| Branch Type | Naming Convention | Example |
|-------------|-------------------|---------|
| Feature | `feat/<kebab-case-description>` | `feat/realtime-collaboration` |
| Bug Fix | `fix/<kebab-case-description>` | `fix-viewer-readonly-enforcement` |
| Documentation | `docs/<description>` | `docs/part3-project-management` |

**Merge policy:**
- All feature and fix branches merge into `main` via **GitHub Pull Request**.
- PRs require at least **one approving review** from the other team member before merge.
- We use **merge commits** (not squash or rebase) to preserve the full commit history of each feature branch.
- Branch is deleted after merge.

**Evidence from our repo:** PRs #1–#4 all follow this model — each feature branch was reviewed, approved, and merged via GitHub PR.

### Code Review Process

| Aspect | Policy |
|--------|--------|
| **Who reviews** | The team member who does not own the changed area. Cross-cutting PRs require both members to review. |
| **Review criteria** | (1) Code correctness and no regressions, (2) adherence to Part 2 API contracts and data model, (3) no hardcoded secrets or security issues, (4) tests included for new functionality |
| **Turnaround time** | Reviews completed within 24 hours of PR creation |
| **Approval threshold** | 1 approval required (since the team has 2 members) |

**Review checklist (used for each PR):**
- [ ] Does the code match the API contract from Part 2?
- [ ] Are there tests covering the new/changed behavior?
- [ ] Does the code handle errors appropriately?
- [ ] Are there any hardcoded credentials or secrets?
- [ ] Does it break any existing functionality? (run `pytest app/tests/ -v`)

### Issue Tracking and Task Assignment

- **GitHub Issues** are used to define work items. Each issue has a clear title, description, and assignee.
- **GitHub Pull Requests** link to issues and serve as the primary record of what was implemented and why.
- Work is broken into **small, focused PRs** — each PR addresses a single feature or fix (e.g., PR #1 for TipTap editor, PR #3 for Yjs sync, PR #4 for read-only enforcement).
- We track progress informally using the PR list on GitHub: open PRs = in progress, merged PRs = done.

### Communication

| Tool | Purpose |
|------|---------|
| **WeChat** | Day-to-day communication, quick questions, coordination |
| **GitHub PR comments** | Technical discussion tied to specific code changes |
| **GitHub Issues** | Task definition and assignment |
| **Part 1–3 documents** | Architectural decisions and project-level agreements (checked into the repo) |

**Decision documentation:** Technical decisions that affect the architecture are documented in the Part 2 document or as comments in the relevant PR. This ensures decisions are not lost in chat messages and remain traceable to the code change that implements them.

---

## 3.3 Development Methodology

### Chosen Methodology: Scrum-Inspired Iterative Development

We use a lightweight **Scrum-inspired** approach adapted for a two-person university team. We chose this because:

1. **Iterative delivery** lets us demonstrate working software at each milestone, which is critical for a PoC where requirements may evolve based on feedback.
2. **Short sprints** (1 week) create natural checkpoints to reassess priorities and catch integration issues early.
3. **Simplicity** — with only two team members, heavy process overhead (daily standups, retrospectives) would slow us down. We keep the ceremonies minimal.

### Iteration Structure

| Element | Details |
|---------|---------|
| **Sprint length** | 1 week (Monday–Sunday) |
| **Planning** | Monday: review backlog, select items for the sprint, assign tasks |
| **Check-in** | Mid-week sync via WeChat to flag blockers |
| **Review** | Sunday: merge outstanding PRs, verify sprint goals |
| **Retrospective** | Brief (15 min) discussion on what worked and what to adjust |

### Backlog Prioritization

We prioritize work using the **MoSCoW method**, aligned with the assignment requirements:

| Priority | Examples |
|----------|---------|
| **Must Have** | Document CRUD, authentication, real-time collaboration, AI integration |
| **Should Have** | Document sharing with permissions, version history, presence awareness |
| **Could Have** | Workspace/team management, document export (PDF/Markdown), audit logging UI |
| **Won't Have (this semester)** | Horizontal scaling, OAuth/SSO, offline-first sync, mobile app |

### Handling Non-User-Visible Work

Infrastructure, data modeling, and testing do not produce user-visible features, but they are essential. We handle them as follows:

- **Infrastructure tasks** (Docker setup, Alembic migrations, CI) are treated as sprint items with the same priority as feature work. They are assigned to Percy and tracked via issues/PRs.
- **Data model design** was completed upfront as part of Part 2 (ER diagram with 11 tables) and implemented in the first sprint. Changes to the schema require a migration (tracked as a PR).
- **Tests** are required for every feature PR. The test is written as part of the same PR that introduces the feature, not as a separate task. This ensures test coverage grows with the codebase.

---

## 3.4 Risk Assessment

### Risk 1: AI Provider Latency and Cost Overruns

| Aspect | Details |
|--------|---------|
| **Description** | External AI providers (OpenAI, Claude) introduce network latency (1–10 seconds per request) and per-token costs that could make the AI assistant impractical for frequent use during demos or testing. |
| **Likelihood** | High — API latency is inherent; cost depends on usage volume. |
| **Impact** | AI features become slow or unusable during live demo. Budget for API calls is exhausted before the semester ends. Testing becomes expensive. |
| **Mitigation** | Default to **Ollama** (local, free inference) for development and demos. Use the `qwen2.5:8b` model which runs on consumer hardware. The abstract provider interface (`BaseProvider`) makes switching providers a config change, not a code change. |
| **Contingency** | If Ollama is too slow on the demo machine, pre-record AI assistant interactions as part of the demo. If cloud API costs exceed budget, disable cloud providers and rely solely on Ollama. |

### Risk 2: Real-Time Collaboration Conflicts and Data Loss

| Aspect | Details |
|--------|---------|
| **Description** | Yjs CRDT sync over WebSocket may fail silently under poor network conditions, causing edits to be lost or documents to diverge between collaborators. |
| **Likelihood** | Medium — Yjs is battle-tested, but our WebSocket relay is custom and has not been stress-tested. |
| **Impact** | Users lose edits without warning. Document state becomes inconsistent across clients. Trust in the collaboration feature is destroyed. |
| **Mitigation** | Yjs provides automatic conflict resolution via CRDT semantics (no manual merge needed). We persist Yjs document state to the database on every sync cycle. Frontend shows a connection-status indicator so users know when they are disconnected. |
| **Contingency** | If CRDT sync proves unreliable, fall back to a **last-write-wins** model with explicit save buttons (degraded but functional). Document versioning provides a recovery path for lost edits. |

### Risk 3: AI Provider API Breaking Changes or Downtime

| Aspect | Details |
|--------|---------|
| **Description** | OpenAI or Anthropic may change their API response format, deprecate models, or experience outages during critical development or demo periods. |
| **Likelihood** | Medium — API changes are infrequent but have occurred historically (e.g., OpenAI deprecating `text-davinci-003`). |
| **Impact** | AI features stop working entirely until the provider implementation is updated. If this happens during the demo, the AI assistant is non-functional. |
| **Mitigation** | The **abstract provider interface** (`BaseProvider`) isolates each provider's API details. If one provider breaks, switching to another is a one-line config change (`AI_DEFAULT_PROVIDER=ollama`). Ollama runs locally and is not subject to external API changes. |
| **Contingency** | Ship with Ollama as the default provider. Cloud providers are optional enhancements, not dependencies. |

### Risk 4: Frontend–Backend Integration Mismatches

| Aspect | Details |
|--------|---------|
| **Description** | With two team members working on frontend and backend independently, the API contract (request/response schemas, endpoint paths, error formats) may drift, causing integration failures when merging. |
| **Likelihood** | Medium — we have documented API contracts in Part 2, but undocumented edge cases exist. |
| **Impact** | Features that work in isolation break when integrated. Debugging integration issues consumes sprint time. |
| **Mitigation** | API contracts are defined in Part 2, Section 2.2 and enforced by Pydantic schemas on the backend. The frontend `api/client.ts` uses TypeScript interfaces that mirror the Pydantic schemas. Cross-cutting PRs require both members to review. |
| **Contingency** | If a mismatch is discovered late, the backend contract is treated as the source of truth (since Pydantic validates at runtime), and the frontend is updated to match. |

### Risk 5: Team Member Availability and Knowledge Silos

| Aspect | Details |
|--------|---------|
| **Description** | With only two team members, if one member is unavailable (illness, other coursework), the other cannot easily continue work in the absent member's ownership area due to unfamiliarity with the code. |
| **Likelihood** | Medium — university schedules are unpredictable, especially near exam periods. |
| **Impact** | Development stalls in one area (frontend or backend). Sprint goals are missed. The available member cannot fix bugs in the other's code. |
| **Mitigation** | Both members review each other's PRs, which builds familiarity with the full codebase. Key architectural decisions are documented in Part 2 and CLAUDE.md. The project uses standard frameworks (FastAPI, React) with extensive community documentation, lowering the barrier to contributing outside one's primary area. |
| **Contingency** | If one member is unavailable for more than 3 days, the other member takes ownership of the critical path and defers non-essential work. The `README.md` and `CLAUDE.md` provide enough context for either member to set up and run the full stack. |

### Risk 6: WebSocket Scalability Bottleneck

| Aspect | Details |
|--------|---------|
| **Description** | The current WebSocket implementation runs in a single FastAPI process. All active document sessions share one event loop. Under load (many concurrent editors), the server may become unresponsive. |
| **Likelihood** | Low for PoC (expected <10 concurrent users), but high if the project were deployed to production. |
| **Impact** | Editor becomes laggy or unresponsive. Real-time sync delays exceed the 100ms latency target from Part 1 requirements. |
| **Mitigation** | For the PoC, the single-process model is acceptable. The architecture is designed to support horizontal scaling via Redis pub/sub (documented in Part 2) when needed. |
| **Contingency** | If performance issues arise during demo, limit the number of concurrent editors per document to 3. Pre-test the demo scenario to identify the breaking point. |

---

## 3.5 Timeline and Milestones

### Completed Milestones

| Milestone | Target Date | Actual Date | Status |
|-----------|-------------|-------------|--------|
| **M0: Requirements & Architecture** | Mar 17 | Mar 17 | Done |
| Part 1 (requirements) and Part 2 (architecture) documents submitted. | | | |
| **M1: Backend API with Authentication** | Mar 20 | Mar 18 | Done |
| *Acceptance criteria:* FastAPI serves document CRUD endpoints (`POST/GET/PATCH/DELETE /api/documents`), user registration and login return valid JWT tokens, 13+ backend tests pass via `pytest app/tests/ -v`. | | | |
| **M2: Frontend Scaffold with Auth Flow** | Mar 20 | Mar 18 | Done |
| *Acceptance criteria:* React app renders login page, authenticates against backend, displays document list after login, and navigates to editor view. | | | |
| **M3: Rich Text Editor** | Mar 25 | Mar 25 | Done |
| *Acceptance criteria:* TipTap editor replaces textarea, supports bold/italic/headings/lists, content persists to backend via API. Verified by PR #1 and #2 merge. | | | |
| **M4: Real-Time Collaboration** | Mar 31 | Mar 31 | Done |
| *Acceptance criteria:* Two browser tabs editing the same document see each other's changes in real-time via Yjs CRDT sync over WebSocket. Presence bar shows active collaborators. Verified by PR #3 merge. | | | |
| **M5: Document Sharing & Permissions** | Apr 1 | Apr 1 | Done |
| *Acceptance criteria:* Owner can share a document with another user as editor or viewer. Viewers cannot edit (enforced in both frontend and backend). Verified by PR #4 merge. | | | |

### Upcoming Milestones

| Milestone | Target Date | Acceptance Criteria |
|-----------|-------------|---------------------|
| **M6: AI Assistant End-to-End** | Apr 7 | User selects text in the editor, chooses an AI action (rewrite, summarize, translate, restructure), receives a suggestion from Ollama, and can accept or reject it. AI job lifecycle (create → poll → apply/reject) works end-to-end. Verified by: (1) manual test with Ollama running in Docker, (2) `test_ai.py` passes with mocked provider. |
| **M7: Version History & Restore** | Apr 10 | User can view a list of document versions with timestamps, preview a past version, and restore it. Restoring creates a new version (non-destructive). Verified by: (1) `test_versions.py` passes, (2) manual test in the UI showing version list and restore action. |
| **M8: Docker Compose Full Stack** | Apr 14 | Running `docker-compose up --build` starts backend, frontend, and Ollama. A new user can register, create a document, edit it, share it, and use the AI assistant — all within Docker. Verified by a single end-to-end walkthrough documented in a screen recording or screenshot sequence. |
| **M9: Part 3 & Part 4 Submission** | Apr 16 | Part 3 (this document) and Part 4 (reflection) are complete and submitted. All code is merged to `main`, tests pass, and the README documents how to run the PoC. |
| **M10: Final Demo & Presentation** | Apr 21 | Live demo showing: (1) two users collaborating on a document in real-time, (2) AI assistant generating and applying a suggestion, (3) document sharing with permission enforcement, (4) version history and restore. Demo runs from Docker Compose on a single laptop. |

### Timeline Gantt (Weeks)

```
Week        Mar 17  Mar 24  Mar 31  Apr 7   Apr 14  Apr 21
            ──────  ──────  ──────  ──────  ──────  ──────
M0 Req/Arch ██
M1 Backend  ██
M2 Frontend ██
M3 Editor           ██
M4 Realtime         ████████
M5 Sharing                  ██
M6 AI E2E                           ██
M7 Versions                         ████
M8 Docker                                   ██
M9 Part 3/4                                 ██
M10 Demo                                            ██
```
