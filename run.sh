#!/usr/bin/env bash
# run.sh — thin wrapper around `make dev` so a fresh clone has an obvious
# single-command start. The Makefile is the canonical entry point.
set -euo pipefail

cd "$(dirname "$0")"
exec make dev
