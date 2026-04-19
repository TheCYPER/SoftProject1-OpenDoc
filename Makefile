# Makefile — one-command workflow for the Collaborative Document Editor.
#
# Local dev:   make install && make migrate && make dev
# Docker:      make docker
# CI checks:   make ci
#
# All targets are phony; Make is just an entrypoint dispatcher, not a build graph.

.PHONY: help install install-backend install-frontend ensure-backend ensure-frontend migrate backend frontend dev test test-cov frontend-test frontend-build ci docker docker-down clean

PYTHON      ?= python3
BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV        := $(BACKEND_DIR)/.venv
PYBIN       := $(VENV)/bin/python
PIP         := $(PYBIN) -m pip
PYTEST      := .venv/bin/python -m pytest
UVICORN     := $(PYBIN) -m uvicorn
ALEMBIC     := $(PYBIN) -m alembic

help:
	@echo "Collaborative Document Editor — make targets"
	@echo ""
	@echo "  make install        install backend venv + frontend node_modules"
	@echo "  make migrate        initialize the dev database schema"
	@echo "  make backend        start the backend only (foreground)"
	@echo "  make frontend       start the frontend only (foreground)"
	@echo "  make dev            start backend + frontend together (Ctrl-C stops both)"
	@echo "  make test           run backend pytest suite"
	@echo "  make test-cov       run backend tests with coverage summary"
	@echo "  make frontend-test  run frontend vitest suite"
	@echo "  make frontend-build build the frontend production bundle"
	@echo "  make ci             run the local CI check set"
	@echo "  make docker         docker-compose up --build"
	@echo "  make docker-down    docker-compose down"
	@echo "  make clean          remove local caches, coverage, and SQLite files"

install: install-backend install-frontend

install-backend:
	@if [ ! -x "$(PYBIN)" ]; then \
		echo ">> creating backend venv"; \
		$(PYTHON) -m venv $(VENV); \
	fi
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

install-frontend:
	@if [ -f "$(FRONTEND_DIR)/package-lock.json" ]; then \
		cd $(FRONTEND_DIR) && npm ci; \
	else \
		cd $(FRONTEND_DIR) && npm install; \
	fi

ensure-backend:
	@if [ ! -x "$(PYBIN)" ]; then \
		echo ">> backend dependencies are missing; run 'make install-backend'"; \
		exit 1; \
	fi

ensure-frontend:
	@if [ ! -d "$(FRONTEND_DIR)/node_modules" ]; then \
		echo ">> frontend dependencies are missing; run 'make install-frontend'"; \
		exit 1; \
	fi

migrate: ensure-backend
	@if [ -d "$(BACKEND_DIR)/alembic/versions" ] && find "$(BACKEND_DIR)/alembic/versions" -maxdepth 1 -type f ! -name '.*' -print -quit | grep -q .; then \
		echo ">> applying alembic migrations"; \
		PYTHONPATH="$(BACKEND_DIR)" $(ALEMBIC) -c $(BACKEND_DIR)/alembic.ini upgrade head; \
	else \
		echo ">> no alembic revisions found; initializing schema from metadata"; \
		PYTHONPATH="$(BACKEND_DIR)" $(PYBIN) -c 'import asyncio; from app.database import init_db; asyncio.run(init_db())'; \
	fi

backend: ensure-backend
	PYTHONPATH="$(BACKEND_DIR)" $(UVICORN) app.main:app --reload --port 8000

frontend: ensure-frontend
	cd $(FRONTEND_DIR) && npm run dev -- --host

# `make dev` runs both; a SIGINT/SIGTERM trap kills both children.
dev: ensure-backend ensure-frontend
	@echo ">> starting backend (port 8000) + frontend (port 5173)"
	@set -m; \
	( PYTHONPATH="$(BACKEND_DIR)" $(UVICORN) app.main:app --reload --port 8000 ) & \
	BE_PID=$$!; \
	( cd $(FRONTEND_DIR) && npm run dev -- --host ) & \
	FE_PID=$$!; \
	trap 'kill $$BE_PID $$FE_PID 2>/dev/null; wait' INT TERM; \
	wait

test: ensure-backend
	cd $(BACKEND_DIR) && $(PYTEST) app/tests/ -v

test-cov: ensure-backend
	cd $(BACKEND_DIR) && $(PYTEST) app/tests/ --cov=app --cov-report=term-missing

frontend-test: ensure-frontend
	cd $(FRONTEND_DIR) && npm run test

frontend-build: ensure-frontend
	cd $(FRONTEND_DIR) && npm run build

ci: migrate test-cov frontend-test frontend-build

docker:
	docker-compose up --build

docker-down:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND_DIR)/.pytest_cache $(BACKEND_DIR)/.coverage $(BACKEND_DIR)/htmlcov
	rm -f collab_editor.db $(BACKEND_DIR)/collab_editor.db $(BACKEND_DIR)/test.db $(BACKEND_DIR)/tmp_duplicate_test.db
	rm -rf $(FRONTEND_DIR)/coverage $(FRONTEND_DIR)/dist
