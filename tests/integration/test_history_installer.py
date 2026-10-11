import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "deployment/shower-history"
sys.path.insert(0, str(FOLDER))
spec = importlib.util.spec_from_file_location("history_installer", FOLDER / "install_history.py")
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
sys.path.remove(str(FOLDER))


def test_backup_failure_prevents_install_and_leaves_stopped(monkeypatch, tmp_path):
    c = installer.c
    commands = []
    monkeypatch.setattr(c, "secure", lambda *a, **k: None)
    monkeypatch.setattr(c, "digest", lambda p: installer.DAEMON_SHA)
    monkeypatch.setattr(c, "active", lambda s: s != "nodered.service")
    monkeypatch.setattr(c, "flow", lambda: None)
    monkeypatch.setattr(c, "pair_high", lambda: None)
    monkeypatch.setattr(c, "stopped", lambda: commands.append("stopped"))
    monkeypatch.setattr(c, "drain", lambda: commands.append("drain"))
    monkeypatch.setattr(c, "venv_info", lambda: {"rpi-freeze-protect":"1.1.0"})
    monkeypatch.setattr(c, "run", lambda args, **kw: commands.append(args) or "")
    monkeypatch.setattr(installer, "config", lambda: {"FREEZE_PROTECT_WEATHER_SETTINGS_TOKEN":"private"})
    monkeypatch.setattr(installer, "status", lambda _: {})
    monkeypatch.setattr(installer, "persistent_stop", lambda: {"enabled":True})
    def fail(_):
        raise RuntimeError("BACKUP_FAILED")
    monkeypatch.setattr(installer, "archive_backup", fail)
    with pytest.raises(SystemExit):
        installer.install({"source_commit":"test"}, tmp_path)
    assert not any(isinstance(cmd, list) and "pip" in cmd for cmd in commands)
    assert ["systemctl", "start", c.HUB] not in commands
    assert commands[-1] == "drain"
    assert json.loads((tmp_path / "STOP.json").read_text())["install_started"] is False


def test_archive_backup_is_coherent_and_reads_back(monkeypatch, tmp_path):
    c = installer.c
    source = tmp_path / "source"
    source.mkdir()
    venv = source / "venv"
    venv.mkdir()
    (venv / "module.py").write_text("baseline")
    for name in ("env", "unit", "nginx"):
        (source / name).write_text(name)
    db = source / "state.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE test(value TEXT)")
        con.execute("INSERT INTO test VALUES ('preserved')")
    db.with_name(db.name + ".weather-identity").write_text("identity")
    for name, value in {"VENV":venv,"ENV":source / "env","UNIT":source / "unit","DB":db}.items():
        monkeypatch.setattr(c, name, value)
    monkeypatch.setattr(installer, "NGINX", source / "nginx")
    monkeypatch.setattr(c, "git", lambda *a: "baseline")
    backup = tmp_path / "backup"
    backup.mkdir()
    installer.archive_backup(backup)
    assert (backup / "BACKUP_COMPLETE").is_file()
    with sqlite3.connect(backup / "database.sqlite3") as con:
        assert con.execute("SELECT value FROM test").fetchone() == ("preserved",)
    assert (backup / "database.weather-identity").read_text() == "identity"


def test_persistent_stop_rejects_active_marker(monkeypatch, tmp_path):
    c = installer.c
    db = tmp_path / "state.db"
    identity = "a" * 32
    db.with_name(db.name + ".weather-identity").write_text(identity)
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE weather_metadata(singleton INTEGER, version TEXT, store_identity TEXT)")
        con.execute("INSERT INTO weather_metadata VALUES(1,'1',?)", (identity,))
        con.execute("CREATE TABLE weather_control(singleton INTEGER,payload_json TEXT)")
        con.execute("INSERT INTO weather_control VALUES(1,?)", (json.dumps({"user_off":True,"active_marker":"auto","fault_inhibited":False,"settings":{}}),))
    monkeypatch.setattr(c, "DB", db)
    with pytest.raises(RuntimeError, match="DURABLE_STOP_REQUIRED"):
        installer.persistent_stop()
