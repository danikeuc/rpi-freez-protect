import json
import sqlite3
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from freeze_protect.domain.models import ForecastSnapshot, SafetySettings
from freeze_protect.persistence.sqlite import SQLiteForecastStore, SQLiteSettingsStore

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)
DATES = tuple(date(2026, 9, 11) + timedelta(days=offset) for offset in range(7))


def snapshot() -> ForecastSnapshot:
    return ForecastSnapshot(
        dates=DATES,
        daily_minima_c=(6.0,) * 7,
        source_generated_at=NOW - timedelta(minutes=5),
        fetched_at=NOW,
        latitude=46.5547,
        longitude=15.6459,
    )


def test_cached_forecast_survives_a_store_reopen(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    SQLiteForecastStore(database).save(snapshot())

    assert SQLiteForecastStore(database).load() == snapshot()


def test_old_m0_settings_row_loads_with_safe_m1_defaults(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    store = SQLiteSettingsStore(database)
    m0_payload = {
        "protection_threshold_c": 1.0,
        "release_threshold_c": 5.0,
        "release_days": 7,
        "sensor_stale_after_s": 900,
        "minimum_protection_dwell_s": 300,
        "settings_version": 1,
    }
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO settings (singleton, version, payload_json, updated_at) VALUES (1, 1, ?, ?)",
            (json.dumps(m0_payload), NOW.isoformat()),
        )

    loaded = store.load()

    assert loaded == SafetySettings(settings_version=1)
    assert loaded.sensor_commissioned is False


def test_legacy_ds18b20_device_id_remains_accepted_and_persisted(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    store = SQLiteSettingsStore(database)
    stored = store.save(
        SafetySettings(sensor_device_id="28-00000legacy", settings_version=1)
    )

    loaded = store.load()

    assert stored.sensor_device_id == "28-00000legacy"
    assert loaded.sensor_device_id == "28-00000legacy"
    assert loaded.sensor_commissioned is False


def test_binding_replacement_sensor_clears_legacy_commissioning_once(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.db"
    store = SQLiteSettingsStore(database)
    store.save(
        SafetySettings(
            sensor_device_id="28-00000legacy",
            sensor_commissioned=True,
            settings_version=1,
        )
    )

    migrated = store.bind_sensor_source("MAX31865_PT100_SPI0_CE0")
    rebound = store.bind_sensor_source("MAX31865_PT100_SPI0_CE0")

    assert migrated.sensor_commissioned is False
    assert migrated.sensor_device_id == "28-00000legacy"
    assert migrated.settings_version == 2
    assert rebound == migrated

    reapproved = store.save(
        replace(
            migrated,
            sensor_commissioned=True,
            settings_version=migrated.settings_version + 1,
        )
    )
    after_restart = SQLiteSettingsStore(database).bind_sensor_source(
        "MAX31865_PT100_SPI0_CE0"
    )

    assert reapproved.sensor_commissioned is True
    assert reapproved.settings_version == 3
    assert after_restart == reapproved


def test_legacy_rollback_reapproval_cannot_transfer_back_to_max31865(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state.db"
    store = SQLiteSettingsStore(database)
    store.save(
        SafetySettings(
            sensor_device_id="28-00000legacy",
            sensor_commissioned=True,
            settings_version=1,
        )
    )
    migrated = store.bind_sensor_source("MAX31865_PT100_SPI0_CE0")
    approved_max31865 = store.save(
        replace(
            migrated,
            sensor_commissioned=True,
            settings_version=migrated.settings_version + 1,
        )
    )

    legacy_reapproved = replace(approved_max31865, settings_version=5)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE settings
            SET version = ?, payload_json = ?, updated_at = ?
            WHERE singleton = 1
            """,
            (
                legacy_reapproved.settings_version,
                json.dumps(asdict(legacy_reapproved), sort_keys=True),
                NOW.isoformat(),
            ),
        )

    rebound = SQLiteSettingsStore(database).bind_sensor_source(
        "MAX31865_PT100_SPI0_CE0"
    )

    assert rebound.sensor_commissioned is False
    assert rebound.settings_version == 6
