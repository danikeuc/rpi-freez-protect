"""Durable action admission over real service/storage and fake paired outputs."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from threading import Event
from uuid import uuid4

import pytest
from test_weather_service import Rig

from freeze_protect.application.weather_actions import (
    WeatherActionError,
    WeatherActionGate,
    WeatherActionInput,
)
from freeze_protect.domain.models import ActuatorCommand, ControllerState
from freeze_protect.persistence.weather import WeatherStateError


def build_gate(rig):
    def payload(read_only):
        weather = rig.service.weather_status(expire_timer=not read_only)
        control = rig.service.status(expire_timer=not read_only)
        return {
            "control_revision": weather.record.control_revision,
            "operation": weather.operation,
            "command": control.command.value,
            "remaining_seconds": control.remaining_seconds,
        }

    return WeatherActionGate(rig.service, rig.store, payload, lambda: rig.mono)


def request(gate, *, duration=180):
    status = gate.status()
    return WeatherActionInput(
        str(uuid4()), status["control_revision"], status["action_nonce"], duration
    )


def assert_error(code, callback):
    with pytest.raises(WeatherActionError) as error:
        callback()
    assert error.value.status_code == code


def test_matching_replay_keeps_revision_and_deadline_without_any_actuator_io(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    result = gate.execute("start", action)
    assert result.accepted is True
    deadline = rig.service.status().timed_shower_deadline
    rig.advance(190)
    before = list(rig.driver.commands)
    replay = gate.execute("start", action)
    assert replay.control_revision == result.control_revision
    assert replay.status["remaining_seconds"] == 0
    assert rig.driver.commands == before
    assert rig.service.status(expire_timer=False).timed_shower_deadline == deadline


def test_same_id_different_body_conflicts_without_action(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    gate.execute("start", action)
    before = list(rig.driver.commands)
    assert_error(
        409, lambda: gate.execute("start", replace(action, duration_seconds=240))
    )
    assert rig.driver.commands == before


def test_stale_start_after_stop_and_reboot_cannot_clear_inhibition(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    stale = request(gate)
    gate.execute("stop", request(gate, duration=None))
    assert_error(409, lambda: gate.execute("start", stale))
    restarted = rig.new_service()
    restarted.startup()
    rig.service = restarted
    second_gate = build_gate(rig)
    assert_error(409, lambda: second_gate.execute("start", stale))
    assert rig.store.load().user_off is True
    assert ActuatorCommand.SUPPLY not in rig.driver.commands


def test_same_id_concurrent_start_performs_begin_once(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: gate.execute("start", action), range(2)))
    assert results[0].control_revision == results[1].control_revision
    assert rig.driver.commands.count(ActuatorCommand.SUPPLY) == 1


def test_expired_nonce_and_full_pool_never_disable_unconditional_drain(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    first = request(gate)
    for _ in range(63):
        assert gate.status()["action_nonce"] is not None
    assert gate.status()["action_nonce"] is None
    rig.advance(10)
    assert_error(409, lambda: gate.execute("start", first))
    assert gate.status()["action_nonce"] is not None
    assert rig.service.drain().command is ActuatorCommand.DRAIN
    assert rig.store.load().user_off is True


def test_nonce_is_single_use_even_with_different_request_id(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    first = request(gate)
    gate.execute("start", first)
    current = rig.store.load().control_revision
    forged = replace(first, request_id=str(uuid4()), expected_control_revision=current)
    assert_error(409, lambda: gate.execute("start", forged))
    assert rig.driver.commands.count(ActuatorCommand.SUPPLY) == 1


def test_pending_is_persisted_before_begin_and_reconciled_once_at_startup(
    tmp_path, monkeypatch
):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    original = rig.driver.command

    def crash(command, **kwargs):
        if command is ActuatorCommand.SUPPLY:
            receipt = rig.store.get_action_receipt(action.request_id)
            assert receipt is not None and receipt.state == "pending"
            raise SystemExit("simulated process crash")
        return original(command, **kwargs)

    monkeypatch.setattr(rig.driver, "command", crash)
    with pytest.raises(SystemExit):
        gate.execute("start", action)
    monkeypatch.setattr(rig.driver, "command", original)
    rig.service = rig.new_service()
    rig.service.startup()
    restored = build_gate(rig)
    restored.recover_pending()
    assert rig.service.status().state is ControllerState.FAULT
    before = list(rig.driver.commands)
    assert_error(503, lambda: restored.execute("start", action))
    restored.recover_pending()
    assert rig.driver.commands == before
    assert rig.store.load().fault_inhibited is True


def test_completed_receipt_after_crash_replays_without_reopening(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    accepted = gate.execute("start", action)
    gate.status()  # A later normal status durably promotes the timely result.
    rig.service = rig.new_service()
    rig.service.startup()
    restarted = build_gate(rig)
    restarted.recover_pending()
    before = list(rig.driver.commands)
    replay = restarted.execute("start", action)
    assert replay.control_revision == accepted.control_revision
    assert replay.status["operation"] == "USER_OFF"
    assert rig.driver.commands == before


@pytest.mark.parametrize("method", ["begin_action_receipt", "finish_action_receipt"])
def test_receipt_write_failure_drains_faults_and_cannot_reopen(
    tmp_path, monkeypatch, method
):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)

    def broken(*args, **kwargs):
        raise WeatherStateError("injected receipt failure")

    monkeypatch.setattr(rig.store, method, broken)
    assert_error(503, lambda: gate.execute("start", action))
    assert rig.service.status().state is ControllerState.FAULT
    assert rig.driver.commands[-1] is ActuatorCommand.DRAIN
    assert rig.store.load().fault_inhibited
    assert rig.service.run_cycle().state is ControllerState.FAULT
    assert rig.driver.commands.count(ActuatorCommand.SUPPLY) == (
        method == "finish_action_receipt"
    )


def test_expired_action_response_never_reports_success_and_replay_stays_read_only(
    tmp_path, monkeypatch
):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    original = rig.driver.command

    def late(command, **kwargs):
        result = original(command, **kwargs)
        if command is ActuatorCommand.SUPPLY:
            rig.advance(10)
        return result

    monkeypatch.setattr(rig.driver, "command", late)
    assert_error(503, lambda: gate.execute("start", action))
    before = list(rig.driver.commands)
    assert_error(503, lambda: gate.execute("start", action))
    assert rig.driver.commands == before
    assert rig.service.status().state is ControllerState.FAULT


def test_waiting_start_cannot_use_nonce_that_expired_while_lock_was_held(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    entered = Event()

    def execute():
        entered.set()
        return gate.execute("start", action)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with rig.service.weather_action_guard():
            future = pool.submit(execute)
            assert entered.wait(1)
            rig.advance(10)
        assert_error(409, future.result)
    assert ActuatorCommand.SUPPLY not in rig.driver.commands


def test_receipts_keep_only_latest_128_completed_requests(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    first = request(gate, duration=None)
    gate.execute("stop", first)
    for _ in range(128):
        gate.execute("stop", request(gate, duration=None))
    assert rig.store.get_action_receipt(first.request_id) is None
    with closing(sqlite3.connect(tmp_path / "weather.db")) as db:
        assert (
            db.execute("SELECT count(*) FROM weather_action_receipts").fetchone()[0]
            == 128
        )


def test_final_receipt_write_crossing_deadline_cannot_report_accepted_success(
    tmp_path, monkeypatch
):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    original = rig.store.finish_action_receipt

    def late(*args, **kwargs):
        receipt = original(*args, **kwargs)
        rig.advance(10)
        return receipt

    monkeypatch.setattr(rig.store, "finish_action_receipt", late)
    assert_error(503, lambda: gate.execute("start", action))
    before = list(rig.driver.commands)
    assert_error(503, lambda: gate.execute("start", action))
    assert rig.driver.commands == before
    assert rig.service.status().state is ControllerState.FAULT


def test_retention_never_evicts_pending_intents_or_exceeds_128(tmp_path):
    rig = Rig(tmp_path)
    build_gate(rig)
    pending_ids = []
    for _ in range(127):
        identity = str(uuid4())
        pending_ids.append(identity)
        rig.store.begin_action_receipt(identity, "a" * 64)
    completed_id = str(uuid4())
    rig.store.begin_action_receipt(completed_id, "b" * 64)
    rig.store.finish_action_receipt(completed_id, 0)
    rig.store.begin_action_receipt(str(uuid4()), "c" * 64)
    with closing(sqlite3.connect(tmp_path / "weather.db")) as db:
        assert (
            db.execute("SELECT count(*) FROM weather_action_receipts").fetchone()[0]
            == 128
        )
    assert rig.store.get_action_receipt(completed_id) is None
    assert all(
        rig.store.get_action_receipt(identity).state == "pending"
        for identity in pending_ids
    )
    with pytest.raises(WeatherStateError):
        rig.store.begin_action_receipt(str(uuid4()), "d" * 64)


@pytest.mark.parametrize("rejection_write_fails", [False, True])
def test_intent_commit_expiry_rejects_before_start(
    tmp_path, monkeypatch, rejection_write_fails
):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    original = rig.store.begin_action_receipt

    def late_intent(*args, **kwargs):
        original(*args, **kwargs)
        rig.advance(10)

    def broken_rejection(*args, **kwargs):
        raise WeatherStateError("injected rejection write failure")

    monkeypatch.setattr(rig.store, "begin_action_receipt", late_intent)
    if rejection_write_fails:
        monkeypatch.setattr(rig.store, "finish_action_receipt", broken_rejection)
    assert_error(
        503 if rejection_write_fails else 409, lambda: gate.execute("start", action)
    )
    assert ActuatorCommand.SUPPLY not in rig.driver.commands
    before = list(rig.driver.commands)
    assert_error(
        503 if rejection_write_fails else 409, lambda: gate.execute("start", action)
    )
    assert rig.driver.commands == before
    if rejection_write_fails:
        assert rig.service.status().state is ControllerState.FAULT
    else:
        assert rig.store.get_action_receipt(action.request_id).state == "rejected"


def test_provisional_success_replay_is_read_only_and_crash_recovers_unknown(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    accepted = gate.execute("start", action)
    receipt = rig.store.get_action_receipt(action.request_id)
    assert receipt.state == "pending"
    assert receipt.control_revision == accepted.control_revision
    before = list(rig.driver.commands)
    assert gate.execute("start", action).accepted is True
    assert rig.store.get_action_receipt(action.request_id) == receipt
    assert rig.driver.commands == before
    rig.service = rig.new_service()
    rig.service.startup()
    restarted = build_gate(rig)
    restarted.recover_pending()
    before = list(rig.driver.commands)
    assert_error(503, lambda: restarted.execute("start", action))
    assert rig.driver.commands == before
    recovered = rig.store.get_action_receipt(action.request_id)
    assert recovered.state == "unknown"
    assert recovered.control_revision == accepted.control_revision
    assert rig.service.status().state is ControllerState.FAULT


def test_expired_completion_with_failed_unknown_write_never_replays_success(
    tmp_path, monkeypatch
):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    original = rig.store.finish_action_receipt

    def late_completion(*args, **kwargs):
        receipt = original(*args, **kwargs)
        rig.advance(10)
        return receipt

    def broken_unknown(*args, **kwargs):
        raise WeatherStateError("injected withdrawal failure")

    monkeypatch.setattr(rig.store, "finish_action_receipt", late_completion)
    monkeypatch.setattr(rig.store, "mark_action_unknown", broken_unknown)
    assert_error(503, lambda: gate.execute("start", action))
    receipt = rig.store.get_action_receipt(action.request_id)
    assert receipt.control_revision is not None
    assert receipt.state == "pending"
    gate.status()  # Failed outcomes must never be eligible for promotion.
    before = list(rig.driver.commands)
    assert_error(503, lambda: gate.execute("start", action))
    assert rig.driver.commands == before
    rig.service = rig.new_service()
    rig.service.startup()
    restarted = build_gate(rig)
    restarted.recover_pending()
    before = list(rig.driver.commands)
    assert_error(503, lambda: restarted.execute("start", action))
    assert rig.driver.commands == before
    assert (
        rig.store.get_action_receipt(action.request_id).control_revision
        == receipt.control_revision
    )
    assert rig.service.status().state is ControllerState.FAULT


def test_slow_later_promotion_keeps_sound_historical_success(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    accepted = gate.execute("start", action)
    original = rig.store.promote_action_receipts

    def late_promotion(*args, **kwargs):
        original(*args, **kwargs)
        rig.advance(10)

    monkeypatch.setattr(rig.store, "promote_action_receipts", late_promotion)
    gate.status()
    receipt = rig.store.get_action_receipt(action.request_id)
    assert receipt.state == "success"
    assert receipt.control_revision == accepted.control_revision
    assert rig.service.status().state is not ControllerState.FAULT
    rig.service = rig.new_service()
    rig.service.startup()
    restarted = build_gate(rig)
    restarted.recover_pending()
    before = list(rig.driver.commands)
    replay = restarted.execute("start", action)
    assert replay.accepted is True
    assert replay.control_revision == accepted.control_revision
    assert rig.driver.commands == before


def test_failed_later_promotion_faults_without_replaying_action(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    gate.execute("start", action)

    def broken_promotion(*args, **kwargs):
        raise WeatherStateError("injected promotion failure")

    monkeypatch.setattr(rig.store, "promote_action_receipts", broken_promotion)
    with pytest.raises(WeatherStateError):
        gate.status()
    assert rig.service.status().state is ControllerState.FAULT
    before = list(rig.driver.commands)
    # This historical result was timely; replay must not attempt promotion.
    assert gate.execute("start", action).accepted is True
    assert rig.driver.commands == before


def test_validation_memory_and_provisional_retention_stay_bounded(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    current = gate.status()
    first_id = None
    for _ in range(130):
        action = WeatherActionInput(
            str(uuid4()), current["control_revision"], current["action_nonce"]
        )
        if first_id is None:
            first_id = action.request_id
        current = gate.execute("stop", action).status
        assert len(gate._validated) <= 128
    assert rig.store.get_action_receipt(first_id) is None
    with closing(sqlite3.connect(tmp_path / "weather.db")) as db:
        assert (
            db.execute("SELECT count(*) FROM weather_action_receipts").fetchone()[0]
            == 128
        )
        assert db.execute(
            "SELECT DISTINCT state FROM weather_action_receipts"
        ).fetchall() == [("pending",)]
    gate.status()
    assert not gate._validated
    with closing(sqlite3.connect(tmp_path / "weather.db")) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM weather_action_receipts WHERE state='success'"
            ).fetchone()[0]
            == 128
        )
    assert ActuatorCommand.SUPPLY not in rig.driver.commands


def test_crash_after_provisional_commit_before_deadline_validation(
    tmp_path, monkeypatch
):
    rig = Rig(tmp_path)
    rig.service.startup()
    gate = build_gate(rig)
    action = request(gate)
    original = rig.store.finish_action_receipt

    def crash_after_commit(*args, **kwargs):
        original(*args, **kwargs)
        raise SystemExit("crash before post-commit deadline check")

    monkeypatch.setattr(rig.store, "finish_action_receipt", crash_after_commit)
    with pytest.raises(SystemExit):
        gate.execute("start", action)
    receipt = rig.store.get_action_receipt(action.request_id)
    assert receipt.state == "pending"
    assert receipt.control_revision is not None
    rig.service = rig.new_service()
    rig.service.startup()
    restarted = build_gate(rig)
    restarted.recover_pending()
    before = list(rig.driver.commands)
    assert_error(503, lambda: restarted.execute("start", action))
    assert rig.driver.commands == before
    assert rig.service.status().state is ControllerState.FAULT
