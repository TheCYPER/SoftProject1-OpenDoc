#!/usr/bin/env bash
# run.sh — bootstrap a fresh clone, initialize the local DB, then start dev mode.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo ">> created .env from .env.example"
fi

if [ ! -x backend/.venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo ">> installing local dependencies"
  make install
fi

echo ">> initializing database"
make migrate

exec make dev
