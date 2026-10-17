#!/usr/bin/env bash
# Idempotent dev setup: deps, local dirs, Docker services, migrations.
# Safe to run any number of times.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found; install it: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv python install 3.12 >/dev/null
uv sync --python 3.12

mkdir -p data/blobs data/gold/dev data/gold/heldout data/backups

if [ ! -f .env ]; then
  echo "note: .env missing; copy .env.example to .env and fill in keys"
fi

# Docker services (docker-compose.yml lands in P0-02).
if [ -f docker-compose.yml ]; then
  if docker info >/dev/null 2>&1; then
    make up
  else
    echo "warning: docker not available; skipping service start" >&2
  fi
fi

# Migrations (Alembic lands in P0-02).
if [ -f alembic.ini ]; then
  if docker info >/dev/null 2>&1; then
    uv run alembic upgrade head
  else
    echo "warning: docker not available; skipping migrations" >&2
  fi
fi

echo "init.sh: ok"
