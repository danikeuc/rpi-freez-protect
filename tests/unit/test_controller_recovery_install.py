"""Only OFF and clear-fault/DRAIN are allowed during bounded recovery."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "controller_recovery_install",
    Path(__file__).resolve().parents[2]
    / "deployment/lighting/recovery/recover_controllers.py",
)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class API:
    def __init__(self):
        self.light = {
            "health": "FAULT",
            "desired_on": False,
            "gpio_on": False,
            "mode": "AUTO",
            "revision": 70,
        }
        self.shower = {
            "mode": "weather_assisted",
            "operation": "FAULT",
            "state": "FAULT",
            "command": "DRAIN",
        }
        self.writes = []
        self.lose_receipt = False
        self.bad_light_receipt = False
        self.bad_shower_receipt = False

    def __call__(self, kind, endpoint, payload=None):
        if payload is None and endpoint == "settings":
            return {"hold_seconds": 300, "manual_seconds": 1800, "revision": 1}
        if payload is None:
            return dict(self.light if kind == "light" else self.shower)
        self.writes.append((kind, endpoint, payload))
        if self.lose_receipt:
            raise TimeoutError("ambiguous")
        if kind == "light":
            assert (
                payload["action"] == "manual_off" and payload["expected_revision"] == 70
            )
            if not self.bad_light_receipt:
                self.light.update(
                    health="OK", mode="MANUAL_OFF", manual_remaining_seconds=1800
                )
            return dict(self.light)
        if not self.bad_shower_receipt:
            self.shower.update(
                operation="USER_OFF", state="MANUAL_DRAIN", reason="user_off"
            )
        return dict(self.shower)


def test_recovery_uses_only_manual_off_and_clear_fault():
    api = API()
    checks, records = [], []
    result = installer.recover(
        api, lambda: checks.append(True), lambda name, value: records.append(name)
    )
    assert [(kind, endpoint) for kind, endpoint, _ in api.writes] == [
        ("light", "actions"),
        ("shower", "commands/clear-fault"),
    ]
    assert result["light"]["mode"] == "MANUAL_OFF"
    assert result["shower"]["operation"] == "USER_OFF"
    assert checks and records.index("light-action-started.json") < records.index(
        "light-recovered.json"
    )


@pytest.mark.parametrize(
    "field,value",
    [("gpio_on", True), ("gpio_on", None), ("desired_on", True), ("health", "OK")],
)
def test_changed_light_state_stops_before_writes(field, value):
    api = API()
    api.light[field] = value
    with pytest.raises(RuntimeError):
        installer.recover(api, lambda: None, lambda *a: None)
    assert api.writes == []


@pytest.mark.parametrize(
    "field,value",
    [("mode", "automatic"), ("operation", "AUTO_SUPPLY"), ("command", "SUPPLY")],
)
def test_changed_shower_state_stops_before_writes(field, value):
    api = API()
    api.shower[field] = value
    with pytest.raises(RuntimeError):
        installer.recover(api, lambda: None, lambda *a: None)
    assert api.writes == []


def test_failed_pin_check_prevents_all_writes():
    api = API()

    def fail():
        raise RuntimeError("READBACK_FAILED")

    with pytest.raises(RuntimeError):
        installer.recover(api, fail, lambda *a: None)
    assert api.writes == []


def test_ambiguous_action_is_never_retried_or_followed_by_shower_recovery():
    api = API()
    api.lose_receipt = True
    with pytest.raises(TimeoutError):
        installer.recover(api, lambda: None, lambda *a: None)
    assert len(api.writes) == 1


def test_failed_light_receipt_blocks_shower_recovery():
    api = API()
    api.bad_light_receipt = True
    with pytest.raises(RuntimeError):
        installer.recover(api, lambda: None, lambda *a: None)
    assert len(api.writes) == 1


def test_failed_drain_receipt_is_not_accepted_or_retried():
    api = API()
    api.bad_shower_receipt = True
    with pytest.raises(RuntimeError):
        installer.recover(api, lambda: None, lambda *a: None)
    assert len(api.writes) == 2


def test_already_user_off_shower_needs_no_mutation():
    api = API()
    api.shower.update(operation="USER_OFF", state="MANUAL_DRAIN", reason="user_off")
    installer.recover(api, lambda: None, lambda *a: None)
    assert len(api.writes) == 1


def test_source_drift_and_tampered_payload_stop(tmp_path, monkeypatch):
    target = tmp_path / "installed"
    target.mkdir()
    for name in ("controller.py", "models.py"):
        (target / name).write_text("pass")
        (tmp_path / name).write_text("pass")
    monkeypatch.setattr(installer, "BASE", target)
    monkeypatch.setattr(installer, "secure", lambda p: None)
    manifest = {
        n: {"before": installer.sha(target / n), "after": installer.sha(tmp_path / n)}
        for n in ("controller.py", "models.py")
    }
    installer.validate_sources(tmp_path, manifest)
    (target / "models.py").write_text("drift")
    with pytest.raises(RuntimeError, match="BASELINE_CHANGED"):
        installer.validate_sources(tmp_path, manifest)
    (target / "models.py").write_text("pass")
    (tmp_path / "controller.py").write_text("tampered")
    with pytest.raises(RuntimeError, match="PACKAGE_CHANGED"):
        installer.validate_sources(tmp_path, manifest)


def test_private_receipt_cannot_overwrite_previous_attempt(tmp_path):
    f = tmp_path / "started"
    installer.private(f, b"first")
    with pytest.raises(FileExistsError):
        installer.private(f, b"second")
    assert f.read_bytes() == b"first"


@pytest.mark.parametrize("fault", [False, None, "true"])
def test_restart_requires_durable_fault_to_keep_camera_inhibited(tmp_path, fault):
    import json
    import sqlite3

    db = tmp_path / "state.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE state(data TEXT)")
        connection.execute(
            "INSERT INTO state VALUES (?)", (json.dumps({"fault": fault}),)
        )
    with pytest.raises(RuntimeError, match="DURABLE_FAULT_REQUIRED"):
        installer.require_durable_fault(db)


def test_consistent_backup_preserves_history_and_fault(tmp_path):
    import json
    import sqlite3

    source, backup = tmp_path / "state.db", tmp_path / "backup.db"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE state(data TEXT)")
        connection.execute(
            "INSERT INTO state VALUES (?)", (json.dumps({"fault": True}),)
        )
        connection.execute("CREATE TABLE history(id INTEGER PRIMARY KEY, data TEXT)")
        connection.execute("INSERT INTO history VALUES (1, 'original')")
        connection.commit()
        installer.backup_db(source, backup)
        installer.require_durable_fault(backup)
        with sqlite3.connect(backup) as saved:
            assert saved.execute("SELECT * FROM history").fetchall() == [
                (1, "original")
            ]


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        ("actions", {"action": "manual_on"}),
        ("actions", {"action": "auto"}),
        ("settings", {"hold_seconds": 60}),
    ],
)
def test_http_client_rejects_on_auto_and_settings_writes(endpoint, payload):
    api = installer.API({"LIGHT_DISPLAY_TOKEN": "x" * 32}, {})
    with pytest.raises(RuntimeError, match="ACTION_REJECTED|API_ROUTE_REJECTED"):
        api("light", endpoint, payload)


@pytest.fixture
def install_rig(tmp_path, monkeypatch):
    import json
    import sqlite3

    package, installed, evidence = (
        tmp_path / name for name in ("package", "installed", "evidence")
    )
    for directory in (package, installed, evidence):
        directory.mkdir()
    manifest = {}
    for name in ("controller.py", "models.py"):
        (installed / name).write_text("old = True")
        (package / name).write_text("new = True")
        manifest[name] = {
            "before": installer.sha(installed / name),
            "after": installer.sha(package / name),
        }
    (package / "baseline.json").write_text(json.dumps(manifest))
    for name in ("DB", "SHOWER_DB"):
        path = tmp_path / (name + ".db")
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE state(data TEXT)")
            db.execute("INSERT INTO state VALUES (?)", (json.dumps({"fault": True}),))
            db.execute("CREATE TABLE history(id INTEGER PRIMARY KEY, data TEXT)")
            db.execute("INSERT INTO history VALUES (1, 'preserved')")
        monkeypatch.setattr(installer, name, path)
    for name in ("ENV", "SHOWER_ENV"):
        path = tmp_path / name
        path.write_text("secret configuration")
        monkeypatch.setattr(installer, name, path)
    light_env = {
        "LIGHT_DB_PATH": str(installer.DB),
        "LIGHT_DISPLAY_TOKEN": "display-secret-" * 4,
        "LIGHT_SETTINGS_TOKEN": "settings-secret-" * 4,
    }
    shower_env = {
        "FREEZE_PROTECT_DB_PATH": str(installer.SHOWER_DB),
        "FREEZE_PROTECT_CONTROL_MODE": "weather_assisted",
        "FREEZE_PROTECT_DISPLAY_TOKEN": "display-secret-" * 4,
        "FREEZE_PROTECT_ADMIN_TOKEN": "admin-secret-" * 4,
    }
    monkeypatch.setattr(
        installer,
        "environment",
        lambda path: light_env if path == installer.ENV else shower_env,
    )
    monkeypatch.setattr(installer, "secure", lambda path: None)
    monkeypatch.setattr(installer, "BASE", installed)
    monkeypatch.setattr(installer, "MARKER", tmp_path / "started")
    monkeypatch.setattr(installer.tempfile, "mkdtemp", lambda **kwargs: str(evidence))
    monkeypatch.setattr(installer, "clock_check", dict)
    monkeypatch.setattr(installer, "drain_check", lambda: None)
    api = API()
    monkeypatch.setattr(installer, "API", lambda *args: api)
    commands = []

    def run(*args):
        commands.append(args)
        if args[1] == "is-active":
            return "active"
        if "--property=NeedDaemonReload" in args:
            return "no"
        if "--property=ActiveState" in args:
            return "inactive"
        return ""

    monkeypatch.setattr(installer, "run", run)
    return package, installed, evidence, api, commands


def test_full_installer_preserves_both_databases_and_restarts_only_light(
    install_rig, capsys
):
    import sqlite3

    package, installed, evidence, api, commands = install_rig
    installer._install_locked(package)
    assert (evidence / "success.json").exists()
    assert (installed / "controller.py").read_bytes() == (
        package / "controller.py"
    ).read_bytes()
    for name in ("light", "shower"):
        with sqlite3.connect(evidence / (name + ".db")) as db:
            assert db.execute("SELECT * FROM history").fetchall() == [(1, "preserved")]
    mutations = [cmd for cmd in commands if cmd[1] in {"stop", "start", "restart"}]
    assert mutations == [
        ("systemctl", "stop", "light-controller.service"),
        ("systemctl", "start", "light-controller.service"),
    ]
    assert len(api.writes) == 2
    output = capsys.readouterr().out
    assert "CONTROLLERS_RECOVERED_OFF" in output and "secret" not in output


def test_backup_failure_stops_without_restart_actions_or_success(
    install_rig, monkeypatch
):
    package, _installed, evidence, api, commands = install_rig
    original = installer.backup_db

    def fail_light(source, target):
        if source == installer.DB:
            raise RuntimeError("BACKUP_FAILED")
        return original(source, target)

    monkeypatch.setattr(installer, "backup_db", fail_light)
    with pytest.raises(RuntimeError, match="BACKUP_FAILED"):
        installer._install_locked(package)
    assert (evidence / "before.json").exists()
    assert not (evidence / "install-started.json").exists()
    assert not (evidence / "success.json").exists()
    assert api.writes == []
    assert not any(cmd[1] == "start" for cmd in commands)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("HTTP Error 503: secret", ["http_503"]),
        ("Node-RED receipt does not match the request secret", ["receipt_mismatch"]),
        ("Connection refused secret", ["connection_refused"]),
        ("unknown secret", ["unclassified"]),
    ],
)
def test_adapter_diagnostic_exposes_categories_only(message, expected):
    result = installer.adapter_diagnostic(
        {"items": [{"event_type": "relay_driver_error", "payload": {"error": message}}]}
    )
    assert result == {"latest_relay_failure_categories": expected}
    assert "secret" not in str(result)
