# Part 3: Project Management and Team Collaboration

## Abstract

This document records how the Assignment 2 implementation was actually organized and evidenced in the repository. It supersedes the earlier two-person narrative. The shipped workspace is a three-person effort: Percy handled backend/infrastructure and most submission plumbing, CDuongg handled the editor/collaboration frontend and frontend testing, and Giorgi handled AI streaming/history/prompts plus the April 19 fork-local hardening branches. Dates and branch names below use the repository state inspected on April 19, 2026.

## Table of Contents

1. [Team Structure and Ownership](#team-structure-and-ownership)
2. [Workflow and Repository Evidence](#workflow-and-repository-evidence)
3. [Coordination Model](#coordination-model)
4. [Risk Assessment](#risk-assessment)
5. [Timeline and Milestones](#timeline-and-milestones)

## 3.1 Team Structure and Ownership

### Team Members and Roles

| Member | Role | Ownership areas |
| --- | --- | --- |
| Percy | Backend and infrastructure lead | Auth, permissions, shares, versions, export, backend tests, Makefile, run scripts, root docs |
| CDuongg | Frontend and collaboration lead | React UI, Tiptap editor, Yjs client integration, offline/reconnect UX, presence UI, Vitest coverage |
| Giorgi | AI and submission-alignment lead | AI streaming/history/prompt templates, partial acceptance, fork-local hardening branches, AI documentation alignment |

### Ownership Map

| Area | Primary owner | Supporting owner(s) |
| --- | --- | --- |
| `backend/app/api/users.py`, auth flow, refresh tokens | Percy | CDuongg for frontend consumption |
| `backend/app/api/shares.py`, permissions, share-links | Percy | Giorgi for late-stage hardening |
| `backend/app/realtime/websocket.py` server lifecycle | Percy | Giorgi for bonus/hardening work |
| `frontend/src/pages/EditorPage.tsx` | CDuongg | Giorgi for AI-integrated editor behavior |
| `frontend/src/lib/collaboration.ts` and presence UX | CDuongg | Giorgi for cursor/revoke hardening |
| `backend/app/api/ai_jobs.py`, `backend/app/services/ai/*` | Giorgi | Percy for route/auth review |
| `frontend/src/components/AIPanel.tsx` | Giorgi + CDuongg | Shared AI contract work |
| Root `README.md`, `TASKS.md`, `DEVIATIONS.md`, report alignment | Percy + Giorgi | CDuongg for frontend status and evidence |

### Giorgi Scope for Assignment 2

Giorgi's scope is not just "AI in general"; it is evidenced by concrete branches and files:

- `feat/pr19-tooling-ci-baseline`: fresh-clone bootstrap and local CI targets.
- `feat/pr20-ai-streaming-history`: backend SSE streaming, AI status lifecycle, prompt version capture, AI history endpoint.
- `feat/pr21-collab-hardening-bonuses`: remote cursors and collaboration hardening.
- `feat/pr22-backend-integrity`: sharing/collaboration state fixes.
- `feat/pr23-partial-acceptance`: partial AI suggestion acceptance in the editor.

Representative commits: `fa0ee0a`, `3498345`, `3237973`, `ff1806b`.

## 3.2 Workflow and Repository Evidence

### Branching Strategy

The team used a feature-branch workflow with `main` as the integration branch.

| Branch type | Naming pattern | Example |
| --- | --- | --- |
| Feature | `feat/<description>` | `feat/pr20-ai-streaming-history` |
| Fix | `fix/<description>` or review branch | `fix-viewer-readonly-enforcement`, `review/pr-19-revoke-enforcement` |
| Docs | `docs/<description>` | `docs/update-part1-part2-implementation` |

Working rules:

- No direct feature work on `main`.
- Origin-hosted work is visible as GitHub PR merges #1-18.
- Fork-local Assignment 2 completion work on April 19, 2026 is evidenced by local branches `feat/pr19-*` through `feat/pr23-*`.
- At the time of inspection, `main` is the integration branch and the local `feat/pr24-e2e-tests` branch contains the E2E/doc pass on top of it.

### Review Policy

| Area | Review expectation |
| --- | --- |
| Backend-only change | Reviewed by a non-owner before merge where practical |
| Frontend-only change | Reviewed by a non-owner before merge where practical |
| Cross-cutting AI/editor contract | Giorgi and CDuongg coordinate together; Percy reviews permission/security impact |
| Docs/submission alignment | Percy and Giorgi update, with frontend status checked against CDuongg-owned code |

### Repository Evidence

| Date | Evidence | Owner(s) | Outcome |
| --- | --- | --- | --- |
| March 25, 2026 | PR #1 and PR #2 | Percy + CDuongg | Rich-text editor baseline lands |
| March 31, 2026 | PR #3 `origin/feat/realtime-collaboration` | CDuongg | Yjs real-time collaboration shipped |
| April 1, 2026 | PR #4 `origin/fix-viewer-readonly-enforcement` | CDuongg | Viewer editing blocked in UI and realtime path |
| April 15, 2026 | PRs #7-10 | Percy | Refresh tokens, permission audit, share-links, backend tests, Makefile/run.sh, infra/docs |
| April 16-18, 2026 | PRs #12-18 | CDuongg | Refresh interceptor, autosave, headings/code blocks, AI comparison UX, reconnect hardening, frontend tests, offline editing |
| April 19, 2026 | `feat/pr19-tooling-ci-baseline` | Giorgi | Local CI/bootstrap pass for fresh clones |
| April 19, 2026 | `feat/pr20-ai-streaming-history` | Giorgi | AI streaming/history work lands |
| April 19, 2026 | `feat/pr21-collab-hardening-bonuses` | Giorgi | Remote cursors and hardening land |
| April 19, 2026 | `feat/pr22-backend-integrity` | Giorgi | Sharing/collaboration fixes land |
| April 19, 2026 | `feat/pr23-partial-acceptance` merged into local `main` | Giorgi | Partial AI acceptance lands in local `main` |

### Contribution Evidence

`git shortlog -sn --all` on April 19, 2026:

- Percy: 39 commits
- CDuongg: 16 commits
- Giorgi31: 11 commits

This matters because the assignment expects visible contribution from every team member, not a single final merge from one account.

## 3.3 Coordination Model

### Cross-Cutting Feature Areas

| Feature | Coordination model |
| --- | --- |
| Auth refresh | Percy exposes backend contract; CDuongg implements client refresh behavior |
| Collaboration lifecycle | Percy owns server close codes/room behavior; CDuongg owns reconnect/offline UX; Giorgi hardens late-stage cursor/revoke behavior |
| AI streaming | Giorgi owns backend AI stream and prompt/history work; CDuongg integrates the panel UX; Percy reviews route protection |
| Partial suggestion acceptance | Giorgi implements the diff-block selection path; CDuongg ensures it works in the editor; Percy reviews audit/disposition semantics |

### Decision Rules

1. The owner of the affected area proposes the implementation.
2. If the change crosses backend/frontend or AI/editor boundaries, the supporting owner must review it.
3. If there is no agreement quickly, the simpler implementation that preserves the Part 2 architectural drivers wins for the PoC.
4. Any unresolved shipped-vs-design gap is recorded in `DEVIATIONS.md` instead of being hand-waved away.

## 3.4 Risk Assessment

### Risk 1: AI provider variability or outage

| Aspect | Detail |
| --- | --- |
| Likelihood | High |
| Impact | AI demo path becomes slow or unavailable |
| Mitigation | Provider abstraction plus environment-based provider switching (`openai`, `groq`, `claude`, `ollama`) |
| Current state | Streaming and history are resilient enough for provider errors, but there is still no separate worker tier |

### Risk 2: Realtime permission drift

| Aspect | Detail |
| --- | --- |
| Likelihood | Medium |
| Impact | A revoked or downgraded user might keep an editor session longer than intended |
| Mitigation | Review branch `review/pr-19-revoke-enforcement` plus later hardening branches on April 19 |
| Current state | Safe enough for the PoC, with explicit close/error handling in the realtime path |

### Risk 3: Offline edits vs authoritative state

| Aspect | Detail |
| --- | --- |
| Likelihood | Medium |
| Impact | Users may assume local offline edits are already persisted server-side |
| Mitigation | IndexedDB caching, reconnect banners, reconnect toast, before-unload warning while offline |
| Current state | Good browser-local recovery, but not a full cross-device offline sync system |

### Risk 4: Submission drift between code and docs

| Aspect | Detail |
| --- | --- |
| Likelihood | High before this doc pass |
| Impact | The grader sees a stale team story, stale task status, and incomplete deviations |
| Mitigation | Root docs rewritten against actual repo state, with branch/commit evidence and explicit ownership |
| Current state | Closed by this documentation alignment pass |

## 3.5 Timeline and Milestones

### Actual Milestones

| Milestone | Date | Evidence | Result |
| --- | --- | --- | --- |
| Requirements and architecture baseline | April 2, 2026 | `docs/update-part1-part2-implementation`, `docs/part3-project-management` | Part 1-3 report set established |
| Rich-text editor baseline | March 25-31, 2026 | PRs #1-3 | Editor and realtime base shipped |
| Permission-safe collaboration baseline | April 1, 2026 | PR #4 | Viewer enforcement shipped |
| Backend hardening and tooling | April 15, 2026 | PRs #7-10 | Refresh tokens, shares, tests, docs/tooling shipped |
| Frontend experience pass | April 16-18, 2026 | PRs #12-18 | Autosave, reconnect, tests, offline persistence, AI UX improvements |
| AI streaming and final hardening | April 19, 2026 | Local branches `feat/pr19-*` to `feat/pr23-*` | AI streaming/history, remote cursors, integrity fixes, partial acceptance shipped |

### Submission Readiness Summary

- The repo now tells a three-person story consistently.
- Giorgi's AI work is explicit in both the branch evidence and the owned feature list.
- Root docs, report parts, task matrix, and deviations are aligned to the same inspected repo state.
