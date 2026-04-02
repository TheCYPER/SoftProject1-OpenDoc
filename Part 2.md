# Part 2: System Architecture

## 2.1 Architectural Drivers

The architecture is driven first by the collaboration experience and only second by implementation convenience. That ranking matters: if the top priority were “ship the simplest CRUD app quickly,” a single synchronous backend with periodic saves would be enough. That would not satisfy the requirements in Part 1, especially FR-COL-01, FR-COL-03, FR-COL-04, NFR-LAT-01, NFR-AVAIL-03, and the AI-review workflows in FR-AI-02 and FR-AI-03.

| Rank | Architectural driver | Requirements that force it | Why it dominates the design |
| --- | --- | --- | --- |
| 1 | Low-latency, consistent real-time collaboration | FR-COL-01, FR-COL-02, FR-COL-03, FR-COL-04, NFR-LAT-01 | The product fails if collaboration feels delayed or if edits are lost. This drives a dedicated real-time synchronization path, local-first editor state, and an algorithm that converges after overlapping edits and reconnects. |
| 2 | Failure isolation and graceful degradation | NFR-AVAIL-01, NFR-AVAIL-02, NFR-AVAIL-03 | The core editor must continue working even if AI is slow or unavailable. This drives a separation between the collaboration path and the AI path, plus asynchronous job handling and reconnection logic. |
| 3 | Security, privacy, and auditable authorization | FR-DOC-03, FR-USER-01, FR-USER-02, FR-AI-04, FR-AI-05, NFR-SEC-01 to NFR-SEC-05 | Sensitive documents and third-party AI processing require explicit policy checks, least-privilege access, audit trails, and bounded prompt construction. |
| 4 | Reviewable, non-destructive AI assistance | FR-AI-02, FR-AI-03, US-07, US-08 | AI output must behave like a proposal, not a silent overwrite. This drives suggestion objects, base-revision tracking, partial acceptance, and stale-suggestion handling during concurrent editing. |
| 5 | Horizontal scalability under document and session growth | NFR-SCALE-01, NFR-SCALE-02, NFR-SCALE-03 | Supporting many active documents and dozens of editors per document requires stateless API scaling, horizontally scalable real-time nodes, and storage that does not assume a single application server. |
| 6 | Team velocity and architectural evolvability | Part 2.3, Part 4 PoC requirements | The team must build a working PoC and continue evolving it across the semester. This drives a monorepo with shared contracts, explicit module boundaries, and a provider abstraction around AI. |

Two different rankings would produce a different design. For example, if cost minimization were ranked above collaboration fidelity, a polling-based editor with no dedicated real-time service and only on-demand AI calls would be plausible. This architecture instead prioritizes a trustworthy live-editing experience and therefore accepts the complexity of a specialized synchronization layer.

## Scope Clarification: Target Architecture vs Current PoC

This document intentionally describes both:

* the **target architecture** the team aims to reach during the semester, and
* the **current PoC scope** implemented for Assignment 1 Part 4.

To avoid ambiguity during grading, the default reading rule is:

* Sections in this Part 2 describe the **target architecture by default**.
* Any capability not fully implemented in the current codebase is explicitly marked as **PoC-limited** below.

| Area | Target architecture (design intent) | Current PoC scope (implemented now) |
| --- | --- | --- |
| AI execution model | Asynchronous job lifecycle with queue-like states, event publication, and non-blocking UX | AI request is handled within API request flow; status is persisted, but no separate worker/queue runtime |
| AI policy & role gating | Workspace policy + role-based feature controls enforced for invocation and outcomes | Basic policy data model and endpoint exist; enforcement is partial and not complete across all AI paths |
| Suggestion application model | Suggestion acceptance updates document state with full revision-aware flow | Suggestion records and dispositions are persisted; full end-to-end revision mutation flow is limited |
| Permissions surface | Uniform least-privilege checks across all sensitive routes | Core document/share permissions are present; some endpoints remain PoC-hardening candidates |
| Collaboration resiliency | Full reconnect semantics with explicit stale/rebase UX for AI+collaboration interactions | Core Yjs sync and reconnect are functional; advanced stale/rebase UX is partially implemented |
| Scalability strategy | Horizontally scalable API/realtime services with shared pub/sub layer | Single-process deployment profile suitable for PoC/demo scale |

This clarification is intended to keep architectural depth while making the current implementation boundary explicit and auditable.

## 2.2 System Design using the C4 Model

The architecture uses the same component IDs introduced in Section 1.5:

* **AC-01 Frontend Editor UI**
* **AC-02 Collaboration / Real-Time Sync Service**
* **AC-03 Backend API Service**
* **AC-04 Document Service**
* **AC-05 Versioning Service**
* **AC-06 Auth & Authorization Service**
* **AC-07 AI Orchestration Service**
* **AC-08 AI Provider Adapter**
* **AC-09 Export Service**
* **AC-10 Audit / Activity Log Service**
* **AC-11 Presence Service**
* **AC-12 Document Database / Storage**

At a high level, the system separates the editing path from the AI path. Real-time changes flow through AC-02 for low latency and convergence, while slower AI operations flow through AC-07 so that AI latency or failure does not interrupt normal editing.

### Level 1 - System Context Diagram

```mermaid
%%{init: {'c4': {'c4ShapeMargin': 95, 'diagramMarginY': 30}}}%%
C4Context
title Collaborative Document Editor with AI - System Context
Person(editor, "Collaborator", "Creates, edits, comments on, shares, and exports documents")
Person(admin, "Organization Admin", "Manages members, policies, and role-based AI availability")
Person(reviewer, "Team Lead / Compliance Reviewer", "Reviews version history and AI activity where permitted")
System_Ext(idp, "Identity Provider", "Authenticates users and may provide SSO")
System_Ext(llm, "Third-Party LLM Provider", "Processes bounded AI prompts and returns generated suggestions")

System_Boundary(prod, "Collaborative Document Editor Platform") {
  System(editorPlatform, "Collaborative Document Editor with AI", "Real-time collaborative editor with versioning, sharing, and AI-assisted writing")
}

Rel(editorPlatform, llm, "Sends AI prompts")
Rel(editorPlatform, idp, "Authenticates users, resolves identity")
Rel(editor, editorPlatform, "Edits, collaborates, requests AI help")
Rel(admin, editorPlatform, "Configures access and AI policies")
Rel(reviewer, editorPlatform, "Reviews version and AI logs")
```

