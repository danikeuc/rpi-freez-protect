import pytest
from conftest import Clock, Output

from freeze_protect.lighting.controller import LightController, LightError
from freeze_protect.lighting.models import Action, Event, SettingsUpdate


@pytest.fixture
def rig(tmp_path):
    clock, output = Clock(), Output()
    controller = LightController(tmp_path / "light.db", output, {"camera-1"}, clock)
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
    clock.advance(3601)
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
    retried = c.actions(request)
    assert retried.health == "FAULT"
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
