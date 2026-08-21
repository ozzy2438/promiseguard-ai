# Local Docker stack

## Start

```bash
docker compose up --build
```

Services:

- PostgreSQL 16 on host `5433` (container `5432`; development password only);
- FastAPI on host `${PROMISEGUARD_API_PORT:-8000}` after Alembic `upgrade head`;
- Streamlit console on host `${PROMISEGUARD_CONSOLE_PORT:-8501}`.

The API image uses Python 3.12. Compose does not write `OPENAI_API_KEY` into the repository. If
the launching shell exports the key, it is passed through to the API container.

If host ports `8000` or `8501` are already allocated:

```bash
PROMISEGUARD_API_PORT=8001 PROMISEGUARD_CONSOLE_PORT=8501 docker compose up --build
python3.12 scripts/local_e2e.py --api-url http://127.0.0.1:8001 --wait-seconds 120
```

## Prove the integrated stack

```bash
python3.12 scripts/local_e2e.py --wait-seconds 120
```

The probe covers health/readiness, evaluation, approval, governed execution, independent
verification, operator feedback, Prometheus metrics, kill-switch blocking, tenant-filtered
persistence and Streamlit reachability. It does not call OpenAI.

Restart safety:

```bash
docker compose restart api
python3.12 scripts/local_e2e.py --replay --wait-seconds 120
```

`make docker-e2e` runs start, probe, restart, replay and shutdown.

## Shutdown

```bash
docker compose down
```

Data in the named PostgreSQL volume survives `down` unless `-v` is used. Treat that volume as
disposable local evidence, not production data.
