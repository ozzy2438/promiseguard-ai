.PHONY: install test coverage lint format-check typecheck migrate api generate generate-events train evaluate-value demo docker-up docker-down

install:
	python -m pip install -e ".[dev,ml,postgres]"

test:
	pytest

coverage:
	pytest --cov=promiseguard --cov=apps.api --cov-report=term-missing --cov-fail-under=88

lint:
	ruff check .

format-check:
	ruff format --check .

typecheck:
	mypy src/promiseguard

migrate:
	alembic upgrade head

api:
	uvicorn apps.api.main:create_app --factory --reload

generate:
	promiseguard-generate --count 100000 --output data/generated/orders.jsonl

generate-events:
	promiseguard-generate-events --input data/generated/orders.jsonl --output data/generated/events.jsonl

train:
	promiseguard-train --input data/generated/orders.jsonl --output-dir artifacts/models

evaluate-value:
	promiseguard-evaluate-value --input data/generated/orders.jsonl --model-path artifacts/models/risk_model.joblib --output artifacts/evidence/value_evaluation.json

demo:
	python scripts/demo_governed_workflow.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down
