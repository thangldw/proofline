.PHONY: setup dev dev-api dev-web seed embed test eval benchmark-retrieval simulate-pilot check format release-check

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
	.venv/bin/proofline eval --dataset evals/retrieval/seed-v2.json \
		--min-recall 1.0 --min-ndcg 1.0 --min-expected-empty-accuracy 1.0
	.venv/bin/proofline eval-grounded --dataset evals/grounded-qa/seed-v1.json \
		--min-citation-resolution 1.0 --min-citation-precision 1.0 \
		--min-grounded-success 1.0 --min-status-accuracy 1.0

simulate-pilot:
	@.venv/bin/python scripts/simulate_pilot.py \
		--dataset evals/pilot-simulation/engineering-context-v1.json

benchmark-retrieval:
	.venv/bin/python scripts/benchmark_reranker.py \
		--dataset evals/reranking/seed-v1.json \
		--output evals/benchmarks/reranker-token-overlap-v1.json
	.venv/bin/python scripts/benchmark_vector_index.py \
		--sources 1000 --output evals/benchmarks/vector-index-1000-v1.json

check:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	npm run build:web
	$(MAKE) eval

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .

release-check:
	@test -n "$(TAG)" || (echo "TAG is required, for example TAG=v0.6.0"; exit 2)
	.venv/bin/python scripts/release_check.py --tag "$(TAG)"