![Context Diagram](https://www.plantuml.com/plantuml/png/ZPDFRziy3CRl_XHyStbJ86akE-tKh0ss0kaQD2s6dGB5Ocq2-kDHTD9is7SV5TiBiXR3Rh94_Xxo8NsLnB2qtXN_KIXTQn5gaIQzdytOx2yhahhTjWcvZ44mo6KP_Qnn9kISQHBhQ3kxVZTTvQkdk-NCcoJ8UhMvpXalSjba-l_G1atrYW2f4PwZSt5FeG970S442sVFn4bF4LGQN2oDSmTb_AxnJtond7-zVthSVBbz_BHPBZukFj-CBuf2I9m6gvRPHZP2EuIRMBP7dOKbYGnxRH7cjp25zI49UkZ1nGevnJ36OzW4HYTCv57-PZI2QG8v8as6-XF4C85K6yvlkJ5yQIBhlUsLq-XYW1lhAIZhdYiJwBiHYW7c-J8ht9bWAapWqM-HbTP4HoKDN8uEfrkJqERwpSwGraUEv70IODmHxZ7N_uZ6mnADXPdsw1j79fG83tr45kpE2NQQd2kfAKdaWwfr4gKwg7ZOryW83R8d4RGgrtctMRp8c6oZg5kBGNBiYkEERCUVjrBdwp8RbsVBwSZsvW1D5mVhzVqvppcVgw-9xNHbM97BvTqPLiybfgJ8RMo3xVnGdc-aupDAoo51XG7PY0Qajb9dizrv6eFSXvnk-33MPAlWls-ExhmyH_QZ2_XH07ICVb-6DuNyq_frxXit5V88vLaAdYA7oL2ekXtBXtuyKvCIfTpSdadqGHlxMHGFw5xLr5cwnc3JoIeruirWdUVRevi0Oufkfz_KJ_iCCO5NNYo6NsNe3u-KRoqcEPPIesiwoF1llE5dUAQgLMqmPPxxi9x3tz7ddrR_7F5wpmU0YrLEli9WM-z-0G00)

**Explanation**
This level shows the platform as a single system. The important architectural observation is that the product depends on two external systems with very different failure and trust characteristics: the identity provider is required for access control, while the LLM provider is optional and must never be allowed to break core document editing.

### Level 2 - Container Diagram

```mermaid
%%{init: {'c4': {'diagramMarginX': 80, 'diagramMarginY': 55, 'c4ShapeMargin': 180, 'boxMargin': 40}}}%%
C4Container
title Collaborative Document Editor with AI - Container Diagram
Person(editor, "Collaborator", "Uses the web editor and AI assistant")
Person(admin, "Organization Admin", "Manages sharing, roles, and AI policy")
System_Ext(idp, "Identity Provider", "OIDC / SSO provider")
System_Ext(llm, "Third-Party LLM Provider", "Hosted LLM API")

System_Boundary(prod, "Collaborative Document Editor Platform") {
  Container(web, "AC-01 Frontend Editor UI", "React + TipTap/ProseMirror + Yjs", "Rich-text editing, local state, AI panel, offline/reconnect")
  Container(api, "AC-03 Backend API Service", "Python FastAPI REST API", "Document CRUD, sharing, versioning, export, audit")
  Container(sync, "AC-02 Collaboration / Real-Time Sync", "Yjs over FastAPI WebSocket", "Merges updates via CRDT, awareness, presence broadcast")
  Container(ai, "AC-07 AI Orchestration Service", "Merged into FastAPI backend", "Prompts, AI policy/quota, multi-provider LLM calls, suggestion storage")
  ContainerDb(db, "Platform Database", "SQLite (aiosqlite)", "Users, workspaces, doc metadata + content, shares, versions, AI metadata, audit logs")
}

UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="1")

Rel(editor, web, "Edits, reviews suggestions", "HTTPS")
Rel(admin, web, "Policy and permissions", "HTTPS")
Rel(web, api, "Documents, versions/shares, AI jobs", "HTTPS")
Rel(web, sync, "Live session, presence updates", "WebSocket")
Rel(api, db, "Metadata, content, and audit", "SQL via SQLAlchemy async")
Rel(sync, db, "Yjs CRDT state persistence", "SQL")
Rel(ai, llm, "Prompts and completions", "HTTPS via httpx")
Rel(ai, db, "AI interaction and suggestion metadata", "SQL")
```
![Container Diagram](https://www.plantuml.com/plantuml/png/VLLTZ-8s57tdLzpEInaL9lseLAbFomBRHO92Xw3LFesS-0vurx6plZSmjEf_xxL9mj2k-aGmztpu-3Yy8LQ1cyeElZ6kj8r6E33Nz6kM1NLws1i-D4L364hl61q_bBxAQgjSn8o9jJL5Dlrvl8bBkzKognGn1bbwcWf26OVXeOxytqBZ15m92V01uTbRwq_6xS7A42YduUPd4qYUF8WuM5ygQy_2qRji1V25B_I3vUJZUfS_VLZaxv-Myz_cly-6zuC16xOoB5ggy46nEIBCVDaadRasx0ESP9CmMS0OUiimCseVL3NOO23lXfWcHt1tPVBXJhxl22dvFM41bwcq5Q5JH8POOhcxxsYKhemJr3hibJD_YXtlO18N8zTAERKNEZge8BcC87YBDEhuQczDUHQoxPaOgwVv2m-DhWMuqEZOy1asmH-DnkHilPXD8OFjTWrrktoBjRQIiVnWWXvlL13uShcweNZlPLYdvSbc8UWE_jOtJgjm7Wgpbi7_prUwmSy-L7VtyDS0hY4F9JC1JwRZxt-0To4LJ7UWtI8wU4HLCdm7kQbpLMTYZd1bGl115Zz-eZHZoiCu5Y7bdu9BVG5YnJXAqIc7TWJ--JbsBGieRNPOoidS-56rQVty16zL-JdQaOt35iFHb1Z5DcS-U0Vl577yvN6-pMKaUUstFNtSpKRNKpnY8EDTUiQNsWUM8ssq-RSwdLtPol_ukh4Ybu44OSUvgH2sCXRbPFVWXRltyW6BhHVJdBg48LQfgRLY-JmQ9RPckIYVL4279Bsg0nAw4g48NkbIqN_owEBu9OQu3kK1YLjBRIQzbWRZsFTcYajyARBWgvf5h-zmzgNnh4PGDPRDk6jdwbcyvp9ApLxi9o5YIM6FjzPcnL37xdJLWfbYLIXAVhP_B0qZY7rFNwmythStDGZpoOVFLAiIvLdx4YfafGKiVMfVSPUZG-fFBbdl1zl30-lt9AR-7WmUqVOlY4kbOuS55V1ey4IlTaFfMkNvPYjGmRLlX1QsIUca-rvZg0pHro1fDbMrhzmhhrbdNYn_yiNNqMtLbl6s4YQPQntQqYHatwaMdMHJygikZZwsv3jbqnv2QfryJgmKfv9zHTcMA3wsJ5BarCtBVOqx9qCSdRGydRP8MrjT6zNzPzGMRxDDml5lxAM7jbeIYX6tGPKHaGYkXzCVyLNtZNIugUm_)

**Explanation**
The container split is intentional. AC-01 is optimized for responsive editing and local recovery. AC-02 handles low-latency synchronization and AC-11 presence tracking via Yjs awareness protocol. AC-03 owns stable business APIs and security-sensitive resource checks. AC-07 is merged into the FastAPI backend for PoC simplicity but retains a separate service layer that can be extracted later. AC-12 is implemented as SQLite with document content stored as JSON and Yjs CRDT state as binary within the database.

#### Container responsibilities, technology choices, and communication

| Container | Main responsibility | Technology choice | Communication |
| --- | --- | --- | --- |
| AC-01 Frontend Editor UI | Rich-text editor, local state, collaborator presence, AI suggestion review | React 19, TipTap/ProseMirror, Yjs client, TypeScript | HTTPS to AC-03, WebSocket to AC-02 |
| AC-03 Backend API Service | Resource APIs, permissions, versions, audit, export | Python FastAPI with SQLAlchemy async | HTTPS with AC-01, SQL to SQLite via aiosqlite |
| AC-02 Collaboration / Real-Time Sync Service | Real-time document updates, Yjs CRDT sync, awareness, reconnect flow, AC-11 Presence Service | FastAPI WebSocket with y-protocols | WebSocket with AC-01, Yjs state persisted to SQLite |
| AC-07 AI Orchestration Service | AI job execution, prompt building, quota checks, AI result persistence | Merged into FastAPI backend as a service layer with abstract provider interface | SQL reads/writes, HTTPS to LLM providers (OpenAI, Claude, Ollama) via httpx |
| AC-12 Document Database / Storage | Persistent metadata, document content (JSON), Yjs CRDT state (binary), versions, AI logs | SQLite via aiosqlite with SQLAlchemy async ORM | SQL via async sessions |

### Level 3 - Component Diagram for AC-07 AI Orchestration Service

```mermaid
%%{init: {'c4': {'diagramMarginX': 90, 'diagramMarginY': 70, 'c4ShapeMargin': 180, 'boxMargin': 45, 'c4ShapePadding': 18}}}%%
C4Component
title AC-07 AI Orchestration Service - Component Diagram
Container(api, "AC-03 Backend API Service", "Python FastAPI", "Creates AI jobs and reads suggestions")
System_Ext(llm, "LLM Providers", "OpenAI, Claude, or Ollama")
ContainerDb(db, "Platform Database", "SQLite (aiosqlite)", "Policies, AI interactions, suggestion metadata")
Container(sync, "AC-02 Collaboration / Real-Time Sync Service", "FastAPI WebSocket", "Publishes job status to collaborators")

Container_Boundary(ai, "AC-07 AI Orchestration Service") {
  Component(policyGuard, "Policy & Quota Guard", "Domain service", "Checks policy, entitlement, and quota")
  Component(requestHandler, "AI Job Handler", "Queue consumer / application service", "Validates jobs and coordinates execution")
  Component(contextResolver, "Context Resolver", "Domain service", "Loads selection context and revision metadata")
  Component(promptRegistry, "Prompt Template Registry", "Versioned template catalog", "Resolves prompt templates and model settings")
  Component(eventPublisher, "Result Publisher", "Event publisher", "Publishes job status events to the session")
  Component(providerAdapter, "AC-08 AI Provider Adapter", "Provider abstraction", "Maps requests and responses to the LLM provider")
  Component(suggestionComposer, "Suggestion Composer", "Diff and proposal builder", "Builds reviewable suggestions and stale/conflict flags")
  Component(auditLogger, "AI Audit Logger", "Persistence component", "Stores interaction records and disposition metadata")
}

UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="1")

Rel(api, requestHandler, "Enqueue AI job")
Rel(requestHandler, policyGuard, "Check policy and quota")
Rel(requestHandler, contextResolver, "Load document context")
Rel(requestHandler, promptRegistry, "Load prompt template")
Rel(requestHandler, providerAdapter, "Call provider adapter")
Rel(providerAdapter, llm, "Generate completion")
Rel(requestHandler, suggestionComposer, "Build reviewable suggestion")
Rel(suggestionComposer, auditLogger, "Persist result metadata")
Rel(auditLogger, db, "Write interaction metadata")
Rel(contextResolver, db, "Read metadata and document content")
Rel(requestHandler, eventPublisher, "Publish job status")
Rel(eventPublisher, sync, "Push status to collaborators")
```

![Component Diagram](https://www.plantuml.com/plantuml/png/TLLFRoEt3xtxK_2NmwyEuAoBja2BdjRhfBifl4qspZReAU1eQ5jTZJGHgIH6qUzUITPCd75y6pp-uHFvo7dFWbv2OqR_qrQPK1DiH5h-TJhr-FHkhMKJgi3abRD2LjufrqnRWpR5dB7KHbVJ-Kzdrmdw-danRP25V8JkvwvfdKqnRSh_7GGRWvi8W6m8LiuOzwJj6eos16XhU6NMdkENWy04nYaqPXjpz2nJWKJfkQGVBMP_NNszlR-xlFrqlxZuUF77-VXqD18jXc0sF_l-PvXTmfLN6sBnADfPM99_r8hW37gkSAvnxR4PfUIeBVanjde29od5Z_01rJUAJ6VNbrtqIJHURsKJy_s6BD6IaBad5E9KyszNSNvUX6e63kirSQhF9wUZvPQ5clkBPnaRqyJ0nU8pN7ltg6lod39TjMHdbnEO6mmrJS1vk3866upHFSdpQbnNYOX1MJdVm3aALiYPtVBBGWl16BNZ1nC_JpDdPxJIn9F4KLiXZogpcknHX8O4QvHNnSQyjQgqv8VOEcEmSgMbKxWXD6UtkY5OHhVzBfNsm1rLInVxA9b6g8pc3N7g4x2W14vZLtrQvrEZNihVVt31rkYtO-m6Stos9wVmpmXUvZjkqxEt7mFwkcl25luFNu8JX0mdLkUkYRM0NyZFDwI-CUp29q0sAol9TPA7-n1Sxj9-BKyFWLW-HRiXdxXUmk-kWWAaj5y21GBbB8U6F4m1spPMo6_OB_yd6brdHVLoKixvMjiCqZEfa6863DHkHMw8dNdC5ChIG0Uz_Tg5or8bGoepANcAZ1yr3xJngiC-ViQIQytYjwd96O1RQbg3Gj2Pyhl8frnKWtHcXOB6hPEra6JOvUnzTWreN4q6c4IqNVE01JsIbKvSVfSh684UIlalaXEq7NHKZpbPacK-JKpCXwrkozBEQco5V57cBqcPtJv3iQKwFOOLIrczX7_6bg48fpiR74imzVNJYUYg3KYyR6x6EFDOzY1qQ9wwNgrIWPGhWcYW2jhKE-E7zCbvrlI4bQ7zkvMZMD3GL3cxCbe9h0mUp013hMNXObmH_om1a93IX3Hz5hAAG7LX-MI9yyJxPmayAUVhNUrQSsIiXnVgtz7eXipkO1_iteMDGA1oaQDtSXrwxL-7ilC5Urdo8w63LIjB1BLJ8Ls9pduaUhWqENWe--En0-NDqPWU1jpX9Vh0U_VV-KYMFCfk3ePIQu-KEzHOfvUtvLBIl1NsMY153U3pflQ3BV6lVFFFxivheNsD34C68obXDuHrxmbeXpEonsPqS5BAzzwbA953p_J3pFxH-VWlxZtPEZJcFm00)

**Explanation**
This container is responsible for turning an AI request into a reviewable suggestion rather than a direct document mutation. AC-08 hides vendor-specific APIs from the rest of the system. The Context Resolver and Suggestion Composer are critical because they connect AI output back to a specific document range, base revision, and later accept/reject/partial-apply flow.

### Feature Decomposition

The system is decomposed into modules that can be developed and tested with limited coupling. The frontend, API, real-time, AI, and persistence layers all depend on shared contracts, but they do not share runtime state directly.

| Module | What it does | Depends on | Interface exposed to other modules |
| --- | --- | --- | --- |
| AC-01 Frontend Editor UI | Renders the editor, manages local document state, displays collaborator presence, shows AI suggestions, and handles offline/reconnect UX | Shared contracts package, AC-03 APIs, AC-02 session token and WebSocket channel | React components, editor commands, API client methods, WebSocket event handlers |
| AC-02 Collaboration / Real-Time Sync Service | Accepts document updates, merges concurrent edits via Yjs CRDT, distributes remote updates, and hosts AC-11 Presence Service | AC-12 (SQLite for Yjs state persistence), session claims from AC-03 | Binary WebSocket protocol using y-protocols: sync messages (type 0) and awareness messages (type 1) |
| AC-11 Presence Service | Tracks who is connected, active cursors, and summarized presence state for crowded documents | AC-02 session room, Yjs awareness protocol | Presence payloads to AC-01; collaborator list and cursor metadata |
| AC-03 Backend API Service | Entry point for document CRUD, versioning, sharing, export, session bootstrap, and AI job creation | AC-04, AC-05, AC-06, AC-09, AC-10, AC-07 | REST/JSON endpoints under `/api/...` |
| AC-04 Document Service | Creates documents, loads metadata, resolves current snapshot pointers, and enforces document lifecycle rules | AC-06, AC-12 | Internal service methods and REST handlers such as `POST /documents`, `GET /documents/{id}` |
| AC-05 Versioning Service | Creates immutable checkpoints, lists version history, and restores previous versions as new current versions | AC-04, AC-06, AC-12 | `GET /documents/{id}/versions`, `POST /documents/{id}/versions/{versionId}/restore` |
| AC-06 Auth & Authorization Service | Verifies identity claims, evaluates workspace role plus document role, and gates AI usage by policy | Identity provider claims, workspace policy tables, share records | `authorize(user, action, resource)` and permission metadata returned to the client |
| AC-07 AI Orchestration Service | Executes AI jobs, builds prompts, selects models, and publishes suggestion results | AC-06 policy data, AC-12, AC-08 | AI job queue interface and status events |
| AC-08 AI Provider Adapter | Normalizes calls to the chosen LLM provider and shields the rest of the system from vendor changes | Third-party LLM API | Provider-independent `generate(prompt, schema, modelProfile)` interface |
| AC-09 Export Service | Produces HTML and plain text exports from the current document content | AC-04, AC-12 | `GET /documents/{id}/export?format=html\|txt` |
| AC-10 Audit / Activity Log Service | Records version restores, sharing changes, AI requests, AI outcomes, and security-relevant events | AC-06, AC-12 | Audit write interface and read APIs for permitted reviewers |
| AC-12 Document Database / Storage | Stores metadata, document content (JSON), Yjs state (binary), access rules, versions, AI logs, and exports | SQLite via aiosqlite with SQLAlchemy async ORM | Persistence contracts used by AC-02, AC-03, and AC-07 |

### AI Integration Design

#### Context and scope

The AI assistant should not always see the full document. The default rule is to send the minimum context necessary for the requested feature.

| AI feature | Context sent to the model | Why this scope is chosen | Long-document handling |
| --- | --- | --- | --- |
| Rewrite | Selected text plus the previous and next paragraph, document title, and style hints | Keeps prompts small while preserving tone and local coherence | If the selection exceeds the token budget, chunk by paragraph and synthesize a final rewrite candidate |
| Summarize | Selected text or the current section; optionally section heading path | Summaries depend on the section, not necessarily the full document | Summarize chunks first, then combine them into a second-stage summary |
| Translate | Selected text plus requested target language and glossary/terminology hints | Translation quality benefits more from term hints than from full-document context | Translate in formatting-preserving chunks if the selection is long |
| Restructure | Section outline plus current section content; full document outline only when small enough | Structural changes need broader context than sentence rewrites | For large documents, first generate an outline from headings and section summaries, then propose section-level restructuring |

This scope policy directly balances cost, relevance, and latency. Full-document prompting is reserved for small documents or outline-only operations because it is the most expensive and slowest option and increases privacy exposure.

#### Suggestion UX

AI output is presented as a reviewable suggestion, never as a silent replacement. The UX has two modes:

* **Inline tracked-change style proposal** for local rewrites, summaries inserted below selection, and translation replacements of a bounded selection.
* **Side-panel proposal** for larger restructures or section-level rewrites where direct inline replacement would be visually disruptive.

Users can:

* accept the full suggestion,
* reject it with no document mutation,
* edit the suggestion text before applying it,
* partially accept it by applying only selected diff blocks or sentences,
* undo an accepted suggestion through normal editor undo and version history.

Each suggestion is tied to a `baseRevisionId` so that the system knows what text the model actually saw.

#### AI during collaboration

The architecture does **not** hard-lock the selected region by default. That would protect consistency but would harm the core collaboration experience. Instead:

1. When a user invokes AI, the selected range is marked locally as `AI pending`, and collaborators can see a lightweight indicator that an AI proposal is being generated.
2. Other collaborators may continue editing the document, including the same region.
3. When the result arrives, the system compares the original `baseRevisionId` and text hash with the latest state.
4. If the region has only changed slightly, the Suggestion Composer rebases the proposal onto the latest revision and shows it as a normal suggestion.
5. If the region has changed substantially, the suggestion is marked `stale` and shown with an explanation such as “The source text changed while the AI was generating. Review before applying.”

This gives all collaborators a predictable experience: work continues, but AI proposals are explicitly treated as proposals against a moving shared state.

#### Prompt design

Prompt logic is **template-based and versioned**, not hardcoded in controller code. Each AI feature has:

* a versioned system prompt,
* task-specific variables such as tone, target language, or structure style,
* response schema instructions so the provider returns structured output where possible,
* guardrails telling the model to preserve facts and avoid unrequested changes.

Prompt templates live in a dedicated prompt catalog package and can also be overridden by a database-backed configuration table for selected workspaces. That means prompt wording can evolve without redeploying the whole application, while prompt versions remain auditable in AI interaction records.

#### Model and cost strategy

The platform uses different model profiles for different AI tasks:

* **Fast/low-cost model** for short rewrite, summarize, and translate requests.
* **Higher-quality model** for restructure and long-context summarization jobs.

Cost is controlled at two levels:

* **Per-user quotas** to prevent one user from exhausting shared capacity.
* **Organization-level budgets and feature policies** so admins can disable expensive features or cap monthly usage.

When a user exceeds the allowed limit, AC-07 returns a quota-specific error and publishes a `quota_exceeded` job state. The editor remains fully usable for manual editing; only new AI requests are blocked until the quota resets or an administrator changes the policy.

### API Design

The API layer uses different interaction styles for different problems:

* **REST/JSON** for stable resource operations such as document CRUD, sharing, versions, export, and policy management.
* **WebSocket** for low-latency collaborative updates and presence because polling would not satisfy NFR-LAT-01.
* **Asynchronous job pattern** for AI because LLM calls are slow, failure-prone, and quota-bound.

#### Document CRUD and versioning

| Method | Path | Purpose | Key request / response fields |
| --- | --- | --- | --- |
| `POST` | `/api/documents` | Create a new document | Request: `title`, `workspaceId`, `initialContent?`; Response: `documentId`, `latestVersionId`, `role`, `content` |
| `GET` | `/api/documents` | List documents visible to the current user | Response: paged list with `documentId`, `title`, `updatedAt`, `role`, `preview` |
| `GET` | `/api/documents/{documentId}` | Load document metadata and current snapshot reference | Response: `documentId`, `title`, `content`, `latestVersionId`, `permissions`, `sharingSummary` |
| `PATCH` | `/api/documents/{documentId}` | Update document metadata or PoC-style non-live content fields | Request: `title?`, `status?`, `content?`; Response: updated document resource |
| `DELETE` | `/api/documents/{documentId}` | Soft-delete or archive a document | Response: `204 No Content` |
| `GET` | `/api/documents/{documentId}/versions` | List immutable checkpoints | Response: array of `versionId`, `createdAt`, `actor`, `reason` |
| `POST` | `/api/documents/{documentId}/versions/{versionId}/restore` | Restore an older version as a new current version | Response: `restoredVersionId`, `latestVersionId`, `restoredFromVersionId` |

Example create contract:

```json
POST /api/documents
{
  "title": "Q2 Launch Plan",
  "workspaceId": "ws_123",
  "initialContent": {
    "type": "doc",
    "content": []
  }
}
```

```json
201 Created
{
  "documentId": "doc_456",
  "title": "Q2 Launch Plan",
  "latestVersionId": "ver_001",
  "role": "owner",
  "contentFormat": "prosemirror-json",
  "content": {
    "type": "doc",
    "content": []
  }
}
```

#### Real-time session management

| Method / channel | Path | Purpose | Key fields |
| --- | --- | --- | --- |
| `WS` | `/ws/documents/{documentId}?token=...` | Join the live editing room with JWT auth | Binary messages using y-protocols: sync (type 0) and awareness (type 1) |

The WebSocket connection authenticates via JWT token in the query parameter. The server verifies the token and checks document access permissions before allowing the connection. The Yjs CRDT protocol handles document synchronization (sync step 1, step 2, and incremental updates) and awareness (cursor positions, user presence). No separate session bootstrap endpoint is needed — the client connects directly with its JWT token.

#### AI assistant invocation

| Method | Path | Purpose | Key request / response fields |
| --- | --- | --- | --- |
| `POST` | `/api/documents/{documentId}/ai-jobs` | Create an AI request against a selection or section | Request: `action`, `scope`, `selectionRange`, `baseRevisionId`, `options`; Response: `jobId`, `status`, `queuedAt`, `quotaRemaining?` |
| `GET` | `/api/ai-jobs/{jobId}` | Fetch current job status when event subscription is unavailable | Response: `status`, `suggestionId?`, `errorCode?`, `message?` |
| `GET` | `/api/ai-jobs/{jobId}/suggestion` | Load the generated suggestion payload | Response: `originalText`, `suggestedText`, `diff`, `baseRevisionId`, `stale` |
| `POST` | `/api/ai-jobs/{jobId}/apply` | Apply all or part of a suggestion | Request: `mode`, `selectedDiffBlocks?`, `targetRevisionId`; Response: `appliedVersionId`, `newRevisionId` |
| `POST` | `/api/ai-jobs/{jobId}/reject` | Explicitly reject a suggestion and persist the outcome | Response: `status: rejected` |

Example AI request:

```json
POST /api/documents/doc_456/ai-jobs
{
  "action": "summarize",
  "scope": "selection",
  "selectionRange": {
    "from": 120,
    "to": 480
  },
  "baseRevisionId": "rev_1042",
  "options": {
    "tone": "professional",
    "targetLanguage": null
  }
}
```

```json
202 Accepted
{
  "jobId": "ai_222",
  "status": "queued",
  "queuedAt": "2026-03-17T10:15:00Z"
}
```

#### User, sharing, and permission management

| Method | Path | Purpose | Key fields |
| --- | --- | --- | --- |
| `GET` | `/api/me` | Load the current user profile and workspace memberships | Response: `userId`, `displayName`, `workspaceRoles`, `featureEntitlements` |
| `POST` | `/api/documents/{documentId}/shares` | Grant user, team, or link-based access | Request: `granteeType`, `granteeIdOrEmail`, `role`, `expiresAt?`, `allowAi?` |
| `PATCH` | `/api/documents/{documentId}/shares/{shareId}` | Modify an existing share rule | Request: `role?`, `expiresAt?`, `allowAi?` |
| `DELETE` | `/api/documents/{documentId}/shares/{shareId}` | Revoke access | Response: `204 No Content` |
| `PATCH` | `/api/workspaces/{workspaceId}/ai-policy` | Change role-based AI feature availability or budgets | Request: `allowedRolesByFeature`, `monthlyBudget`, `perUserQuota` |
| `GET` | `/api/documents/{documentId}/audit` | View audit trail when authorized | Response: array of activity events |

#### Long-running AI operations and error handling

From the client perspective, AI is a job with explicit states: `queued`, `running`, `ready`, `stale`, `failed`, or `quota_exceeded`. The client subscribes to `ai.job.status` events over the existing document session channel; if the WebSocket is unavailable, it falls back to `GET /api/ai-jobs/{jobId}` polling.

This lets the client distinguish:

* **“The AI is slow”**: job remains in `queued` or `running`.
* **“The AI failed”**: job becomes `failed` with `errorCode` such as `AI_PROVIDER_TIMEOUT` or `AI_PROVIDER_UNAVAILABLE`.
* **“You have exceeded your quota”**: request is rejected with HTTP `429` or transitions to `quota_exceeded`.

Other important status codes are:

* `401 Unauthorized` for missing/expired session
* `403 Forbidden` for role or policy restrictions
* `409 Conflict` for stale base revision or apply-on-old-version attempts
* `422 Unprocessable Entity` for invalid selection ranges or malformed requests
* `503 Service Unavailable` when the AI provider is down but the editor itself remains available

### Authentication & Authorization

Authentication is required because the system contains private documents, auditable change history, and quota-controlled AI features. The platform expects several user types:

* workspace members,
* invited external collaborators,
* organization administrators,
* reviewers such as team leads or compliance staff with narrow audit access,
* link-based guests with restricted read or comment permissions.

Document access is controlled by both workspace membership and document-specific sharing rules. The main roles and actions are:

| Role | Read | Edit | Share | Restore versions | Invoke AI | Review AI history |
| --- | --- | --- | --- | --- | --- | --- |
| Owner | Yes | Yes | Yes | Yes | Yes | Yes |
| Editor | Yes | Yes | If granted | If granted | Yes if policy allows | Usually no unless explicitly granted |
| Viewer | Yes | No | No | No | No | No |

Actions beyond basic read/write are explicitly protected:

* sharing and permission changes,
* version restore,
* export,
* AI invocation,
* AI history review.

Privacy considerations for third-party LLM processing are built into the authorization model. A workspace can disable external AI processing entirely, restrict it to specific roles, or allow only certain features. Even when AI is allowed, the Context Resolver sends the minimum required text rather than the full document by default.

### Communication Model

The system uses a **push-based real-time communication model** for editing and presence, plus a resource API for stable state transitions.

**Why this choice**

* Push-based synchronization gives the best user experience for collaborative editing and is the only realistic way to satisfy the keystroke propagation targets in NFR-LAT-01.
* Polling would simplify the backend but would make simultaneous editing feel laggy and would create more conflict windows.
* The trade-off is greater implementation complexity, especially around reconnection, ordering, and stale suggestions.

**When a user first opens a shared document**

1. AC-01 calls `GET /api/documents/{id}` to load metadata, current permissions, and the latest content.
2. The client connects to AC-02 over WebSocket at `/ws/documents/{id}?token=JWT`, authenticating via the JWT token.
3. The server sends a Yjs sync step 1 message; the client responds with its state, and the server sends any missing updates.
4. AC-11 Presence Service (via Yjs awareness protocol) broadcasts the current participant list and cursor state.
5. The editor becomes fully interactive once local Yjs state and server state are synchronized.

**When connectivity is lost and returns**

* The client keeps the local editing buffer and marks the document as offline or reconnecting.
* Local edits remain in the local CRDT state and are not discarded.
* On reconnect, the client re-authenticates if needed, rejoins the room, exchanges missing updates, and reconciles local operations.
* If the document has moved too far ahead or the token is invalid, the UI requests a safe reload while preserving the unsynced local draft until the user confirms.

## 2.3 Code Structure & Repository Organization

### Monorepo vs. multi-repo

This project should use a **monorepo**.

That choice is justified by the team size and by the amount of shared logic across frontend, backend, real-time, and AI services:

* frontend and backend share document contracts, permission enums, and validation schemas;
* the AI service shares prompt templates, model profiles, and event payload types;
* the PoC in Part 4 needs fast end-to-end iteration without cross-repository release coordination;
* a semester project benefits more from simple refactoring and shared CI than from independent repo autonomy.

A multi-repo setup would make sense for a much larger organization with separate deployment teams, but for this assignment it would add friction without enough benefit.

### Proposed repository tree

```text
softassignment1/
├── backend/                      Python FastAPI backend
│   ├── app/
│   │   ├── main.py               FastAPI app factory with lifespan, CORS, rate limiting
│   │   ├── config.py             Pydantic Settings (env-based config)
│   │   ├── database.py           Async SQLAlchemy engine + session factory
│   │   ├── models/               SQLAlchemy ORM models (11 tables)
│   │   │   ├── user.py
│   │   │   ├── workspace.py      Workspace, WorkspaceMember, Team, TeamMember
│   │   │   ├── document.py
│   │   │   ├── document_share.py
│   │   │   ├── document_version.py
│   │   │   ├── ai_interaction.py
│   │   │   ├── ai_suggestion.py
│   │   │   └── audit_event.py
│   │   ├── schemas/              Pydantic request/response schemas
│   │   ├── api/                  FastAPI routers
│   │   │   ├── deps.py           Dependency injection (DB session, JWT auth)
│   │   │   ├── users.py          Register, login, profile
│   │   │   ├── documents.py      CRUD + export
│   │   │   ├── shares.py         Share management
│   │   │   ├── versions.py       Version list + restore
│   │   │   ├── ai_jobs.py        AI job lifecycle
│   │   │   ├── audit.py          Audit trail
│   │   │   ├── workspaces.py     AI policy management
│   │   │   └── health.py         Health check
│   │   ├── services/
│   │   │   ├── permissions.py    Role-based access control
│   │   │   └── ai/               AI service layer
│   │   │       ├── ai_service.py         Orchestration
│   │   │       ├── providers/            Abstract base + OpenAI, Claude, Ollama
│   │   │       └── prompts/templates.py  Versioned prompt templates
│   │   ├── realtime/
│   │   │   └── websocket.py      Yjs CRDT sync over WebSocket
│   │   └── tests/                Pytest async tests (9 modules)
│   ├── alembic/                  Database migrations
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                     React + Vite + TypeScript
│   ├── src/
│   │   ├── pages/                LoginPage, DocumentListPage, EditorPage
│   │   ├── components/           AIPanel, ShareModal, VersionPanel, PresenceBar
│   │   ├── api/client.ts         Axios wrapper with JWT interceptor
│   │   ├── lib/collaboration.ts  Yjs WebSocket provider + awareness
│   │   ├── types/index.ts        TypeScript interfaces
│   │   ├── App.tsx               Router setup
│   │   └── main.tsx              Entry point
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml            Backend + Frontend services
├── .env.example
├── CLAUDE.md
└── README.md
```

### Directory layout and shared code rationale

| Path | Purpose |
| --- | --- |
| `backend/app/api/` | FastAPI routers for documents, versions, shares, AI jobs, audit, workspaces, users, and health |
| `backend/app/models/` | SQLAlchemy ORM models for all 11 database tables |
| `backend/app/schemas/` | Pydantic request/response schemas enforcing API contracts |
| `backend/app/services/ai/` | AI orchestration: abstract provider interface, OpenAI/Claude/Ollama implementations, versioned prompt templates |
| `backend/app/services/permissions.py` | Role-based access control with role hierarchy (viewer < editor < admin) and share expiry |
| `backend/app/realtime/` | Yjs CRDT synchronization and awareness over FastAPI WebSocket |
| `backend/app/tests/` | Pytest async tests using in-memory SQLite for auth, CRUD, versions, shares, AI, audit, export, realtime |
| `backend/alembic/` | Alembic database migrations |
| `frontend/src/pages/` | Page components: LoginPage, DocumentListPage, EditorPage |
| `frontend/src/components/` | UI components: AIPanel, ShareModal, VersionPanel, PresenceBar, Toast |
| `frontend/src/lib/` | Collaboration client (Yjs WebSocket provider with reconnect logic) |
| `frontend/src/api/` | Axios HTTP client with JWT interceptor |
| `frontend/src/types/` | TypeScript interfaces mirroring backend Pydantic schemas |

### Configuration management

Secrets such as API keys, database URLs, session secrets, and LLM credentials do **not** live in source control. The repository includes:

* `.env.example` with placeholder names and default values,
* strongly validated runtime configuration via `pydantic-settings` in `backend/app/config.py`,
* environment variables loaded from `.env` file at startup and validated by Pydantic.

Configuration includes: `DATABASE_URL`, `SECRET_KEY`, `AI_DEFAULT_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and optional `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` with their base URLs.

### Testing structure

All backend tests live in `backend/app/tests/` and run with `pytest` + `pytest-asyncio` against an in-memory SQLite database:

* **test_health.py** — health check endpoint
* **test_auth.py** — registration, login, duplicate email rejection, wrong password, unauthenticated access
* **test_documents.py** — document CRUD lifecycle, not-found handling, unauthorized access
* **test_versions.py** — version listing and restore
* **test_shares.py** — share creation, listing, updating, deletion, and permission checks
* **test_ai.py** — AI job lifecycle (create, fetch suggestion, apply, reject), empty text validation
* **test_audit.py** — audit trail retrieval and event recording
* **test_export.py** — HTML and plain text export
* **test_realtime.py** — WebSocket connection, message flow, state persistence

AI tests mock the provider via `unittest.mock.patch` to avoid calling real LLM APIs. The default test strategy uses deterministic mock responses rather than real provider calls.

## 2.4 Data Model

### Entity-relationship diagram

```mermaid
erDiagram
    USER {
        uuid user_id PK
        string email
        string display_name
        string hashed_password
        string auth_subject
        datetime created_at
    }

    WORKSPACE {
        uuid workspace_id PK
        string name
        json ai_policy_json
        datetime created_at
    }

    WORKSPACE_MEMBER {
        uuid workspace_member_id PK
        uuid workspace_id FK
        uuid user_id FK
        string workspace_role
        datetime joined_at
    }

    TEAM {
        uuid team_id PK
        uuid workspace_id FK
        string name
    }

    TEAM_MEMBER {
        uuid team_member_id PK
        uuid team_id FK
        uuid user_id FK
    }

    DOCUMENT {
        uuid document_id PK
        uuid workspace_id FK
        uuid created_by FK
        string title
        json content
        string content_format
        string current_revision_id
        binary yjs_state
        string status
        datetime created_at
        datetime updated_at
    }

    DOCUMENT_SHARE {
        uuid share_id PK
        uuid document_id FK
        string grantee_type
        string grantee_ref
        string role
        boolean allow_ai
        string link_token_hash
        datetime expires_at
        uuid created_by FK
        datetime created_at
    }

    DOCUMENT_VERSION {
        uuid version_id PK
        uuid document_id FK
        json snapshot
        string base_revision_id
        string reason
        uuid created_by FK
        uuid restored_from_version_id
        datetime created_at
    }

    AI_INTERACTION {
        uuid interaction_id PK
        uuid document_id FK
        uuid requested_by FK
        string action_type
        string scope_type
        int selection_from
        int selection_to
        string base_revision_id
        string prompt_template_version
        string model_profile
        string status
        datetime created_at
        datetime completed_at
    }

    AI_SUGGESTION {
        uuid suggestion_id PK
        uuid interaction_id FK
        text original_text
        text suggested_text
        string disposition
        boolean stale
        json diff_json
        json accepted_segments_json
        string applied_revision_id
        uuid applied_by FK
        datetime applied_at
    }

    AUDIT_EVENT {
        uuid audit_event_id PK
        uuid workspace_id FK
        uuid document_id FK
        uuid actor_user_id FK
        string event_type
        string target_ref
        json metadata_json
        datetime created_at
    }

    WORKSPACE ||--o{ WORKSPACE_MEMBER : contains
    USER ||--o{ WORKSPACE_MEMBER : joins
    WORKSPACE ||--o{ TEAM : contains
    TEAM ||--o{ TEAM_MEMBER : has
    USER ||--o{ TEAM_MEMBER : belongs_to
    WORKSPACE ||--o{ DOCUMENT : owns
    USER ||--o{ DOCUMENT : creates
    DOCUMENT ||--o{ DOCUMENT_SHARE : grants
    DOCUMENT ||--o{ DOCUMENT_VERSION : records
    DOCUMENT ||--o{ AI_INTERACTION : receives
    AI_INTERACTION ||--|| AI_SUGGESTION : produces
    USER ||--o{ AI_INTERACTION : initiates
    USER ||--o{ AI_SUGGESTION : applies
    DOCUMENT ||--o{ AUDIT_EVENT : generates
    USER ||--o{ AUDIT_EVENT : performs
    WORKSPACE ||--o{ AUDIT_EVENT : scopes
```

### How a document is represented in storage

The current document state is represented by:

* metadata in the `DOCUMENT` table,
* a `content` JSON column storing the ProseMirror document structure,
* a `yjs_state` binary column storing the Yjs CRDT state for real-time synchronization,
* a `current_revision_id` used by the AI system to detect stale operations.

For the PoC, both content and CRDT state are stored directly in the database rather than in external object storage. This simplifies deployment (no S3 dependency) while keeping the schema extensible for future extraction.

Beyond raw content, a document stores:

* title,
* workspace ownership,
* creator,
* content format,
* status such as active or archived,
* current revision reference,
* creation and update timestamps.

### Versioning, history visibility, and restore

Version history is modeled through `DOCUMENT_VERSION` as immutable checkpoints. A new checkpoint is created:

* when a user explicitly restores a version,
* when a major AI suggestion is applied,
* on explicit export or save milestones,
* periodically after a threshold such as every 100 operations or after an idle window.

Users with the right permission can list versions and restore one. Restore does **not** delete later history. Instead, the restored snapshot becomes a new current version with `restored_from_version_id` referencing the source checkpoint. That preserves auditability and matches US-03.

### AI interaction history and suggestion tracking

AI activity is split into two related entities:

* `AI_INTERACTION` records the request, who initiated it, the feature used, the source range, template version, model profile, and status.
* `AI_SUGGESTION` records the generated proposal, structured diff, stale flag, disposition, and whether all or part of the suggestion was applied.

Partial acceptance is tracked through `accepted_segments_json`, which stores the subset of diff blocks the user accepted. This lets the system distinguish:

* accepted in full,
* rejected,
* partially applied,
* generated but never applied,
* stale because the source region changed too much before review.

### Permissions and sharing model

Permissions are modeled through `DOCUMENT_SHARE` plus workspace membership:

* `grantee_type = USER` supports direct user sharing by email address.
* The `link_token_hash` field is reserved for future link-based sharing but is not yet implemented.
* Team-based sharing (`grantee_type = TEAM`) is modeled in the schema but not yet exposed in the API.

Each share rule stores the granted role (`viewer` or `editor`) and whether AI invocation is allowed for that share (`allow_ai` flag). The document creator has implicit owner access. Access checks also verify share expiry (`expires_at`) when set.

## 2.5 Architecture Decision Records (ADRs)

### ADR-01: Use a dedicated CRDT-based real-time synchronization service

**Status:** Accepted

**Context:**  
The platform must support simultaneous editing, overlapping edits, offline recovery, and fast keystroke propagation. A normal REST save endpoint is not sufficient for FR-COL-01, FR-COL-03, FR-COL-04, or NFR-LAT-01.

**Decision:**  
Use a dedicated real-time synchronization service based on a CRDT-capable editor state and WebSocket transport. Clients keep local-first document state and synchronize deltas through AC-02 instead of treating the backend API as the primary write path for every keystroke.

**Consequences:**  
Positive: better convergence for concurrent edits, strong reconnect story, and low-latency propagation.  
Negative: more operational complexity, binary snapshot persistence, and more difficult debugging than simple CRUD updates.

**Alternatives considered:**  
Operational transform in the main API service was considered, but it would put collaboration and REST concerns into the same scaling unit. Polling plus whole-document save was rejected because it would fail the latency and offline requirements.

### ADR-02: Isolate AI into an asynchronous orchestration service

**Status:** Accepted

**Context:**  
LLM requests are slow, quota-limited, occasionally unavailable, and involve external processing. Core editing must remain available during AI slowdown or provider outages.

**Decision:**  
Run AI requests through AC-07 as asynchronous jobs. The backend API creates a job and returns immediately. AC-07 resolves context, applies policy and quota checks, calls the provider through AC-08, stores the result, and publishes status events back to the document session.

**Consequences:**  
Positive: AI failures do not break editing, retries and rate limiting are easier, and provider changes are localized.  
Negative: the client must handle more states such as queued, running, stale, and quota exceeded.

**Alternatives considered:**  
Direct synchronous LLM calls inside AC-03 were rejected because they would couple API latency and availability to the provider. Direct client-to-provider calls were rejected because they would leak credentials, weaken policy enforcement, and reduce auditability.

### ADR-03: Treat AI output as reviewable suggestion objects tied to base revisions

**Status:** Accepted

**Context:**  
Users need to trust the editor, partially accept suggestions, undo changes, and collaborate while AI is generating. Silent replacement would violate FR-AI-02, FR-AI-03, US-07, and US-08.

**Decision:**  
Store AI outputs as structured suggestion objects that reference the original selection and `baseRevisionId`. Suggestions must be explicitly accepted, rejected, or partially applied. If the source region changes significantly before review, the suggestion is marked stale instead of being auto-applied.

**Consequences:**  
Positive: better user control, stronger audit trail, safer collaboration, and simpler version reasoning.  
Negative: extra UI complexity, additional persistence, and a more complex apply flow than “replace text immediately.”

**Alternatives considered:**  
Immediate AI overwrite was rejected as too risky. A loose side panel with no persisted suggestion object was rejected because it would make auditability, partial acceptance, and collaboration conflict handling much weaker.

### ADR-04: Use a monorepo with Python backend and TypeScript frontend

**Status:** Accepted

**Context:**  
The same project needs a web app, API, real-time service, AI integration, and a working PoC. The team is small and benefits from fast refactoring and one CI pipeline more than from strict repository separation.

**Decision:**  
Keep the backend (Python/FastAPI) and frontend (React/TypeScript) in one monorepo. The backend uses Pydantic schemas as the source of truth for API contracts; the frontend mirrors these with TypeScript interfaces. AI orchestration is merged into the backend as a service layer rather than a separate worker, simplifying deployment for the PoC.

**Consequences:**  
Positive: simpler cross-cutting changes, fewer schema mismatches, faster onboarding, single Docker Compose for the full stack, and easier alignment between Part 2 architecture and Part 4 code.  
Negative: two languages in one repo (Python + TypeScript), API contracts must be kept in sync manually between Pydantic schemas and TypeScript interfaces.

**Alternatives considered:**  
Separate frontend and backend repositories were considered, but they would create avoidable coordination overhead for a semester project. A TypeScript-only stack (NestJS) was considered but rejected in favor of Python/FastAPI for its stronger async ecosystem, simpler AI provider integration via httpx, and the team's existing Python experience.
