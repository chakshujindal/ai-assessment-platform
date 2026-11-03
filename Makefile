# Run `make help` for a summary. Backend uses uv; frontend uses npm.
UV ?= uv
DEMO_ENV := LLM_PROVIDER=fake DATABASE_URL=sqlite:///./data/demo.db SNAPSHOT_DIR=./data/demo-snapshots

.PHONY: help install lint test build run demo clean

help:
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install: ## Install backend (.venv via uv) and frontend (node_modules) dependencies
	cd backend && $(UV) sync
	cd frontend && npm ci

lint: ## ruff + format check (backend), tsc + prettier check (frontend)
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check .
	cd frontend && npm run typecheck && npm run format:check

test: ## pytest with coverage gate (backend), vitest (frontend)
	cd backend && $(UV) run pytest
	cd frontend && npm test

build: ## Production build of the React app into frontend/dist
	cd frontend && npm run build

run: ## API with auto-reload on :8000; pair with `cd frontend && npm run dev` (:5173)
	cd backend && $(UV) run uvicorn --factory app.main:create_app --reload --port 8000

demo: build ## Fresh demo data + FakeLLM (no API key); app on http://localhost:8000
	cd backend && rm -rf data/demo.db data/demo-snapshots && $(DEMO_ENV) $(UV) run python -m app.seed
	cd backend && $(DEMO_ENV) $(UV) run uvicorn --factory app.main:create_app --port 8000

clean: ## Remove local databases, snapshots, build output and caches
	rm -rf backend/data frontend/dist backend/.pytest_cache backend/.ruff_cache backend/.coverage
