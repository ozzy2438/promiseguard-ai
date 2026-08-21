"""Verify that Alembic created the required PostgreSQL evidence tables."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect

REQUIRED = {
    "operational_events",
    "decisions",
    "approvals",
    "actions",
    "outcomes",
    "runtime_controls",
    "autonomy_profiles",
    "autonomy_evidence",
    "openai_budgets",
    "openai_runs",
    "operator_feedback",
}


def main() -> None:
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    missing = REQUIRED - tables
    if missing:
        raise SystemExit(f"missing tables: {sorted(missing)}")
    print("postgres migration smoke test passed")


if __name__ == "__main__":
    main()
