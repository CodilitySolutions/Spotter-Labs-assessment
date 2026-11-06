.PHONY: up down build rebuild logs test lint format check

up:            ## Start the whole stack
	docker compose up

down:          ## Stop and remove containers
	docker compose down

build:         ## Build images
	docker compose build

rebuild:       ## Rebuild after dependency changes (refreshes node_modules volume)
	docker compose up --build --renew-anon-volumes

logs:
	docker compose logs -f

test:          ## Backend (pytest) and frontend (vitest) tests
	docker compose run --rm --no-deps backend pytest
	docker compose run --rm --no-deps frontend npm test

lint:          ## Lint + type-check both apps
	docker compose run --rm --no-deps backend ruff check .
	docker compose run --rm --no-deps backend ruff format --check .
	docker compose run --rm --no-deps frontend npm run lint
	docker compose run --rm --no-deps frontend npm run typecheck
	docker compose run --rm --no-deps frontend npm run format:check

format:        ## Auto-format both apps
	docker compose run --rm --no-deps backend ruff format .
	docker compose run --rm --no-deps backend ruff check --fix .
	docker compose run --rm --no-deps frontend npm run format

check: lint test
