.PHONY: setup dev dev-api dev-web seed test check format

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e '.[dev]'
	npm install

dev:
	@echo "Run 'make dev-api' and 'make dev-web' in separate terminals."

dev-api:
	.venv/bin/proofline serve

dev-web:
	npm run dev:web

seed:
	.venv/bin/proofline seed

test:
	.venv/bin/pytest -q

check:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	npm run build:web

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .
