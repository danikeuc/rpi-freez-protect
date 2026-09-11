from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from freeze_protect.domain.models import AuditEvent, SafetySettings
from freeze_protect.persistence.sqlite import (
    SettingsVersionConflict,
    SQLiteEventStore,
    SQLiteSettingsStore,
)


def event(event_type: str, occurred_at: datetime) -> AuditEvent:
    return AuditEvent(
        id=f"event-{event_type}",
        occurred_at=occurred_at,
        event_type=event_type,
        payload={"source": "test"},
    )


def test_settings_survive_a_new_store_instance(tmp_path: Path) -> None:
    database = tmp_path / "freeze-protect.db"
    first = SQLiteSettingsStore(database)
    saved = first.save(SafetySettings(protection_threshold_c=1.5, settings_version=2))

    second = SQLiteSettingsStore(database)

    assert second.load() == saved


def test_default_settings_are_available_without_a_database_row(tmp_path: Path) -> None:
    settings = SQLiteSettingsStore(tmp_path / "freeze-protect.db").load()

    assert settings == SafetySettings()


def test_settings_require_the_next_version_after_a_saved_value(tmp_path: Path) -> None:
    store = SQLiteSettingsStore(tmp_path / "freeze-protect.db")
    store.save(SafetySettings(settings_version=2))

    with pytest.raises(SettingsVersionConflict):
        store.save(SafetySettings(settings_version=2))


def test_audit_events_are_append_only_in_time_order(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "freeze-protect.db")
    now = datetime.now(UTC)
    store.append(event("automatic_decision", now))
    store.append(event("manual_command", now + timedelta(seconds=1)))

    events = store.list(limit=10, offset=0)

    assert [item.event_type for item in events] == [
        "manual_command",
        "automatic_decision",
    ]


def test_event_pagination_arguments_are_bounded(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "freeze-protect.db")

    with pytest.raises(ValueError, match="limit"):
        store.list(limit=0, offset=0)
    with pytest.raises(ValueError, match="offset"):
        store.list(limit=1, offset=-1)
