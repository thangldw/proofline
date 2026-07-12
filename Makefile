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
	npm run test:web

eval:
	.venv/bin/proofline eval-extraction --dataset evals/extraction/seed-v1.json \
		--min-precision 1.0 --min-recall 1.0 --min-f1 1.0 \
		--min-evidence-resolution 1.0 --min-expected-evidence-accuracy 1.0 \
		--min-negative-source-accuracy 1.0
	.venv/bin/proofline eval --dataset evals/retrieval/seed-v1.json --min-recall 0.80 --min-ndcg 0.80
	.venv/bin/proofline eval-grounded --dataset evals/grounded-qa/seed-v1.json \
		--min-citation-resolution 1.0 --min-citation-precision 1.0 \
		--min-grounded-success 1.0 --min-status-accuracy 1.0

check:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	npm run build:web
	$(MAKE) eval

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .
