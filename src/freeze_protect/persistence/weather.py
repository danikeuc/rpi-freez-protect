"""Transactional durable weather control state; forecast observations remain local."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

from freeze_protect.domain.weather import WeatherControlRecord, WeatherSettings

_VERSION = "1"


class WeatherRevisionConflict(ValueError):
    """A control or settings revision no longer matches the durable state."""


class WeatherStateError(RuntimeError):
    """Durable weather state is missing, invalid, or unavailable; fail closed."""


class SQLiteWeatherStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        try:
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                table = db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='weather_control'"
                ).fetchone()
                db.execute(
                    "CREATE TABLE IF NOT EXISTS weather_metadata "
                    "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), version TEXT NOT NULL)"
                )
                version = db.execute(
                    "SELECT version FROM weather_metadata WHERE singleton=1"
                ).fetchone()
                if version is None:
                    if table is not None:
                        raise WeatherStateError("weather version marker missing")
                    db.execute(
                        "CREATE TABLE weather_control "
                        "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload_json TEXT NOT NULL)"
                    )
                    db.execute("INSERT INTO weather_metadata VALUES(1,?)", (_VERSION,))
                    db.execute(
                        "INSERT INTO weather_control VALUES(1,?)",
                        (_encode(WeatherControlRecord()),),
                    )
                elif version[0] != _VERSION:
                    raise WeatherStateError("unsupported weather schema version")
                self._read(db)
        except (OSError, sqlite3.Error) as error:
            raise WeatherStateError("weather storage initialization failed") from error

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)

    def _read(self, db: sqlite3.Connection) -> WeatherControlRecord:
        version = db.execute(
            "SELECT version FROM weather_metadata WHERE singleton=1"
        ).fetchone()
        if version is None or version[0] != _VERSION:
            raise WeatherStateError("weather schema version missing or unsupported")
        row = db.execute(
            "SELECT payload_json FROM weather_control WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise WeatherStateError("established weather record missing")
        return _decode(row[0])

    def load(self) -> WeatherControlRecord:
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN")
                return self._read(db)
        except sqlite3.Error as error:
            raise WeatherStateError("weather storage read failed") from error

    def compare_and_swap(
        self, expected_control_revision: int, record: WeatherControlRecord
    ) -> WeatherControlRecord:
        if type(expected_control_revision) is not int or expected_control_revision < 0:
            raise WeatherRevisionConflict("invalid expected control revision")
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                current = self._read(db)
                if (
                    current.control_revision != expected_control_revision
                    or record.control_revision != current.control_revision
                    or record.settings.revision != current.settings.revision
                ):
                    raise WeatherRevisionConflict("weather revision conflict")
                settings_changed = record.settings != current.settings
                saved = replace(
                    record,
                    control_revision=current.control_revision + 1,
                    settings=replace(
                        record.settings,
                        revision=current.settings.revision + int(settings_changed),
                    ),
                )
                db.execute(
                    "UPDATE weather_control SET payload_json=? WHERE singleton=1",
                    (_encode(saved),),
                )
                return saved
        except sqlite3.Error as error:
            raise WeatherStateError("weather storage write failed") from error

    def recover_interrupted(self) -> WeatherControlRecord:
        """Startup only: interrupted supply requires a fresh deliberate START.

        Preserve the active marker until confirmed DRAIN and a subsequent durable
        clear. Existing fault inhibition remains independent of user inhibition.
        Even idle startup advances the control revision, invalidating stale actions.
        """
        record = self.load()
        recovered = replace(
            record, user_off=record.user_off or record.active_marker is not None
        )
        return self.compare_and_swap(record.control_revision, recovered)


def _encode(record: WeatherControlRecord) -> str:
    return json.dumps(asdict(record), sort_keys=True, allow_nan=False)


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _decode(raw: str) -> WeatherControlRecord:
    try:
        value = json.loads(raw, object_pairs_hook=_object)
        record_keys = {
            "settings",
            "user_off",
            "fault_inhibited",
            "active_marker",
            "control_revision",
        }
        settings_keys = {"enabled", "latitude", "longitude", "timezone", "revision"}
        if not isinstance(value, dict) or set(value) != record_keys:
            raise ValueError("invalid record fields")
        settings = value["settings"]
        if not isinstance(settings, dict) or set(settings) != settings_keys:
            raise ValueError("invalid settings fields")
        return WeatherControlRecord(
            settings=WeatherSettings(
                enabled=cast(bool, settings["enabled"]),
                latitude=cast(float | None, settings["latitude"]),
                longitude=cast(float | None, settings["longitude"]),
                timezone=cast(str, settings["timezone"]),
                revision=cast(int, settings["revision"]),
            ),
            user_off=cast(bool, value["user_off"]),
            fault_inhibited=cast(bool, value["fault_inhibited"]),
            active_marker=cast(str | None, value["active_marker"]),
            control_revision=cast(int, value["control_revision"]),
        )
    except (ValueError, TypeError, OverflowError) as error:
        raise WeatherStateError("stored weather record is invalid") from error
