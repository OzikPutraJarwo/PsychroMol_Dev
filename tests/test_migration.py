from __future__ import annotations

from sqlalchemy import create_engine

from psychromol.db.session import _add_missing_columns


def _columns(engine, table):
    with engine.connect() as connection:
        return {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}

def test_a_pre_existing_profiles_table_gets_the_new_column(tmp_path):
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
    assert "poll_interval_seconds" not in _columns(engine, "profiles")

    _add_missing_columns(engine)

    assert "poll_interval_seconds" in _columns(engine, "profiles")

def test_running_the_migration_twice_is_harmless(tmp_path):
    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
    _add_missing_columns(engine)
    _add_missing_columns(engine)
    assert "poll_interval_seconds" in _columns(engine, "profiles")
