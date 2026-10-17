.PHONY: up down test lint fmt

COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

up:
	@if [ -f docker-compose.yml ]; then $(COMPOSE) up -d --wait; else echo "no docker-compose.yml yet (added in P0-02)"; fi

down:
	@if [ -f docker-compose.yml ]; then $(COMPOSE) down; else echo "no docker-compose.yml yet (added in P0-02)"; fi

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy

fmt:
	uv run ruff check --fix src tests
	uv run ruff format src tests
