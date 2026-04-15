# Makefile — one-command workflow for the Collaborative Document Editor.
#
# Local dev:   make install && make migrate && make dev
# Docker:      make docker
# Tests:       make test
#
# All targets are phony; Make is just an entrypoint dispatcher, not a build graph.

.PHONY: help install install-backend install-frontend migrate backend frontend dev test test-cov docker docker-down clean

PYTHON      ?= python3
BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV        := $(BACKEND_DIR)/.venv
PIP         := $(VENV)/bin/pip
PYBIN       := $(VENV)/bin/python
UVICORN     := $(VENV)/bin/uvicorn
ALEMBIC     := $(VENV)/bin/alembic

help:
	@echo "Collaborative Document Editor — make targets"
	@echo ""
	@echo "  make install        install backend venv + frontend node_modules"
	@echo "  make migrate        run alembic upgrade head"
	@echo "  make backend        start the backend only (foreground)"
	@echo "  make frontend       start the frontend only (foreground)"
	@echo "  make dev            start backend + frontend together (Ctrl-C stops both)"
	@echo "  make test           run backend pytest suite"
	@echo "  make test-cov       run backend tests with coverage summary"
	@echo "  make docker         docker-compose up --build"
	@echo "  make docker-down    docker-compose down"
	@echo "  make clean          remove caches, .pytest_cache, frontend dist"

install: install-backend install-frontend

install-backend:
	@if [ ! -d "$(VENV)" ]; then \
		echo ">> creating backend venv"; \
		$(PYTHON) -m venv $(VENV); \
	fi
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND_DIR)/requirements.txt

install-frontend:
	cd $(FRONTEND_DIR) && npm install

migrate:
	cd $(BACKEND_DIR) && ../$(VENV)/bin/alembic upgrade head

backend:
	cd $(BACKEND_DIR) && ../$(VENV)/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd $(FRONTEND_DIR) && npm run dev -- --host

# `make dev` runs both; a SIGINT/SIGTERM trap kills both children.
dev:
	@echo ">> starting backend (port 8000) + frontend (port 5173)"
	@set -m; \
	( cd $(BACKEND_DIR) && ../$(VENV)/bin/uvicorn app.main:app --reload --port 8000 ) & \
	BE_PID=$$!; \
	( cd $(FRONTEND_DIR) && npm run dev -- --host ) & \
	FE_PID=$$!; \
	trap 'kill $$BE_PID $$FE_PID 2>/dev/null; wait' INT TERM; \
	wait

test:
	cd $(BACKEND_DIR) && ../$(VENV)/bin/python -m pytest app/tests/ -v

test-cov:
	cd $(BACKEND_DIR) && ../$(VENV)/bin/python -m pytest app/tests/ --cov=app --cov-report=term-missing

docker:
	docker-compose up --build

docker-down:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND_DIR)/.pytest_cache $(BACKEND_DIR)/.coverage
	rm -rf $(FRONTEND_DIR)/dist
