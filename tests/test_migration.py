from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine

from psychromol.db.migrate import MISSING_REFERENCE, MigrationError, schema_version
from psychromol.db.session import create_all

V2_SCHEMA = """
CREATE TABLE crops (id INTEGER NOT NULL, name VARCHAR(120) NOT NULL, created_at DATETIME NOT NULL, PRIMARY KEY (id));
CREATE TABLE facilities (id INTEGER NOT NULL, name VARCHAR(120) NOT NULL, altitude_m FLOAT NOT NULL,
    equipment JSON NOT NULL, created_at DATETIME NOT NULL, PRIMARY KEY (id));
CREATE TABLE growth_stages (id INTEGER NOT NULL, crop_id INTEGER NOT NULL, name VARCHAR(120) NOT NULL,
    position INTEGER NOT NULL, temperature_min FLOAT NOT NULL, temperature_max FLOAT NOT NULL,
    humidity_min FLOAT NOT NULL, humidity_max FLOAT NOT NULL, vpd_min FLOAT NOT NULL, vpd_max FLOAT NOT NULL,
    substrate_moisture_min FLOAT, substrate_moisture_max FLOAT, par_min FLOAT, par_max FLOAT, co2_min FLOAT,
    co2_max FLOAT, dew_point_margin FLOAT NOT NULL, condensation_humidity FLOAT NOT NULL,
    evaporative_cooling_humidity FLOAT NOT NULL, ventilation_high FLOAT NOT NULL, reference TEXT,
    created_at DATETIME NOT NULL, PRIMARY KEY (id),
    FOREIGN KEY(crop_id) REFERENCES crops (id) ON DELETE CASCADE);
CREATE TABLE profiles (id INTEGER NOT NULL, name VARCHAR(120) NOT NULL, crop_id INTEGER NOT NULL,
    facility_id INTEGER NOT NULL, source_url TEXT, source_note TEXT, last_polled_at DATETIME,
    last_poll_error TEXT, is_default BOOLEAN NOT NULL, created_at DATETIME NOT NULL,
    poll_interval_seconds INTEGER, stage_id INTEGER REFERENCES growth_stages(id), PRIMARY KEY (id),
    FOREIGN KEY(crop_id) REFERENCES crops (id), FOREIGN KEY(facility_id) REFERENCES facilities (id));
CREATE TABLE readings (id INTEGER NOT NULL, profile_id INTEGER NOT NULL, measured_at DATETIME NOT NULL,
    received_at DATETIME NOT NULL, temperature FLOAT, relative_humidity FLOAT, pressure FLOAT NOT NULL,
    saturation_vapour_pressure FLOAT, vapour_pressure FLOAT, humidity_ratio FLOAT, dew_point FLOAT,
    wet_bulb FLOAT, enthalpy FLOAT, specific_volume FLOAT, density FLOAT, vpd FLOAT, absolute_humidity FLOAT,
    degree_of_saturation FLOAT, dew_point_depression FLOAT, mollier_ordinate FLOAT, engine_version VARCHAR(20),
    error TEXT, surface_temperature FLOAT, outdoor_temperature FLOAT, outdoor_relative_humidity FLOAT,
    substrate_moisture FLOAT, par FLOAT, co2 FLOAT, ventilation FLOAT, PRIMARY KEY (id),
    CONSTRAINT uq_reading UNIQUE (profile_id, measured_at),
    FOREIGN KEY(profile_id) REFERENCES profiles (id) ON DELETE CASCADE);
CREATE TABLE decisions (id INTEGER NOT NULL, reading_id INTEGER NOT NULL, profile_id INTEGER NOT NULL,
    measured_at DATETIME NOT NULL, evaluated_at DATETIME NOT NULL, crop_name VARCHAR(120), stage_name VARCHAR(120),
    status VARCHAR(20) NOT NULL, environmental_state VARCHAR(80) NOT NULL, temperature_state VARCHAR(20) NOT NULL,
    humidity_state VARCHAR(20) NOT NULL, vpd_state VARCHAR(20) NOT NULL, condensation_risk VARCHAR(20) NOT NULL,
    rule_name VARCHAR(120), recommendation TEXT, explanation JSON NOT NULL, PRIMARY KEY (id), UNIQUE (reading_id),
    FOREIGN KEY(reading_id) REFERENCES readings (id) ON DELETE CASCADE,
    FOREIGN KEY(profile_id) REFERENCES profiles (id) ON DELETE CASCADE);
CREATE TABLE rules (id INTEGER NOT NULL, name VARCHAR(120) NOT NULL, conditions JSON NOT NULL,
    severity VARCHAR(20) NOT NULL, recommendation TEXT NOT NULL, requires_equipment VARCHAR(40),
    priority INTEGER NOT NULL, enabled BOOLEAN NOT NULL, created_at DATETIME NOT NULL,
    crop_id INTEGER REFERENCES crops(id) ON DELETE CASCADE,
    stage_id INTEGER REFERENCES growth_stages(id) ON DELETE CASCADE, PRIMARY KEY (id));
CREATE INDEX ix_readings_profile_id ON readings (profile_id);
CREATE INDEX ix_readings_measured_at ON readings (measured_at);
CREATE INDEX ix_growth_stages_crop_id ON growth_stages (crop_id);
CREATE INDEX ix_decisions_measured_at ON decisions (measured_at);
CREATE INDEX ix_decisions_profile_id ON decisions (profile_id);
CREATE TABLE greenhouses (id INTEGER NOT NULL, name VARCHAR(120) NOT NULL, PRIMARY KEY (id));
"""

