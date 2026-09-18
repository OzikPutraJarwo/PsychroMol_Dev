from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from ..units import kpa_from
from .models import DEFAULT_POLL_INTERVAL_SECONDS, Base

logger = logging.getLogger(__name__)

V2_FOLDED_TABLES = ("decisions", "v2_rules", "v2_readings", "v2_profiles", "growth_stages", "crops", "facilities")
STAGE_FROM_V2 = {"vegetative": "vegetative", "flowering": "flowering", "fruit development": "flowering"}
FALLBACK_STAGE = "vegetative"
MISSING_REFERENCE = "No documented reference was recorded before the upgrade. Enter the source of this band."
V2_PLACEHOLDER_REFERENCES = ("Migrated from this crop's earlier single set of targets", "PROVISIONAL")
V2_SOURCE_FIELDS = {"field_time": "/timestamp", "field_temperature": "/temperature", "field_humidity": "/humidity"}
SEA_LEVEL_PRESSURE_PA = 101325.0
PRESSURE_TOLERANCE_PA = 0.5


class MigrationError(RuntimeError):
    pass


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def schema_version(connection: sqlite3.Connection) -> int | None:
    tables = _tables(connection)
    if "profiles" not in tables:
        return None
    columns = _columns(connection, "profiles")
    if "crop_name" in columns:
        return 3
    if {"crop_id", "stage_id", "facility_id"} <= columns and {"growth_stages", "crops", "facilities"} <= tables:
        return 2
    raise MigrationError(
        "this database was made by a version of PsychroMol older than 2 and cannot be upgraded automatically"
    )


def database_path(engine: Engine) -> Path | None:
    if engine.url.get_backend_name() != "sqlite":
        return None
    database = engine.url.database
    if not database or database == ":memory:":
        return None
    return Path(database)


def backup(path: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.stem}.backup-{stamp}-{label}{path.suffix}")
    source = sqlite3.connect(path)
    try:
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    return target


def _create_v3_tables(connection: sqlite3.Connection, engine: Engine) -> None:
    for table in Base.metadata.sorted_tables:
        connection.execute(str(CreateTable(table).compile(engine)))
        for index in table.indexes:
            connection.execute(str(CreateIndex(index).compile(engine)))


def _stage(connection: sqlite3.Connection, crop_id: int, stage_id: int | None) -> tuple:
    columns = "name, temperature_min, temperature_max, humidity_min, humidity_max, reference"
    row = None
    if stage_id is not None:
        row = connection.execute(f"SELECT {columns} FROM growth_stages WHERE id = ?", (stage_id,)).fetchone()
    if row is None:
        row = connection.execute(
            f"SELECT {columns} FROM growth_stages WHERE crop_id = ? ORDER BY position, id LIMIT 1", (crop_id,)
        ).fetchone()
    if row is None:
        raise MigrationError(f"crop {crop_id} has no growth stage to take temperature and humidity bands from")
    return row


def _reference(text: str | None) -> str:
    if not text or not text.strip() or text.strip().startswith(V2_PLACEHOLDER_REFERENCES):
        return MISSING_REFERENCE
    return text.strip()


def _pressure(connection: sqlite3.Connection, profile_id: int) -> tuple[str, float | None]:
    row = connection.execute(
        "SELECT pressure FROM v2_readings WHERE profile_id = ? ORDER BY measured_at DESC LIMIT 1", (profile_id,)
    ).fetchone()
    if row is None or row[0] is None or abs(row[0] - SEA_LEVEL_PRESSURE_PA) <= PRESSURE_TOLERANCE_PA:
        return "standard", None
    return "fixed", kpa_from(row[0], "Pa")


def _migrate_v2(connection: sqlite3.Connection, engine: Engine) -> dict[str, int]:
    for table in ("profiles", "readings", "rules"):
        connection.execute(f'ALTER TABLE "{table}" RENAME TO "v2_{table}"')
    _create_v3_tables(connection, engine)

    profiles = connection.execute(
        "SELECT p.id, p.name, c.name, p.crop_id, p.stage_id, p.source_url, p.poll_interval_seconds,"
        " p.last_polled_at, p.last_poll_error, p.created_at"
        " FROM v2_profiles p JOIN crops c ON c.id = p.crop_id ORDER BY p.id"
    ).fetchall()
    for (profile_id, name, crop_name, crop_id, stage_id, source_url, interval, polled, error, created) in profiles:
        stage_name, t_min, t_max, rh_min, rh_max, reference = _stage(connection, crop_id, stage_id)
        mode, pressure_kpa = _pressure(connection, profile_id)
        fields = V2_SOURCE_FIELDS if source_url else dict.fromkeys(V2_SOURCE_FIELDS)
        connection.execute(
            "INSERT INTO profiles (id, name, crop_name, stage, temperature_min, temperature_max,"
            " temperature_reference, humidity_min, humidity_max, humidity_reference, vpd_min, vpd_max,"
            " vpd_reference, pressure_mode, pressure_kpa, source_url, poll_interval_seconds, field_time,"
            " field_temperature, field_humidity, field_pressure, pressure_unit, rules_seeded,"
            " last_polled_at, last_poll_error, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, 'kPa', 0, ?, ?, ?)",
            (
                profile_id, name, crop_name,
                STAGE_FROM_V2.get((stage_name or "").strip().lower(), FALLBACK_STAGE),
                t_min, t_max, _reference(reference),
                rh_min, rh_max, _reference(reference),
                mode, pressure_kpa, source_url, interval or DEFAULT_POLL_INTERVAL_SECONDS,
                fields["field_time"], fields["field_temperature"], fields["field_humidity"],
                polled, error, created or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
            ),
        )

    copied = connection.execute(
        "INSERT INTO readings (id, profile_id, measured_at, received_at, temperature_c,"
        " relative_humidity_percent, pressure_kpa)"
        " SELECT id, profile_id, measured_at, COALESCE(received_at, measured_at), temperature,"
        " relative_humidity, NULL FROM v2_readings"
        " WHERE temperature IS NOT NULL AND relative_humidity IS NOT NULL"
        " AND profile_id IN (SELECT id FROM profiles)"
    ).rowcount
    skipped = connection.execute("SELECT COUNT(*) FROM v2_readings").fetchone()[0] - copied

    for table in V2_FOLDED_TABLES:
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    return {"profiles": len(profiles), "readings": copied, "skipped_readings": skipped}


def upgrade(engine: Engine) -> Path | None:
    path = database_path(engine)
    if path is None or not path.exists():
        return None
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        if schema_version(connection) != 2:
            return None
        saved = backup(path, "v2")
        logger.info("upgrading the database to version 3; the previous file is saved as %s", saved)
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            counts = _migrate_v2(connection, engine)
            problems = connection.execute("PRAGMA foreign_key_check").fetchall()
            if problems:
                raise MigrationError(f"foreign key problems after the upgrade: {problems[:5]}")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        connection.execute("PRAGMA foreign_keys = ON")
        logger.info(
            "database upgraded: %(profiles)s profiles, %(readings)s readings kept, "
            "%(skipped_readings)s readings without temperature or humidity left out",
            counts,
        )
        return saved
    finally:
        connection.close()
