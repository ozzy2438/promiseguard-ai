PYTHON := $(shell command -v python3.12 2>/dev/null || command -v python3)

.PHONY: python-version install test coverage lint format-check typecheck migrate api generate generate-events train evaluate-value demo openai-smoke evals docker-up docker-down docker-e2e

python-version:
	$(PYTHON) -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" || \
		(echo "Python 3.12 is required. Found: $$($(PYTHON) --version 2>/dev/null || echo missing)" && exit 1)
	$(PYTHON) -c "import sys; print(sys.version)"

install: python-version
	$(PYTHON) -m pip install -e ".[dev,ml,postgres,agent]"

test: python-version
	$(PYTHON) -m pytest

coverage: python-version
	$(PYTHON) -m pytest --cov=promiseguard --cov=apps.api --cov-report=term-missing --cov-fail-under=88

lint:
	$(PYTHON) -m ruff check .

format-check:
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy src/promiseguard

migrate:
	$(PYTHON) -m alembic upgrade head

api:
	$(PYTHON) -m uvicorn apps.api.main:create_app --factory --reload

generate:
	promiseguard-generate --count 100000 --output data/generated/orders.jsonl

generate-events:
	promiseguard-generate-events --input data/generated/orders.jsonl --output data/generated/events.jsonl

train:
	promiseguard-train --input data/generated/orders.jsonl --output-dir artifacts/models

evaluate-value:
	promiseguard-evaluate-value --input data/generated/orders.jsonl --model-path artifacts/models/risk_model.joblib --output artifacts/evidence/value_evaluation.json

demo:
	$(PYTHON) scripts/demo_governed_workflow.py

openai-smoke:
	promiseguard-openai-smoke

evals:
	$(PYTHON) evals/run_local.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-e2e:
	docker compose up --build -d
	$(PYTHON) scripts/local_e2e.py --wait-seconds 120
	docker compose restart api
	$(PYTHON) scripts/local_e2e.py --replay --wait-seconds 120
	docker compose down
