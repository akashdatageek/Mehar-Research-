.PHONY: up down test lint fmt

COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

up:
	$(COMPOSE) up -d --wait
	uv run rlg db health

down:
	$(COMPOSE) down

test:
	uv run pytest

lint:
	uv run ruff check src tests migrations
	uv run ruff format --check src tests migrations
	uv run mypy

fmt:
	uv run ruff check --fix src tests migrations
	uv run ruff format src tests migrations