NOW = "2026-09-17 09:48:55.000000"


def stage(stage_id, crop_id, name, bands, reference):
    return (stage_id, crop_id, name, 0, *bands, 0.5, 1.2, None, None, None, None, None, None, 2.0, 85.0, 85.0, 80.0, reference, NOW)


@pytest.fixture
def v2_path(tmp_path):
    path = tmp_path / "psychromol.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(V2_SCHEMA)
        connection.executemany("INSERT INTO crops VALUES (?, ?, ?)", [(1, "Tomato", NOW), (2, "Lettuce", NOW)])
        connection.executemany(
            "INSERT INTO facilities VALUES (?, ?, ?, '[]', ?)", [(1, "House 1", 30.0, NOW), (2, "GH", 0.0, NOW)]
        )
        connection.executemany(
            "INSERT INTO growth_stages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                stage(1, 1, "General", (18.0, 28.0, 60.0, 80.0), "  Own greenhouse records, 2025  "),
                stage(2, 1, "Fruit development", (18.0, 27.0, 60.0, 80.0), "PROVISIONAL placeholder values, not yet taken from a documented source."),
                stage(3, 2, "Vegetative", (12.0, 22.0, 55.0, 75.0), None),
            ],
        )
        connection.executemany(
            "INSERT INTO profiles VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)",
            [
                (1, "Tomato · House 1", 1, 1, "https://example.test/live.json", NOW, None, 1, NOW, None, 1),
                (2, "Lettuce", 2, 2, None, None, "old error", 0, NOW, 5, None),
                (3, "Tomato fruiting", 1, 2, None, None, None, 0, NOW, None, 2),
            ],
        )
        readings = [
            (1, 1, "2026-09-17 09:47:55.000000", NOW, 24.0, 70.0, 100965.12276026042),
            (2, 1, "2026-09-17 09:48:55.000000", NOW, 24.5, 69.0, 100965.12276026042),
            (3, 1, "2026-09-17 09:49:55.000000", NOW, None, 69.0, 100965.12276026042),
            (4, 2, "2026-09-17 09:48:55.000000", NOW, 18.0, 65.0, 101325.0),
        ]
        connection.executemany(
            "INSERT INTO readings (id, profile_id, measured_at, received_at, temperature, relative_humidity,"
            " pressure, vpd) VALUES (?, ?, ?, ?, ?, ?, ?, 1.0)",
            readings,
        )
        connection.execute(
            "INSERT INTO decisions VALUES (1, 2, 1, ?, ?, 'Tomato', 'General', 'ok', 'OPTIMAL', 'OPTIMAL',"
            " 'OPTIMAL', 'OPTIMAL', 'LOW', 'Fine', 'Nothing.', '{}')",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO rules VALUES (1, 'Condensation risk', '[]', 'critical', 'Heat.', NULL, 1, 1, ?, NULL, NULL)",
            (NOW,),
        )
        connection.execute("INSERT INTO greenhouses VALUES (1, 'Kept as it was')")
        connection.commit()
    finally:
        connection.close()
    return path


