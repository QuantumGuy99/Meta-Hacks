# Crucible dev commands (PLAN §16 S-0). Run from the repo root.
# Backend: uv (Python 3.12). Frontend: pnpm (the version pinned in frontend/package.json).

PNPM ?= $(shell command -v pnpm >/dev/null 2>&1 && echo pnpm || echo "npx --yes pnpm@12.15.0")
UV   := uv --directory backend
NODE_TESTS := frontend/src/lib/**/*.test.mjs

.PHONY: install dev dev-backend dev-frontend mock check lint format test test-backend test-node typecheck contracts contracts-check validate evals clean

install:            ## uv sync + pnpm install
	$(UV) sync
	$(PNPM) --dir frontend install

dev:                ## backend on :8000 and frontend on :3000 (Ctrl-C stops both)
	@trap 'kill 0' INT TERM; \
	$(MAKE) --no-print-directory dev-backend & \
	$(MAKE) --no-print-directory dev-frontend & \
	wait

dev-backend:
	$(UV) run uvicorn crucible.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend:
	$(PNPM) --dir frontend dev

mock:               ## frontend development without API keys (never for the demo)
	MOCK=1 $(MAKE) dev

check: lint test typecheck contracts-check   ## everything CI runs

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(PNPM) --dir frontend lint

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

test: test-backend test-node

test-backend:
	$(UV) run pytest -q

test-node:          ## capture/replay tests (Node >= 22, no extra dependency)
	@if ls $(NODE_TESTS) >/dev/null 2>&1; then \
		node --experimental-strip-types --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --test "$(NODE_TESTS)"; \
	else echo "no Node tests yet"; fi

typecheck:          ## next typegen first: Next 16 generates the route types tsc needs
	$(PNPM) --dir frontend exec next typegen
	$(PNPM) --dir frontend exec tsc --noEmit

contracts:          ## regenerate frontend/src/types/contracts.ts from the Pydantic contracts
	$(UV) run python -m crucible.contracts.export

contracts-check:    ## fail if contracts.ts is out of date (skipped until S-1 lands)
	@if [ -f backend/crucible/contracts/export.py ]; then $(UV) run python -m crucible.contracts.export --check; \
	else echo "contracts not merged yet (S-1): skipping drift check"; fi

validate:           ## validate every problem and sample app in data/ (DATA-2)
	@echo "validate lands with DATA-2 (crucible.datatools)"; exit 1

evals:              ## scripted sessions through the real models; costs credits
	@echo "evals land with DATA-5"; exit 1

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/.ruff_cache
