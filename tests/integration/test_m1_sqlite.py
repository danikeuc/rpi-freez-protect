import json
import sqlite3
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
