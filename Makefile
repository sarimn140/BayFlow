# BayFlow developer commands (GNU Make; spec 07). Run `make` or `make help`.
# Windows without GNU Make: use start.bat / stop.bat, WSL2, or `docker compose up --build`.
SHELL := /bin/bash
.DEFAULT_GOAL := help
LOAD_ENV := set -a; [ -f .env ] && . ./.env; set +a;

.PHONY: help setup up down db-up migrate seed db-reset api web agent dev test lint fmt gen-api smoke

help: ## List all targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-9s %s\n", $$1, $$2}'

setup: ## First run: create .env, install API + web dependencies, install git hooks
	@[ -f .env ] || cp .env.example .env
	cd apps/api && uv sync
	cd apps/web && pnpm install
	@if [ -f .pre-commit-config.yaml ] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
	  uvx pre-commit install; \
	else \
	  echo "setup: git hooks skipped (no .pre-commit-config.yaml or not a git repository)"; \
	fi

up: ## Everything in Docker: PostgreSQL, migrate + seed, API :4000, web :3000
	docker compose up --build

down: ## Stop the Docker stack (the database volume is kept)
	docker compose down

db-up: ## Start only PostgreSQL in Docker and wait until it is healthy
	docker compose up -d --wait db

migrate: ## Apply Alembic migrations to DATABASE_URL
	cd apps/api && uv run alembic upgrade head

seed: ## Load the demo data (idempotent; repairs the demo cast)
	cd apps/api && uv run python -m app.scripts.seed --force

db-reset: ## Wipe the LOCAL Docker database, then migrate and seed (refuses production / non-local URLs)
	@app_env="$${APP_ENV:-$$(sed -n 's/^APP_ENV=//p' .env 2>/dev/null | tail -n 1 | tr -d '"')}"; \
	db_url="$${DATABASE_URL:-$$(sed -n 's/^DATABASE_URL=//p' .env 2>/dev/null | tail -n 1 | tr -d '"')}"; \
	if [ "$$app_env" = production ]; then \
	  echo "db-reset refused: APP_ENV=production" >&2; exit 2; fi; \
	case "$$db_url" in \
	  *@localhost:*|*@localhost/*|*@127.0.0.1:*|*@127.0.0.1/*|*@\[::1\]:*|*@\[::1\]/*|*@db:*|*@db/*) ;; \
	  *) echo "db-reset refused: DATABASE_URL is not a local database (localhost, 127.0.0.1, ::1 or db)" >&2; exit 2 ;; \
	esac
	docker compose up -d --wait db
	docker compose exec -T db psql -U bayflow -d bayflow -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	$(MAKE) migrate seed

api: ## API with auto-reload on http://localhost:4000 (Swagger at /docs)
	cd apps/api && uv run uvicorn app.main:app --reload --port 4000

web: ## Web with hot reload on http://localhost:3000 (reads the root .env)
	$(LOAD_ENV) cd apps/web && PORT=3000 pnpm dev

agent: ## AI Front Desk worker (needs CALL_PROVIDER_*, LLM_API_KEY, AGENT_SERVICE_TOKEN in .env)
	cd apps/agent && PYTHONPATH=src uv run python -m bayflow_agent dev

dev: db-up migrate seed ## PostgreSQL in Docker + API and web locally (Ctrl+C stops both)
	$(MAKE) -j2 api web

test: db-up ## API tests (pytest on real PostgreSQL) + web unit tests (vitest)
	cd apps/api && uv run pytest
	cd apps/web && pnpm test

lint: ## Lint, format check, type check, architecture contracts
	cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run lint-imports
	cd apps/web && pnpm lint && pnpm format:check && pnpm typecheck

fmt: ## Auto-fix lint findings and format all code
	cd apps/api && uv run ruff check --fix . && uv run ruff format .
	cd apps/web && pnpm format

gen-api: ## Regenerate openapi.json (API export), then schema.d.ts (web script api:types) - D76
	cd apps/api && uv run python -m app.scripts.export_openapi ../web/src/lib/api/openapi.json
	cd apps/web && pnpm api:types

smoke: ## Post-deploy smoke test: make smoke WEB_URL=https://... API_URL=https://...
	WEB_URL="$(WEB_URL)" API_URL="$(API_URL)" ./scripts/smoke.sh
