import json
import sqlite3
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from freeze_protect.domain.models import AuditEvent, ForecastSnapshot, SafetySettings
from freeze_protect.domain.weather import WeatherSettings
from freeze_protect.persistence.sqlite import (
    SQLiteEventStore,
    SQLiteForecastStore,
    SQLiteSettingsStore,
)
from freeze_protect.persistence.weather import (
    SQLiteWeatherStore,
    WeatherRevisionConflict,
    WeatherStateError,
)


def test_new_database_disabled_and_cas(tmp_path):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    original = store.load()
    assert original.settings == WeatherSettings()
    assert not original.user_off and not original.fault_inhibited
    saved = store.compare_and_swap(0, replace(original, user_off=True))
    assert saved.control_revision == 1 and saved.settings.revision == 0
    assert SQLiteWeatherStore(path).load() == saved
    with pytest.raises(WeatherRevisionConflict):
        store.compare_and_swap(0, original)
    edited = store.compare_and_swap(
        1, replace(saved, settings=replace(saved.settings, enabled=True))
    )
    assert edited.control_revision == 2 and edited.settings.revision == 1
    assert store.load() == edited


def test_migration_preserves_v110_data(tmp_path):
    path = tmp_path / "state.db"
    settings = SQLiteSettingsStore(path)
    settings.save(SafetySettings(settings_version=1))
    now = datetime.now(UTC)
    forecast = ForecastSnapshot(
        tuple(now.date() + timedelta(days=i) for i in range(7)),
        (6.0,) * 7,
        None,
        now,
        46.0,
        14.0,
    )
    SQLiteForecastStore(path).save(forecast)
    event = AuditEvent("existing", now, "test", {"existing": True})
    SQLiteEventStore(path).append(event)
    with sqlite3.connect(path) as db:
        before = [
            db.execute("SELECT * FROM " + table).fetchall()
            for table in (
                "settings",
                "forecast_cache",
                "audit_events",
                "runtime_metadata",
            )
        ]
    assert not SQLiteWeatherStore(path).load().settings.enabled
    with sqlite3.connect(path) as db:
        after = [
            db.execute("SELECT * FROM " + table).fetchall()
            for table in (
                "settings",
                "forecast_cache",
                "audit_events",
                "runtime_metadata",
            )
        ]
    assert before == after
    assert SQLiteForecastStore(path).load() == forecast


@pytest.mark.parametrize("marker", ["manual", "auto"])
def test_unclean_recovery_inhibits_and_preserves_marker(tmp_path, marker):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    active = store.compare_and_swap(0, replace(store.load(), active_marker=marker))
    reopened = SQLiteWeatherStore(path)
    assert reopened.load() == active
    recovered = reopened.recover_interrupted()
    assert recovered.user_off and not recovered.fault_inhibited
    assert recovered.active_marker == marker and recovered.control_revision == 2
    assert SQLiteWeatherStore(path).load() == recovered


@pytest.mark.parametrize(
    "payload",
    [None, "{", "{}", '{"settings":true}', '{"user_off":false,"user_off":true}'],
)
def test_missing_or_corrupt_established_record_faults(tmp_path, payload):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    with sqlite3.connect(path) as db:
        if payload is None:
            db.execute("DELETE FROM weather_control")
        else:
            db.execute("UPDATE weather_control SET payload_json=?", (payload,))
    with pytest.raises(WeatherStateError):
        store.load()
    with pytest.raises(WeatherStateError):
        SQLiteWeatherStore(path)


def test_strict_record_decoding(tmp_path):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    payload = asdict(store.load())
    for key, value in [
        ("control_revision", True),
        ("active_marker", "supply"),
        ("user_off", 1),
    ]:
        malformed = dict(payload, **{key: value})
        with sqlite3.connect(path) as db:
            db.execute(
                "UPDATE weather_control SET payload_json=?", (json.dumps(malformed),)
            )
        with pytest.raises(WeatherStateError):
            store.load()


def test_failed_write_rolls_back(tmp_path):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    saved = store.compare_and_swap(0, replace(store.load(), active_marker="auto"))
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TRIGGER fail_write BEFORE UPDATE ON weather_control "
            "BEGIN SELECT RAISE(ABORT,'injected write failure'); END"
        )
    with pytest.raises(WeatherStateError):
        store.compare_and_swap(1, replace(saved, active_marker=None))
    assert SQLiteWeatherStore(path).load() == saved


def test_recovery_preserves_fault_and_advances_idle_revision(tmp_path):
    store = SQLiteWeatherStore(tmp_path / "state.db")
    idle = store.recover_interrupted()
    assert idle.control_revision == 1
    assert not idle.user_off and not idle.fault_inhibited
    active = store.compare_and_swap(
        1, replace(idle, active_marker="manual", fault_inhibited=True)
    )
    recovered = store.recover_interrupted()
    assert recovered.settings.revision == active.settings.revision
    assert recovered.fault_inhibited and recovered.user_off


@pytest.mark.parametrize(
    "mutation",
    [
        "DELETE FROM weather_metadata",
        "UPDATE weather_metadata SET version='2'",
        "DROP TABLE weather_control",
    ],
)
def test_missing_schema_marker_or_table_faults(tmp_path, mutation):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    with sqlite3.connect(path) as db:
        db.execute(mutation)
    with pytest.raises(WeatherStateError):
        store.load()
    with pytest.raises(WeatherStateError):
        SQLiteWeatherStore(path)


def test_settings_revision_cannot_be_forged(tmp_path):
    store = SQLiteWeatherStore(tmp_path / "state.db")
    record = store.load()
    with pytest.raises(WeatherRevisionConflict):
        store.compare_and_swap(
            0, replace(record, settings=replace(record.settings, revision=1))
        )
    assert store.load() == record


def test_two_independent_stores_cannot_overwrite_stale_control(tmp_path):
    path = tmp_path / "state.db"
    first, second = SQLiteWeatherStore(path), SQLiteWeatherStore(path)
    old = second.load()
    saved = first.compare_and_swap(0, replace(old, user_off=True))
    with pytest.raises(WeatherRevisionConflict):
        second.compare_and_swap(0, replace(old, active_marker="auto"))
    assert second.load() == saved


def test_concurrent_cas_has_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    path = tmp_path / "state.db"
    record = SQLiteWeatherStore(path).load()
    gate = Barrier(2)

    def update(marker):
        store = SQLiteWeatherStore(path)
        gate.wait(timeout=5)
        try:
            return store.compare_and_swap(0, replace(record, active_marker=marker))
        except WeatherRevisionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, ["manual", "auto"]))
    assert sum(result is not None for result in results) == 1
    assert SQLiteWeatherStore(path).load() in results


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": 1},
        {"latitude": True, "longitude": 14.0},
        {"latitude": float("nan"), "longitude": 14.0},
        {"revision": True},
        {"timezone": "invalid"},
        {"extra": "unknown"},
    ],
)
def test_corrupt_nested_settings_faults(tmp_path, change):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    payload = asdict(store.load())
    payload["settings"].update(change)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE weather_control SET payload_json=?", (json.dumps(payload),))
    with pytest.raises(WeatherStateError):
        store.load()
