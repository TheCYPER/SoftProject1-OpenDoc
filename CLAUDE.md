# Collaborative Document Editor - Project Guide

## Project Overview
Real-time collaborative document editor with AI writing assistant (Google Docs-like).
University assignment PoC — Part 4 implementation based on Part 1 (requirements) and Part 2 (architecture).

## Tech Stack
- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Alembic, SQLite (aiosqlite)
- **Frontend**: React + TypeScript, Vite, react-router-dom
- **AI**: Multi-provider (OpenAI, Claude, Ollama) with abstract provider interface
- **Realtime**: FastAPI WebSocket (simple message relay, no CRDT yet)
- **Infra**: Docker Compose (postgres, backend, ollama, frontend)

## Project Structure
```
backend/           Python FastAPI backend
  app/
    main.py        FastAPI app factory
    config.py      Pydantic Settings (env-based config)
    database.py    Async SQLAlchemy engine + session
    models/        SQLAlchemy ORM models (11 tables from Part 2 ER diagram)
    schemas/       Pydantic request/response schemas
    api/           FastAPI routers (documents, versions, shares, ai_jobs, users, health)
    api/deps.py    Dependency injection (DB session, JWT auth)
    services/ai/   AI service layer
      providers/   Abstract base + OpenAI, Claude, Ollama implementations
      prompts/     Versioned prompt templates
    realtime/      WebSocket stub for collaboration
    tests/         Pytest async tests with SQLite
  alembic/         Database migrations
frontend/          React + Vite + TypeScript
```

## Key Commands
```bash
# Backend tests (from backend/)
pip install -r requirements.txt
pytest app/tests/ -v

# Run backend locally
uvicorn app.main:app --reload

# Docker
docker-compose up --build

# Alembic migrations
cd backend && alembic revision --autogenerate -m "description"
cd backend && alembic upgrade head
```

## Architecture Decisions
- AI worker merged into backend for PoC simplicity (can extract later)
- Document content stored as JSONB in DB (no object storage for PoC)
- JWT auth (stateless, simple)
- WebSocket is simple relay (no CRDT) — to be expanded
- AI provider abstraction: same interface for all providers, user can bring own API key

## API Contracts
Follow Part 2.md Section 2.2 API design tables exactly.
All endpoints prefixed with `/api/`.

## Testing
- Tests use SQLite (aiosqlite) to avoid PostgreSQL dependency
- AI tests mock the provider via `unittest.mock.patch`
- Run: `pytest app/tests/ -v` from `backend/`

## Data Model
See Part 2.md Section 2.4 for the full ER diagram.
11 tables: users, workspaces, workspace_members, teams, team_members,
documents, document_shares, document_versions, ai_interactions, ai_suggestions, audit_events.