def upgraded(path):
    engine = create_engine(f"sqlite:///{path}", future=True)
    create_all(engine)
    engine.dispose()
    return sqlite3.connect(path)


def rows(connection, sql):
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(sql)]


def test_the_upgrade_backs_up_the_v2_file_first(v2_path):
    upgraded(v2_path).close()
    backups = list(v2_path.parent.glob("psychromol.backup-*-v2.db"))
    assert len(backups) == 1
    saved = sqlite3.connect(backups[0])
    try:
        assert schema_version(saved) == 2
        assert saved.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 4
    finally:
        saved.close()


def test_each_profile_takes_its_crop_stage_bands_source_and_pressure(v2_path):
    connection = upgraded(v2_path)
    try:
        profiles = {row["id"]: row for row in rows(connection, "SELECT * FROM profiles")}
    finally:
        connection.close()

    house = profiles[1]
    assert (house["name"], house["crop_name"], house["stage"]) == ("Tomato · House 1", "Tomato", "vegetative")
    assert (house["temperature_min"], house["temperature_max"], house["humidity_min"], house["humidity_max"]) == (18.0, 28.0, 60.0, 80.0)
    assert house["temperature_reference"] == house["humidity_reference"] == "Own greenhouse records, 2025"
    assert (house["vpd_min"], house["vpd_max"], house["vpd_reference"]) == (None, None, None)
    assert house["pressure_mode"] == "fixed"
    assert house["pressure_kpa"] == pytest.approx(100.96512276026042)
    assert house["source_url"] == "https://example.test/live.json"
    assert (house["field_time"], house["field_temperature"], house["field_humidity"]) == ("/timestamp", "/temperature", "/humidity")
    assert house["poll_interval_seconds"] == 60
    assert house["rules_seeded"] == 0
    assert house["last_polled_at"] == NOW

    lettuce = profiles[2]
    assert (lettuce["stage"], lettuce["temperature_min"]) == ("vegetative", 12.0)
    assert lettuce["temperature_reference"] == MISSING_REFERENCE
    assert (lettuce["pressure_mode"], lettuce["pressure_kpa"]) == ("standard", None)
    assert (lettuce["source_url"], lettuce["field_temperature"]) == (None, None)
    assert (lettuce["poll_interval_seconds"], lettuce["last_poll_error"]) == (5, "old error")

    assert profiles[3]["stage"] == "flowering"
    assert profiles[3]["temperature_reference"] == MISSING_REFERENCE
    assert profiles[3]["pressure_mode"] == "standard"


def test_readings_keep_their_measured_values_and_nothing_derived(v2_path):
    connection = upgraded(v2_path)
    try:
        readings = rows(connection, "SELECT * FROM readings ORDER BY id")
    finally:
        connection.close()
    assert [row["id"] for row in readings] == [1, 2, 4]
    assert readings[1] == {
        "id": 2,
        "profile_id": 1,
        "measured_at": "2026-09-17 09:48:55.000000",
        "received_at": NOW,
        "temperature_c": 24.5,
        "relative_humidity_percent": 69.0,
        "pressure_kpa": None,
    }


def test_the_folded_v2_tables_go_and_everything_else_stays(v2_path):
    connection = upgraded(v2_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert tables == {"profiles", "readings", "rules", "greenhouses"}
        assert connection.execute("SELECT name FROM greenhouses").fetchall() == [("Kept as it was",)]
        assert connection.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert schema_version(connection) == 3
    finally:
        connection.close()


def test_the_upgrade_runs_once(v2_path):
    upgraded(v2_path).close()
    upgraded(v2_path).close()
    assert len(list(v2_path.parent.glob("psychromol.backup-*"))) == 1


def test_a_new_database_is_created_without_a_backup(tmp_path):
    connection = upgraded(tmp_path / "fresh.db")
    try:
        assert schema_version(connection) == 3
    finally:
        connection.close()
    assert not list(tmp_path.glob("*.backup-*"))


def test_a_database_older_than_v2_is_refused(tmp_path):
    path = tmp_path / "ancient.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE crops (id INTEGER PRIMARY KEY, name TEXT, temperature_min FLOAT);"
        "CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT, crop_id INTEGER, facility_id INTEGER);"
    )
    connection.close()
    with pytest.raises(MigrationError, match="older than 2"):
        upgraded(path)
