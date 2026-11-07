.PHONY: db api-install migrate seed api web mobile test tokens
db:            ## start PostgreSQL
	docker compose up -d db
api-install:   ## create venv and install the API
	cd apps/api && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
migrate:       ## apply database migrations
	cd apps/api && cp -n .env.example .env; .venv/bin/alembic upgrade head
seed:          ## load the sample dataset
	cd apps/api && .venv/bin/python -m app.seed
api:           ## run the API on :8000
	cd apps/api && .venv/bin/uvicorn app.main:app --reload
web:           ## run the web app on :5173
	cd apps/web && npm install && npm run dev
mobile:        ## run the Expo app
	cd apps/mobile && npm install && npm start
tokens:        ## regenerate design tokens for web and mobile
	node packages/tokens/sync.mjs
test:          ## run all tests and type checks
	cd apps/api && .venv/bin/pytest -q && .venv/bin/ruff check .
	cd apps/web && npm test && npm run build
	cd apps/mobile && npm run typecheck
