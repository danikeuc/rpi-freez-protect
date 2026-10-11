from datetime import UTC, datetime
from uuid import uuid4

import pytest
from test_m1_service import build_service
from test_weather_service import Rig

from freeze_protect.domain.models import AuditEvent, ControlMode
from freeze_protect.persistence.sqlite import SQLiteEventStore


def history(store):
    return store.shower_history(0)["items"]


def test_manual_transitions_are_durable_and_renewals_deduplicated(tmp_path):
    store = SQLiteEventStore(tmp_path / "history.db")
    service, _driver, _clock = build_service(mode=ControlMode.MANUAL_TIMED)
    service._event_store = store
    service.startup()
    service.run_cycle()
    service.start_timed_shower(60)
    service.run_cycle()
    service.drain()
    service.run_cycle()
    service.shutdown()
    assert [item["operation"] for item in history(store)] == [
        "SHUTDOWN",
        "MANUAL_IDLE",
        "MANUAL_ACTIVE",
        "MANUAL_IDLE",
        "STARTING",
    ]
    assert history(SQLiteEventStore(tmp_path / "history.db")) == history(store)
    assert all(item["occurred_at"].endswith("+00:00") for item in history(store))


def test_weather_auto_manual_stop_and_restart(tmp_path):
    rig = Rig(tmp_path)
    store = SQLiteEventStore(tmp_path / "history.db")
    rig.service._event_store = store
    rig.warm()
    rig.service.run_cycle()
    rig.advance(900)
    rig.service.run_cycle()
    rig.result(error="fetch_failed")
    rig.service.run_cycle()
    rig.service.start_weather_shower(60)
    rig.service.run_cycle()
    rig.advance(60)
    rig.service.run_cycle()
    rig.service.stop_weather_shower()
    rig.service.shutdown()
    assert [row["operation"] for row in history(store)] == [
        "SHUTDOWN",
        "USER_OFF",
        "MANUAL_IDLE",
        "MANUAL_ACTIVE",
        "MANUAL_IDLE",
        "AUTO_SUPPLY",
        "MANUAL_IDLE",
        "STARTING",
    ]
    restarted = rig.new_service()
    restarted._event_store = store
    restarted.startup()
    assert [row["operation"] for row in history(store)][:2] == ["USER_OFF", "STARTING"]


def test_history_failure_preserves_fail_closed_audit_policy(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()

    class BrokenHistory:
        def append(self, event):
            if event.event_type == "shower_transition":
                raise OSError("disk full")

    rig.service._event_store = BrokenHistory()
    decision = rig.service.stop_weather_shower()
    assert decision.reason == "persistence_error"
    assert decision.command.value == "DRAIN"
    assert rig.service.run_cycle().state.value == "FAULT"


def test_history_projection_filters_other_events_paginates_and_uses_insertion_order(
    tmp_path,
):
    store = SQLiteEventStore(tmp_path / "history.db")
    for index in range(13):
        store.append(
            AuditEvent(
                str(uuid4()),
                datetime(2026, 1, 1, tzinfo=UTC),
                "shower_transition",
                {
                    "mode": "manual_timed",
                    "operation": "MANUAL_IDLE",
                    "command": "DRAIN",
                    "reason": "manual_idle",
                    "secret": "never expose",
                    "extra": index,
                },
            )
        )
    store.append(
        AuditEvent(
            str(uuid4()),
            datetime(2026, 1, 1, tzinfo=UTC),
            "fault",
            {"reason": "private diagnostic"},
        )
    )
    page = store.shower_history(0)
    assert len(page["items"]) == 10 and page["has_more"] is True
    assert len(store.shower_history(10)["items"]) == 3
    assert store.shower_history(13) == {"items": [], "offset": 13, "has_more": False}
    assert set(page["items"][0]) == {
        "occurred_at",
        "mode",
        "operation",
        "command",
        "reason",
    }
    assert "secret" not in str(page)
    with pytest.raises(ValueError):
        store.shower_history(-1)


def test_fault_transition_does_not_expose_driver_diagnostic(tmp_path):
    rig = Rig(tmp_path)
    store = SQLiteEventStore(tmp_path / "history.db")
    rig.service._event_store = store
    rig.warm()
    rig.service._fault("relay_driver_error")
    assert history(store)[0]["operation"] == "FAULT"
    assert history(store)[0]["reason"] == "relay_driver_error"


def test_history_read_never_creates_missing_database(tmp_path):
    path = tmp_path / "history.db"
    store = SQLiteEventStore(path)
    path.unlink()
    with pytest.raises(Exception, match="unable to open database"):
        store.shower_history()
    assert not path.exists()


def test_history_order_follows_transition_order_despite_clock_correction(tmp_path):
    store = SQLiteEventStore(tmp_path / "history.db")
    for year, operation in ((2027, "MANUAL_IDLE"), (2026, "MANUAL_ACTIVE")):
        store.append(
            AuditEvent(
                str(uuid4()),
                datetime(year, 1, 1, tzinfo=UTC),
                "shower_transition",
                {
                    "mode": "manual_timed",
                    "operation": operation,
                    "command": "DRAIN" if operation == "MANUAL_IDLE" else "SUPPLY",
                    "reason": "manual_idle",
                },
            )
        )
    assert [row["operation"] for row in history(store)] == [
        "MANUAL_ACTIVE",
        "MANUAL_IDLE",
    ]


def test_history_empty_is_distinct_from_invalid_storage(tmp_path):
    store = SQLiteEventStore(tmp_path / "history.db")
    assert store.shower_history() == {"items": [], "offset": 0, "has_more": False}
    store.append(
        AuditEvent(
            str(uuid4()),
            datetime(2026, 1, 1, tzinfo=UTC),
            "shower_transition",
            {
                "mode": "manual_timed",
                "operation": "MANUAL_IDLE",
                "command": "DRAIN",
                "reason": "private reason is not a code",
            },
        )
    )
    with pytest.raises(ValueError, match="invalid history"):
        store.shower_history()


def test_history_write_failure_after_supply_returns_fault_and_drains(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()

    class BrokenHistory:
        def append(self, event):
            if event.event_type == "shower_transition":
                raise OSError("disk full")

    rig.service._event_store = BrokenHistory()
    rig.result()
    decision = rig.service.run_cycle()
    assert decision.reason == "persistence_error"
    assert decision.command.value == "DRAIN"
    assert rig.driver.commands[-1].value == "DRAIN"
    assert rig.store.load().fault_inhibited is True


def test_weather_operator_drain_preserves_reason_and_records_user_off(tmp_path):
    rig = Rig(tmp_path)
    store = SQLiteEventStore(tmp_path / "history.db")
    rig.service._event_store = store
    rig.warm()
    assert rig.service.drain().reason == "drain_requested"
    assert history(store)[0]["operation"] == "USER_OFF"
    rig.service.run_cycle()
    assert history(store)[0]["reason"] == "drain_requested"
