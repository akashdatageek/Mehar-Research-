#!/usr/bin/env bash
# Idempotent dev setup: deps, local data dirs, Docker services, migrations.
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

docker_ok() { docker info >/dev/null 2>&1; }

# Cloud containers ship dockerd but do not start it. Start it once if we can.
if command -v docker >/dev/null 2>&1 && ! docker_ok && command -v dockerd >/dev/null 2>&1 \
   && [ "$(id -u)" = "0" ]; then
  echo "starting dockerd"
  nohup dockerd >/tmp/dockerd.log 2>&1 &
  for _ in $(seq 1 30); do docker_ok && break; sleep 1; done
fi

# Docker services (docker-compose.yml lands in P0-02).
if [ -f docker-compose.yml ]; then
  if docker_ok; then
    make up
  else
    echo "error: docker-compose.yml present but Docker is not reachable" >&2
    exit 1
  fi
fi

# Migrations (Alembic lands in P0-02).
if [ -f alembic.ini ]; then
  uv run alembic upgrade head
fi

echo "init.sh: ok"
