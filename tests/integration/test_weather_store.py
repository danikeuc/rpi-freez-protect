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


@pytest.mark.parametrize(
    "replacement", ["missing", "empty", "other_store", "schema_removed"]
)
def test_established_identity_cannot_be_reset(tmp_path, replacement):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    saved = store.compare_and_swap(
        0, replace(store.load(), active_marker="auto", user_off=True)
    )
    assert saved.user_off and saved.active_marker == "auto"
    if replacement == "schema_removed":
        with sqlite3.connect(path) as db:
            db.execute("DROP TABLE weather_control")
            db.execute("DROP TABLE weather_metadata")
    else:
        path.unlink()
        if replacement == "empty":
            path.touch()
        elif replacement == "other_store":
            other_path = tmp_path / "other.db"
            SQLiteWeatherStore(other_path)
            path.write_bytes(other_path.read_bytes())
    with pytest.raises(WeatherStateError):
        store.load()
    with pytest.raises(WeatherStateError):
        SQLiteWeatherStore(path)
    if replacement == "missing":
        assert not path.exists()


def test_deeply_nested_json_faults_for_load_and_reopen(tmp_path):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE weather_control SET payload_json=?",
            ("[" * 10000 + "0" + "]" * 10000,),
        )
    with pytest.raises(WeatherStateError):
        store.load()
    with pytest.raises(WeatherStateError):
        SQLiteWeatherStore(path)


@pytest.mark.parametrize("sentinel_state", ["missing", "empty", "wrong_identity"])
def test_established_sentinel_loss_or_corruption_faults(tmp_path, sentinel_state):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    sentinel = path.with_name(path.name + ".weather-identity")
    assert sentinel.exists()
    if sentinel_state == "missing":
        sentinel.unlink()
    else:
        sentinel.write_text("" if sentinel_state == "empty" else "0" * 32)
    with pytest.raises(WeatherStateError):
        store.load()
    with pytest.raises(WeatherStateError):
        SQLiteWeatherStore(path)


def test_interrupted_initialization_after_sentinel_creation_faults_closed(
    tmp_path, monkeypatch
):
    import os

    path = tmp_path / "state.db"
    with monkeypatch.context() as patch:

        def fail_sync(descriptor):
            raise OSError("injected durability failure")

        patch.setattr(os, "fsync", fail_sync)
        with pytest.raises(WeatherStateError):
            SQLiteWeatherStore(path)
    assert path.with_name(path.name + ".weather-identity").is_file()
    with pytest.raises(WeatherStateError):
        SQLiteWeatherStore(path)
    with sqlite3.connect(path) as db:
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='weather_control'"
            ).fetchone()
            is None
        )


def test_oversized_persisted_numeric_value_faults(tmp_path):
    path = tmp_path / "state.db"
    store = SQLiteWeatherStore(path)
    payload = asdict(store.load())
    payload["settings"]["latitude"] = 10**400
    payload["settings"]["longitude"] = 14.0
    with sqlite3.connect(path) as db:
        db.execute("UPDATE weather_control SET payload_json=?", (json.dumps(payload),))
    with pytest.raises(WeatherStateError):
        store.load()
    with pytest.raises(WeatherStateError):
        SQLiteWeatherStore(path)


def test_concurrent_first_initialization_has_one_durable_identity(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    path = tmp_path / "state.db"
    gate = Barrier(2)

    def initialize(_):
        gate.wait(timeout=5)
        return SQLiteWeatherStore(path).load()

    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(initialize, range(2)))
    assert records[0] == records[1] == SQLiteWeatherStore(path).load()
