.PHONY: setup dev dev-api dev-web seed embed test eval check format

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

embed:
	.venv/bin/proofline embed

test:
	.venv/bin/pytest -q

eval:
	.venv/bin/proofline eval --dataset evals/retrieval/seed-v1.json --min-recall 0.80 --min-ndcg 0.80

check:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	npm run build:web
	$(MAKE) eval

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .
