import pytest
from conftest import Clock, Output

from freeze_protect.lighting.controller import LightController, LightError
from freeze_protect.lighting.models import Action, Event, SettingsUpdate


@pytest.fixture
def rig(tmp_path):
    clock, output = Clock(), Output()
    controller = LightController(
        tmp_path / "light.db", output, {"camera-1"}, clock, provision_new_database=True
    )
    return controller, clock, output


def action(c, name, rid="request-1"):
    return c.actions(
        Action(request_id=rid, expected_revision=c.status().revision, action=name)
    )


def event(c, clock, eid="event-1"):
    return c.events(
        Event(event_id=eid, source_id="camera-1", occurred_at=clock.stamp())
    )


def test_auto_holds_overlap_and_reads_do_not_change_revision(rig):
    c, clock, output = rig
    assert c.settings().hold_seconds == 300
    clock.advance(0.01)
    first = event(c, clock)
    clock.advance(100)
    action(c, "timed_on")
    clock.advance(201)
    c.tick()
    assert c.status().desired_on and output.on
    rev = c.status().revision
    assert c.status().revision == rev
    clock.advance(100)
    c.tick()
    assert not c.status().desired_on and not output.on
    assert first.accepted


def test_camera_duplicate_does_not_extend_and_changed_identity_conflicts(rig):
    c, clock, _ = rig
    original = Event(event_id="evt", source_id="camera-1", occurred_at=clock.stamp())
    c.events(original)
    clock.advance(200)
    assert c.events(original).duplicate
    clock.advance(101)
    c.tick()
    assert not c.status().desired_on
    with pytest.raises(LightError) as exc:
        c.events(original.model_copy(update={"occurred_at": clock.stamp()}))
    assert exc.value.code == 409


def test_manual_blocks_camera_and_returns_off_without_replay(rig):
    c, clock, output = rig
    s = action(c, "manual_on")
    assert s.mode == "MANUAL_ON" and s.manual_remaining_seconds == 3600
    assert not event(c, clock).accepted
    clock.advance(4501)
    c.tick()
    assert c.status().mode == "AUTO" and not output.on
    clock.advance(0.01)
    assert event(c, clock, "fresh").accepted


def test_stale_revision_and_retry_id_are_fenced(rig):
    c, clock, _ = rig
    a = Action(
        request_id="same", expected_revision=c.status().revision, action="manual_off"
    )
    first = c.actions(a)
    clock.advance(60)
    assert c.actions(a) == first
    with pytest.raises(LightError):
        c.actions(a.model_copy(update={"action": "manual_on"}))
    with pytest.raises(LightError):
        c.actions(Action(request_id="stale", expected_revision=0, action="manual_on"))


def test_camera_freshness_allowlist_and_mode_boundary(rig):
    c, clock, _ = rig
    old = Event(event_id="old", source_id="camera-1", occurred_at=clock.stamp())
    clock.advance(10)
    action(c, "manual_off")
    action(c, "auto", "back")
    assert not c.events(old).accepted
    with pytest.raises(LightError):
        c.events(old.model_copy(update={"event_id": "unknown", "source_id": "nope"}))
    clock.advance(61)
    with pytest.raises(LightError):
        c.events(old.model_copy(update={"event_id": "stale"}))


def test_settings_do_not_extend_running_deadline(rig):
    c, clock, _ = rig
    action(c, "manual_off")
    c.update_settings(
        SettingsUpdate(
            request_id="settings",
            expected_revision=0,
            hold_seconds=60,
            manual_seconds=120,
        )
    )
    clock.advance(3500)
    assert c.status().manual_remaining_seconds == 100


def test_restart_recovers_manual_on_inhibited_and_dedup_persisted(rig, tmp_path):
    c, clock, output = rig
    action(c, "manual_on")
    e = Event(event_id="ignored", source_id="camera-1", occurred_at=clock.stamp())
    c.events(e)
    clock.advance(60)
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().mode == "MANUAL_OFF"
    assert restarted.status().manual_remaining_seconds == 3540
    assert not output.on
    assert restarted.events(e).duplicate


def test_clock_fault_and_uncertain_output_require_explicit_recovery(rig):
    c, clock, output = rig
    action(c, "timed_on")
    clock.wall -= 30
    c.tick()
    assert c.status().health == "FAULT" and not c.status().desired_on
    clock.wall += 30
    with pytest.raises(LightError):
        event(c, clock)
    assert not output.on
    action(c, "auto", "recover")
    output.fail = True
    with pytest.raises(LightError):
        action(c, "manual_on", "uncertain")
    assert c.status().health == "FAULT" and not c.status().desired_on
    output.fail = False
    c.tick()
    assert c.status().health == "FAULT"


def test_store_failure_turns_off_and_never_confirms_on(rig):
    c, _clock, output = rig
    action(c, "timed_on")
    c.store.connection.close()
    with pytest.raises(LightError):
        action(c, "manual_on", "disk-fail")
    assert not output.on and c.status().health == "FAULT"


def test_renewal_generation_change_is_fault_and_no_automatic_begin(rig):
    c, _clock, output = rig
    action(c, "timed_on")
    output.generation = "new-boot"
    c.tick()
    assert not output.on and c.status().health == "FAULT"
    begins = output.calls.count("begin")
    c.tick()
    assert output.calls.count("begin") == begins


def test_history_and_status_do_not_write_sqlite(rig):
    c, _clock, output = rig
    statements = []
    c.store.connection.set_trace_callback(statements.append)
    before = len(output.calls)
    for _ in range(3):
        c.status()
        c.settings()
        c.history()
    assert all(sql.startswith("SELECT") for sql in statements)
    assert len(output.calls) == before


def test_cache_full_rejects_event_without_energizing_or_evicting_valid_ids(rig):
    c, clock, output = rig
    with c.store.connection:
        c.store.connection.executemany(
            "INSERT INTO identities VALUES (?,?,?,?,?)",
            [
                ("action", f"id-{i}", "fingerprint", "{}", clock.time() + 1000)
                for i in range(4096)
            ],
        )
    clock.advance(0.01)
    with pytest.raises(LightError) as exc:
        event(c, clock)
    assert exc.value.code == 429
    assert not output.on and not c.status().desired_on
    assert (
        c.store.connection.execute("SELECT COUNT(*) FROM identities").fetchone()[0]
        == 4096
    )


def test_store_keeps_history_bounded(rig):
    c, clock, _output = rig
    for i in range(1020):
        c.store.save(
            c.state,
            clock.time(),
            history=(clock.stamp(), "camera", "AUTO", False, str(i)),
        )
    assert (
        c.store.connection.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 1000
    )
    assert c.history(1)["items"][0]["reason"] == "1019"


def test_corrupted_state_starts_faulted_off_until_explicit_auto(rig, tmp_path):
    c, clock, output = rig
    with c.store.connection:
        c.store.connection.execute("UPDATE state SET data='bad json'")
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().health == "FAULT" and not output.on
    action(restarted, "auto", "recover-bad-state")
    assert restarted.status().health == "OK" and not output.on


def test_clock_forward_fault_can_recover_by_explicit_auto(rig):
    c, clock, output = rig
    action(c, "manual_on")
    clock.wall += 100
    c.tick()
    assert c.status().health == "FAULT" and not output.on
    action(c, "auto", "recover-clock")
    assert c.status().health == "OK" and c.status().mode == "AUTO"


def test_begin_wrong_generation_never_confirms_on(rig):
    c, _clock, output = rig
    output.generation = "restarted-between-off-and-on"
    with pytest.raises(LightError):
        action(c, "manual_on")
    assert c.status().health == "FAULT" and not output.on


def test_manual_fault_is_not_cleared_by_timer_expiry(rig):
    c, clock, output = rig
    action(c, "manual_on")
    output.fail = True
    c.tick()
    output.fail = False
    clock.advance(3601)
    c.tick()
    assert c.status().health == "FAULT" and c.status().mode == "MANUAL_ON"
    assert not output.on


def test_restart_clock_rollback_faults_and_expired_manual_returns_auto(rig, tmp_path):
    c, clock, output = rig
    action(c, "manual_off")
    clock.wall -= 10
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().health == "FAULT"
    action(restarted, "auto", "recover")
    action(restarted, "manual_off", "new-manual")
    clock.advance(3601)
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().mode == "AUTO" and not output.on


def test_distinct_camera_event_extends_hold_and_auto_off_clears_both(rig):
    c, clock, output = rig
    clock.advance(0.01)
    event(c, clock)
    clock.advance(250)
    event(c, clock, "later")
    clock.advance(60)
    c.tick()
    assert output.on
    action(c, "off")
    c.tick()
    assert not output.on and c.status().mode == "AUTO"


def test_failed_post_on_commit_preserves_uncertain_id_and_requests_off(
    rig, monkeypatch
):
    import sqlite3

    c, _clock, output = rig
    original_save = c.store.save
    calls = 0

    def fail_final_save(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("disk full after receipt")
        return original_save(*args, **kwargs)

    monkeypatch.setattr(c.store, "save", fail_final_save)
    request = Action(
        request_id="uncertain-id",
        expected_revision=c.status().revision,
        action="manual_on",
    )
    with pytest.raises(LightError):
        c.actions(request)
    assert not output.on and c.status().health == "FAULT"
    begins = output.calls.count("begin")
    with pytest.raises(LightError) as retry_error:
        c.actions(request)
    assert retry_error.value.code == 503
    assert output.calls.count("begin") == begins


def test_serialized_racing_actions_accept_only_one_expected_revision(rig):
    import concurrent.futures

    c, _clock, _output = rig
    revision = c.status().revision

    def submit(index):
        try:
            c.actions(
                Action(
                    request_id=f"race-{index}",
                    expected_revision=revision,
                    action="manual_off",
                )
            )
            return 200
        except LightError as error:
            return error.code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [200, 409]


def test_nonfinite_persisted_clock_is_recovery_fault(rig, tmp_path):
    import json

    c, clock, output = rig
    data = c.state.model_dump()
    data["saved_at"] = float("nan")
    with c.store.connection:
        c.store.connection.execute("UPDATE state SET data=?", (json.dumps(data),))
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().health == "FAULT" and not output.on


def test_revision_exhaustion_never_leaves_desired_on(rig):
    from freeze_protect.lighting.models import MAX_REVISION

    c, _clock, output = rig
    c.state.revision = MAX_REVISION
    with pytest.raises(LightError):
        action(c, "manual_on")
    assert not c.status().desired_on and not output.on


def test_corrupt_state_recovery_never_reuses_captured_control_revision(rig, tmp_path):
    c, clock, output = rig
    action(c, "manual_off")
    old = Action(
        request_id="captured-unused",
        expected_revision=c.status().revision,
        action="timed_on",
    )
    with c.store.connection:
        c.store.connection.execute("UPDATE state SET data='corrupt'")
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().health == "FAULT"
    action(restarted, "auto", "recovery")
    with pytest.raises(LightError) as error:
        restarted.actions(old)
    assert error.value.code == 409
    assert not output.on


def test_missing_revision_watermark_cannot_recover_or_accept_stale_action(
    rig, tmp_path
):
    from freeze_protect.lighting.models import MAX_REVISION

    c, clock, output = rig
    with c.store.connection:
        c.store.connection.execute("DELETE FROM revision_fence")
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().revision == MAX_REVISION
    assert restarted.status().health == "FAULT"
    with pytest.raises(LightError) as error:
        action(restarted, "auto", "untrusted-recovery")
    assert error.value.code == 503 and not output.on


def test_missing_database_requires_explicit_provisioning(tmp_path):
    path = tmp_path / "missing.db"
    clock, output = Clock(), Output()
    c = LightController(path, output, {"camera-1"}, clock)
    assert not path.exists() and c.status().health == "UNAVAILABLE"
    with pytest.raises(LightError) as error:
        action(c, "manual_on")
    assert error.value.code == 503 and not output.on


def test_corrupt_state_recovery_fences_captured_settings_update(rig, tmp_path):
    c, clock, output = rig
    old = SettingsUpdate(
        request_id="captured-settings",
        expected_revision=c.settings().revision,
        hold_seconds=180,
        manual_seconds=300,
    )
    c.update_settings(
        SettingsUpdate(
            request_id="first-settings",
            expected_revision=0,
            hold_seconds=60,
            manual_seconds=120,
        )
    )
    current = old.model_copy(
        update={
            "request_id": "captured-current-settings",
            "expected_revision": c.settings().revision,
        }
    )
    with c.store.connection:
        c.store.connection.execute("UPDATE state SET data='corrupt'")
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    action(restarted, "auto", "recovery")
    for captured in (old, current):
        with pytest.raises(LightError) as error:
            restarted.update_settings(captured)
        assert error.value.code == 409
    assert not output.on


@pytest.mark.parametrize("corruption", ["missing", "control", "settings"])
def test_untrusted_revision_watermark_rejects_captured_settings_without_change(
    rig, tmp_path, corruption
):
    c, clock, output = rig
    old = SettingsUpdate(
        request_id="captured-settings-untrusted",
        expected_revision=c.settings().revision,
        hold_seconds=180,
        manual_seconds=300,
    )
    with c.store.connection:
        if corruption == "missing":
            c.store.connection.execute("DELETE FROM revision_fence")
        elif corruption == "control":
            c.store.connection.execute("UPDATE revision_fence SET revision='malformed'")
        else:
            c.store.connection.execute(
                "UPDATE revision_fence SET settings_revision='malformed'"
            )
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    before = restarted.settings()
    with pytest.raises(LightError) as error:
        restarted.update_settings(old)
    assert error.value.code in {409, 503}
    assert restarted.settings() == before
    assert not output.on


def test_manual_on_expiry_has_fifteen_minute_camera_cooldown(rig):
    c, clock, output = rig
    action(c, "manual_on")
    clock.advance(3600)
    c.tick()
    assert not output.on
    assert c.status().mode == "MANUAL_OFF"
    assert c.status().reason == "manual_cooldown"
    assert c.status().manual_remaining_seconds == 900
    assert not event(c, clock, "during-cooldown").accepted
    clock.advance(899)
    c.tick()
    assert c.status().mode == "MANUAL_OFF"
    clock.advance(1)
    c.tick()
    assert c.status().mode == "AUTO" and not output.on
    clock.advance(0.01)
    assert event(c, clock, "after-cooldown").accepted


@pytest.mark.parametrize("elapsed", [3599, 3600, 4000, 4501])
def test_restart_preserves_cooldown_without_reenergizing(rig, tmp_path, elapsed):
    c, clock, output = rig
    action(c, "manual_on")
    c.close()
    clock.advance(elapsed)
    c = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert not output.on and c.status().health == "OK"
    if elapsed < 4500:
        assert c.status().mode == "MANUAL_OFF"
        clock.advance(4500 - elapsed)
        c.tick()
    assert c.status().mode == "AUTO"
    assert not output.on


def test_explicit_auto_cancels_cooldown_and_manual_off_has_no_extra_delay(rig):
    c, clock, output = rig
    action(c, "manual_on")
    clock.advance(3600)
    c.tick()
    action(c, "auto", "early-auto")
    assert c.status().mode == "AUTO" and not output.on
    action(c, "manual_off", "manual-off")
    clock.advance(3600)
    c.tick()
    assert c.status().mode == "AUTO" and not output.on


def test_cooldown_is_not_extended_by_settings_or_duplicate_action(rig):
    c, clock, output = rig
    request = Action(
        request_id="on", expected_revision=c.status().revision, action="manual_on"
    )
    c.actions(request)
    clock.advance(3600)
    c.tick()
    c.update_settings(
        SettingsUpdate(
            request_id="settings",
            expected_revision=0,
            hold_seconds=60,
            manual_seconds=7200,
        )
    )
    c.actions(request)
    clock.advance(900)
    c.tick()
    assert c.status().mode == "AUTO" and not output.on


@pytest.mark.parametrize("delta", [-100, 100])
def test_fault_recovers_to_manual_off_without_enabling_camera(rig, tmp_path, delta):
    c, clock, output = rig
    clock.wall += delta
    c.tick()
    assert c.status().health == "FAULT"
    output.calls.clear()
    request = Action(
        request_id="recover-off",
        expected_revision=c.status().revision,
        action="manual_off",
    )
    result = c.actions(request)
    assert result.health == "OK" and result.mode == "MANUAL_OFF"
    assert result.gpio_on is False and result.desired_on is False
    assert result.manual_remaining_seconds == c.settings().manual_seconds
    assert output.calls and set(output.calls) == {"off"}
    assert not c.state.fault
    assert not event(c, clock, "camera-during-recovery").accepted
    count = len(output.calls)
    clock.advance(10)
    assert c.actions(request) == result
    assert len(output.calls) == count
    c.close()
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().health == "OK" and restarted.status().mode == "MANUAL_OFF"
    assert restarted.status().gpio_on is False


def test_fault_manual_off_requires_fresh_off_receipt(rig):
    c, clock, output = rig
    clock.wall += 100
    c.tick()
    output.fail = True
    output.calls.clear()
    with pytest.raises(LightError):
        action(c, "manual_off", "failed-recovery")
    assert output.calls and set(output.calls) == {"off"}
    assert c.status().health == "FAULT" and c.state.fault
    assert c.status().gpio_on is None


def test_fault_manual_off_rejects_stale_revision_before_output(rig):
    c, clock, output = rig
    stale = c.status().revision
    clock.wall += 100
    c.tick()
    output.calls.clear()
    with pytest.raises(LightError) as error:
        c.actions(
            Action(
                request_id="stale-recovery",
                expected_revision=stale,
                action="manual_off",
            )
        )
    assert error.value.code == 409 and output.calls == []
    assert c.status().health == "FAULT"


def test_fault_manual_off_does_not_clear_unconfigured_controller(rig):
    c, clock, _output = rig
    clock.wall += 100
    c.tick()
    c.configured = False
    with pytest.raises(LightError):
        action(c, "manual_off", "unconfigured-recovery")
    assert c.status().health != "OK" and c.state.fault


@pytest.mark.parametrize("failure_call", [1, 2])
def test_manual_off_recovery_storage_failure_relatches_fault(
    rig, tmp_path, monkeypatch, failure_call
):
    import sqlite3

    c, clock, output = rig
    clock.wall += 100
    c.tick()
    original_save = c.store.save
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise sqlite3.OperationalError("disk full")
        return original_save(*args, **kwargs)

    monkeypatch.setattr(c.store, "save", fail_once)
    output.calls.clear()
    with pytest.raises(LightError):
        action(c, "manual_off", "storage-failed-recovery")
    assert c.status().health == "FAULT" and c.state.fault
    assert not output.on and set(output.calls) == {"off"}
    c.close()
    restarted = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
    assert restarted.status().health == "FAULT" and not output.on


def test_clock_fault_logs_numeric_deltas_without_changing_fault_policy(rig, caplog):
    c, clock, output = rig
    clock.wall += 100
    c.tick()
    assert c.status().reason == "clock_or_lease_fault"
    assert c.status().health == "FAULT" and not output.on
    assert "clock discontinuity" in caplog.text
    assert "wall_delta_s=100" in caplog.text and "monotonic_delta_s=0" in caplog.text
    count = len(caplog.records)
    c.tick()
    assert len(caplog.records) == count


def test_renewal_failure_logs_stage_without_private_exception(rig, caplog):
    c, _clock, output = rig
    action(c, "manual_on")

    def fail():
        raise OSError("private-socket-path-or-token")

    output.renew = fail
    c.tick()
    assert c.status().health == "FAULT" and not output.on
    assert "stage=renewal" in caplog.text
    assert "private-socket-path-or-token" not in caplog.text
    assert "clock discontinuity" not in caplog.text
