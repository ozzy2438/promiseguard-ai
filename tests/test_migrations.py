from __future__ import annotations

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_creates_required_evidence_tables(tmp_path) -> None:
    database_path = tmp_path / "migration.db"
    url = f"sqlite+pysqlite:///{database_path}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)

    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert {
        "operational_events",
        "decisions",
        "approvals",
        "actions",
        "outcomes",
        "runtime_controls",
        "autonomy_profiles",
        "autonomy_evidence",
    }.issubset(tables)
