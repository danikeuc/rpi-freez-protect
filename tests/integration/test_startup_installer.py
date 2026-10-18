import importlib.util
import json
import sys
from pathlib import Path

import pytest

FOLDER = Path(__file__).resolve().parents[2] / "deployment/startup-readiness"
sys.path.insert(0, str(FOLDER))
spec = importlib.util.spec_from_file_location("startup_installer", FOLDER / "install_readiness.py")
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
sys.path.remove(str(FOLDER))


def prepare(monkeypatch, tmp_path):
    c = installer.c
    commands = []
    dropin = tmp_path / "units" / "30-node-red-readiness.conf"
    dropin.parent.mkdir()
    monkeypatch.setattr(installer, "DROPIN", dropin)
    monkeypatch.setattr(c, "secure", lambda *a, **k: None)
    monkeypatch.setattr(c, "digest", lambda p: installer.DAEMON_SHA)
    monkeypatch.setattr(c, "active", lambda s: s != "nodered.service")
    monkeypatch.setattr(c, "flow", lambda: None)
    monkeypatch.setattr(c, "pair_high", lambda: None)
    monkeypatch.setattr(c, "stopped", lambda: commands.append("stopped"))
    monkeypatch.setattr(c, "drain", lambda: commands.append("drain"))
    monkeypatch.setattr(c, "venv_info", lambda: {"rpi-freeze-protect":"1.3.0"})
    monkeypatch.setattr(c, "run", lambda args, **kw: commands.append(args) or "")
    monkeypatch.setattr(installer, "config", lambda: {"FREEZE_PROTECT_WEATHER_SETTINGS_TOKEN":"fixture"})
    monkeypatch.setattr(installer, "status", lambda _: {})
    monkeypatch.setattr(installer, "persistent_stop", lambda: {"enabled":True})
    return commands, dropin


def test_backup_failure_prevents_package_and_dropin_changes(monkeypatch, tmp_path):
    commands, dropin = prepare(monkeypatch, tmp_path)
    def fail(_):
        raise RuntimeError("BACKUP_FAILED")
    monkeypatch.setattr(installer, "archive_backup", fail)
    with pytest.raises(SystemExit):
        installer.install({"source_commit":"fixture"}, tmp_path)
    assert not any(isinstance(c, list) and "pip" in c for c in commands)
    assert not dropin.exists()
    assert commands[-1] == "drain"
    assert not json.loads((tmp_path / "STOP.json").read_text())["install_started"]


def test_existing_dropin_stops_before_service_stop(monkeypatch, tmp_path):
    commands, dropin = prepare(monkeypatch, tmp_path)
    dropin.write_text("preserve")
    with pytest.raises(SystemExit):
        installer.install({"source_commit":"fixture"}, tmp_path)
    assert commands == []
    assert dropin.read_text() == "preserve"


def test_dropin_write_has_public_read_mode_and_exact_readback(monkeypatch, tmp_path):
    destination = tmp_path / "ready.conf"
    monkeypatch.setattr(installer, "DROPIN", destination)
    installer.install_dropin()
    assert destination.read_bytes() == (FOLDER / "30-node-red-readiness.conf").read_bytes()
    assert destination.stat().st_mode & 0o777 == 0o644
    assert list(tmp_path.iterdir()) == [destination]


def test_failed_dropin_write_leaves_hub_stopped(monkeypatch, tmp_path):
    commands, dropin = prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(installer, "archive_backup", lambda _: None)
    monkeypatch.setattr(installer.c, "installed_bytes", lambda _: None)
    monkeypatch.setattr(installer.c, "service_readable", lambda: None)
    values = iter([{"rpi-freeze-protect":"1.3.0"}, {"rpi-freeze-protect":"1.3.1"}])
    monkeypatch.setattr(installer.c, "venv_info", lambda: next(values))
    monkeypatch.setattr(installer.c, "replace_file", lambda *a: None)
    def fail():
        raise RuntimeError("DISK_ERROR")
    monkeypatch.setattr(installer, "install_dropin", fail)
    with pytest.raises(SystemExit):
        installer.install({"source_commit":"fixture"}, tmp_path)
    assert ["systemctl", "start", installer.c.HUB] not in commands
    assert commands[-1] == "drain"
    assert not dropin.exists()
    assert json.loads((tmp_path / "readiness-dropin-before.json").read_text()) == {"present":False}


@pytest.mark.parametrize("version", ["1.1.0", "1.3.1", "2.0.0", None])
def test_other_baseline_versions_stop_before_mutation(monkeypatch, tmp_path, version):
    commands, dropin = prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(installer.c, "venv_info", lambda: {"rpi-freeze-protect":version})
    with pytest.raises(SystemExit):
        installer.install({"source_commit":"fixture"}, tmp_path)
    assert ["systemctl", "stop", installer.c.HUB] not in commands
    assert not dropin.exists()
