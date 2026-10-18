import importlib.util
from pathlib import Path

import pytest

PATH = (
    Path(__file__).resolve().parents[2]
    / "deployment/lighting/diagnostics/install_diagnostics.py"
)
SPEC = importlib.util.spec_from_file_location("fault_diagnostic_install", PATH)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def statuses():
    return (
        {
            "health": "OK",
            "mode": "MANUAL_OFF",
            "desired_on": False,
            "gpio_on": False,
            "manual_remaining_seconds": 1800,
        },
        {
            "mode": "weather_assisted",
            "operation": "USER_OFF",
            "state": "MANUAL_DRAIN",
            "command": "DRAIN",
            "reason": "user_off",
        },
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "AUTO"),
        ("health", "FAULT"),
        ("gpio_on", None),
        ("desired_on", True),
        ("manual_remaining_seconds", 299),
    ],
)
def test_light_must_be_healthy_inhibited_off_with_time_to_finish(field, value):
    light, shower = statuses()
    light[field] = value
    with pytest.raises(RuntimeError):
        installer.preflight(light, shower)


def test_shower_cannot_be_auto_or_faulted():
    light, shower = statuses()
    for operation in ("AUTO_SUPPLY", "FAULT"):
        shower["operation"] = operation
        with pytest.raises(RuntimeError):
            installer.preflight(light, shower)


def test_verified_off_states_are_accepted():
    installer.preflight(*statuses())


@pytest.fixture
def rig(tmp_path, monkeypatch):
    import json
    import sqlite3
    import time

    s = installer.support
    package, installed, evidence = [
        tmp_path / n for n in ("package", "installed", "evidence")
    ]
    for path in (package, installed, evidence):
        path.mkdir()
    targets, manifest = {}, {}
    for name in ("light_controller.py", "node_red.py"):
        targets[name] = installed / name
        targets[name].write_text("old = True")
        (package / name).write_text("new = True")
        manifest[name] = {
            "before": s.sha(targets[name]),
            "after": s.sha(package / name),
        }
    (package / "baseline.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(installer, "TARGETS", targets)
    monkeypatch.setattr(installer, "MARKER", tmp_path / "marker")
    monkeypatch.setattr(installer.tempfile, "mkdtemp", lambda **kw: str(evidence))
    for name in ("DB", "SHOWER_DB"):
        path = tmp_path / (name + ".db")
        with sqlite3.connect(path) as db:
            if name == "DB":
                db.execute("CREATE TABLE state(data TEXT)")
                db.execute(
                    "INSERT INTO state VALUES(?)",
                    (
                        json.dumps(
                            {
                                "mode": "MANUAL_OFF",
                                "fault": False,
                                "manual_until": time.time() + 1800,
                                "saved_at": time.time(),
                            }
                        ),
                    ),
                )
            else:
                db.execute(
                    "CREATE TABLE weather_control(singleton INTEGER, payload_json TEXT)"
                )
                db.execute(
                    "INSERT INTO weather_control VALUES(1,?)",
                    (
                        json.dumps(
                            {
                                "user_off": True,
                                "fault_inhibited": False,
                                "active_marker": None,
                                "settings": {"enabled": True},
                            }
                        ),
                    ),
                )
            db.execute("CREATE TABLE history(value TEXT)")
            db.execute("INSERT INTO history VALUES('preserved')")
        monkeypatch.setattr(s, name, path)
    s.SHOWER_DB.with_name(s.SHOWER_DB.name + ".weather-identity").write_text("a" * 32)
    for name in ("ENV", "SHOWER_ENV"):
        path = tmp_path / name
        path.write_text("private-secret")
        monkeypatch.setattr(s, name, path)
    monkeypatch.setattr(
        s,
        "environment",
        lambda path: (
            {"LIGHT_DB_PATH": str(s.DB)}
            if path == s.ENV
            else {
                "FREEZE_PROTECT_DB_PATH": str(s.SHOWER_DB),
                "FREEZE_PROTECT_CONTROL_MODE": "weather_assisted",
            }
        ),
    )
    monkeypatch.setattr(s, "secure", lambda path: None)
    monkeypatch.setattr(s, "clock_check", lambda: None)
    monkeypatch.setattr(s, "drain_check", lambda: None)
    calls, commands = [], []
    light, shower = statuses()

    def api(kind, endpoint):  # No payload parameter: any write fails the test.
        calls.append((kind, endpoint))
        if endpoint == "settings":
            return {"hold_seconds": 300, "manual_seconds": 1800}
        return dict(light if kind == "light" else shower)

    def run(*args):
        commands.append(args)
        if args[1] == "is-active":
            return "active"
        if "--property=NeedDaemonReload" in args:
            return "no"
        if "--property=ActiveState" in args:
            return "inactive"
        return ""

    monkeypatch.setattr(s, "API", lambda *args: api)
    monkeypatch.setattr(s, "run", run)
    return package, evidence, targets, commands, calls


def test_install_only_patches_two_sources_preserves_history_and_never_posts(
    rig, capsys
):
    import sqlite3

    package, evidence, targets, commands, calls = rig
    installer.install_locked(package)
    assert (evidence / "success.json").exists()
    for name, target in targets.items():
        assert target.read_bytes() == (package / name).read_bytes()
        assert (evidence / name).read_text() == "old = True"
    for name in ("light", "shower"):
        with sqlite3.connect(evidence / (name + ".db")) as db:
            assert db.execute("SELECT value FROM history").fetchall() == [
                ("preserved",)
            ]
    assert [c for c in commands if c[1] in ("stop", "start", "restart")] == [
        ("systemctl", "stop", "light-controller.service"),
        ("systemctl", "stop", "freeze-protect.service"),
        ("systemctl", "start", "freeze-protect.service"),
        ("systemctl", "start", "light-controller.service"),
    ]
    assert set(calls) <= {
        ("light", "settings"),
        ("light", "status"),
        ("shower", "display/status"),
    }
    assert "private-secret" not in capsys.readouterr().out


def test_source_drift_prevents_any_service_mutation(rig):
    package, evidence, targets, commands, _ = rig
    targets["node_red.py"].write_text("changed = True")
    with pytest.raises(RuntimeError, match="BASELINE_CHANGED"):
        installer.install_locked(package)
    assert commands == [] and not (evidence / "success.json").exists()


def test_backup_failure_leaves_running_services_untouched(rig, monkeypatch):
    package, evidence, _, commands, _ = rig

    def fail(*args):
        raise RuntimeError("BACKUP_FAILED")

    monkeypatch.setattr(installer.support, "backup_db", fail)
    with pytest.raises(RuntimeError, match="BACKUP_FAILED"):
        installer.install_locked(package)
    assert not any(c[1] in ("stop", "start") for c in commands)
    assert not (evidence / "install-started.json").exists()


@pytest.mark.parametrize(
    "mode,fault,deadline",
    [
        ("AUTO", False, 1800),
        ("MANUAL_OFF", True, 1800),
        ("MANUAL_OFF", False, 60),
        ("MANUAL_OFF", False, float("nan")),
    ],
)
def test_invalid_durable_inhibition_prevents_restart(rig, mode, fault, deadline):
    import json
    import sqlite3
    import time

    package, evidence, targets, commands, _ = rig
    with sqlite3.connect(installer.support.DB) as db:
        db.execute(
            "UPDATE state SET data=?",
            (
                json.dumps(
                    {
                        "mode": mode,
                        "fault": fault,
                        "manual_until": time.time() + deadline,
                        "saved_at": time.time(),
                    }
                ),
            ),
        )
    with pytest.raises(RuntimeError, match="DURABLE_MANUAL_OFF_REQUIRED"):
        installer.install_locked(package)
    assert not any(c[1] == "start" for c in commands)
    assert not (evidence / "install-started.json").exists()
    assert all(t.read_text() == "old = True" for t in targets.values())


def test_source_write_failure_never_restarts_or_rolls_back(rig, monkeypatch):
    package, evidence, _, commands, _ = rig

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(installer, "replace_source", fail)
    with pytest.raises(OSError):
        installer.install_locked(package)
    assert not any(c[1] == "start" for c in commands)
    assert (evidence / "install-started.json").exists()
    assert not (evidence / "success.json").exists()


def test_shower_durable_user_off_is_required(rig):
    import json
    import sqlite3

    package, evidence, _, commands, _ = rig
    with sqlite3.connect(installer.support.SHOWER_DB) as db:
        db.execute(
            "UPDATE weather_control SET payload_json=?",
            (
                json.dumps(
                    {
                        "user_off": False,
                        "fault_inhibited": False,
                        "active_marker": None,
                        "settings": {},
                    }
                ),
            ),
        )
    with pytest.raises(RuntimeError, match="DURABLE_USER_OFF_REQUIRED"):
        installer.install_locked(package)
    assert not any(c[1] == "start" for c in commands)
    assert not (evidence / "success.json").exists()
