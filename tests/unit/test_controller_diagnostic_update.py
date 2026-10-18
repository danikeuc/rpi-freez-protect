import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("controller_update", ROOT / "deployment/maintenance-access/update_controller_diagnostics.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def public_status(target):
    # Existing contract fields, plus the newly proposed helper hash.
    return {"access_version": 1,
            "package_sha256": "f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513",
            "jobs": [], "recovery": {}, "hub_recovery": {},
            "light_gpio21_bench": {"code": "READ"},
            "controllers": {"diagnostic_version": 1, "actuator_commands": 0, "configuration_writes": 0, "checks": []},
            "units": {name: {} for name in (
                "freeze-protect.service", "freeze-protect-pair-gpio.service",
                "node-red.service", "freeze-protect-maintenance-prepare.service",
                "freeze-protect-maintenance-install.service")},
            "artifacts": {**{name: {} for name in (
                "/etc/systemd/system/freeze-protect.service",
                "/etc/systemd/system/freeze-protect.service.d/30-node-red-readiness.conf",
                "/etc/systemd/system/freeze-protect-pair-gpio.service",
                "/etc/systemd/system/freeze-protect-pair-gpio.service.d/40-paired-gpio.conf",
                "/opt/rpi-freez-protect/deployment/node-red/paired_gpio_daemon.py")},
                str(target): {"sha256": m.sha(target.read_bytes())}}}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    here = tmp_path / "package"
    here.mkdir()
    target = tmp_path / "installed.py"
    target.write_bytes(b"old-helper")
    target.chmod(0o700)
    (here / "maintenance.py").write_bytes(b"x = 1")
    (here / "update_controller_diagnostics.py").write_bytes(b"# installer")
    hashes = {name: m.sha((here / name).read_bytes()) for name in ("maintenance.py", "update_controller_diagnostics.py")}
    (here / "manifest.json").write_text(json.dumps({"files": hashes}))
    lock = tmp_path / "operation.lock"
    lock.touch(mode=0o600)
    model = tmp_path / "model"
    model.write_bytes(b"Raspberry Pi 4 Model B Rev 1.1\0")
    monkeypatch.setattr(m, "HERE", here)
    monkeypatch.setattr(m, "TARGET", target)
    monkeypatch.setattr(m, "LOCK", lock)
    monkeypatch.setattr(m, "MODEL", model)
    monkeypatch.setattr(m, "BACKUP_ROOT", tmp_path)
    monkeypatch.setattr(m, "OLD", m.sha(b"old-helper"))
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    # Trusted fixture tree, not a production bypass.
    monkeypatch.setattr(m, "secure", lambda path: None)
    monkeypatch.setattr(m, "preview", lambda candidate: public_status(target))
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps(public_status(target)).encode())
    monkeypatch.setattr(m.subprocess, "run", run)
    return tmp_path, here, target, calls


def test_success_backup_before_replace(setup, monkeypatch):
    root, here, target, calls = setup
    replace = m.os.replace
    def checked_replace(source, dest):
        backups = list(root.glob("freeze-controller-diagnostics.*"))
        assert len(backups) == 1
        assert (backups[0] / "maintenance-before.py").read_bytes() == b"old-helper"
        assert (backups[0] / "STARTED.json").exists()
        replace(source, dest)
    monkeypatch.setattr(m.os, "replace", checked_replace)
    result = m.install()
    assert result["changed"] is True
    assert target.read_bytes() == (here / "maintenance.py").read_bytes()
    assert target.stat().st_mode & 0o777 == 0o700
    assert len(calls) == 1
    assert calls[0] == ["/usr/local/sbin/freeze-protect-maintenance", "status"]
    assert (Path(result["backup"]) / "SUCCESS.json").exists()


@pytest.mark.parametrize("fault", ["root", "model", "baseline", "candidate", "preview"])
def test_preflight_failure_does_not_replace(setup, monkeypatch, fault):
    _root, here, target, calls = setup
    if fault == "root":
        monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
    elif fault == "model":
        m.MODEL.write_bytes(b"synology")
    elif fault == "baseline":
        target.write_bytes(b"changed")
    elif fault == "candidate":
        (here / "maintenance.py").write_bytes(b"changed")
    else:
        monkeypatch.setattr(m, "preview", lambda path: {})
    before = target.read_bytes()
    with pytest.raises(RuntimeError):
        m.install()
    assert target.read_bytes() == before
    assert calls == []


def test_busy_lock_no_mutation(setup):
    import fcntl
    with m.LOCK.open("r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            m.install()
    assert setup[2].read_bytes() == b"old-helper"


def test_failed_postcheck_records_changed_no_rollback(setup, monkeypatch):
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=b"secret"))
    with pytest.raises(RuntimeError):
        m.install()
    root, here, target, _ = setup
    assert target.read_bytes() == (here / "maintenance.py").read_bytes()
    backup = next(root.glob("freeze-controller-diagnostics.*"))
    assert json.loads((backup / "STOPPED.json").read_text())["changed"] is True
    assert "secret" not in (backup / "STOPPED.json").read_text()


def test_replace_failure_leaves_original(setup, monkeypatch):
    monkeypatch.setattr(m.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("secret")))
    with pytest.raises(OSError):
        m.install()
    assert setup[2].read_bytes() == b"old-helper"
    backup = next(setup[0].glob("freeze-controller-diagnostics.*"))
    assert json.loads((backup / "STOPPED.json").read_text())["changed"] is False


def test_secure_rejects_symlink(tmp_path):
    link = tmp_path / "alias"
    link.symlink_to("/etc/passwd")
    with pytest.raises(RuntimeError):
        m.secure(link)


def test_baseline_changed_during_preview(setup, monkeypatch):
    def preview(path):
        setup[2].write_bytes(b"changed-under-lock")
        return {"access_version": 1, "light_gpio21_bench": {}}
    monkeypatch.setattr(m, "preview", preview)
    with pytest.raises(RuntimeError):
        m.install()
    assert setup[2].read_bytes() == b"changed-under-lock"


def test_candidate_snapshot_is_previewed_and_installed(setup, monkeypatch):
    _root, here, target, _calls = setup
    expected = (here / "maintenance.py").read_bytes()
    def snapshot_preview(candidate):
        assert type(candidate) is bytes
        assert candidate == expected
        (here / "maintenance.py").write_bytes(b"changed-during-preview")
        return public_status(target)
    monkeypatch.setattr(m, "preview", snapshot_preview)
    m.install()
    assert target.read_bytes() == expected


@pytest.mark.parametrize("field", ["package_sha256", "jobs", "recovery", "hub_recovery", "units", "artifacts"])
def test_missing_legacy_field_rejected(setup, monkeypatch, field):
    value = public_status(setup[2])
    del value[field]
    monkeypatch.setattr(m, "preview", lambda candidate: value)
    with pytest.raises(RuntimeError):
        m.install()
    assert setup[2].read_bytes() == b"old-helper"


def test_preview_executes_provided_snapshot_without_path_import():
    value = m.preview(b"def diagnostic(): return {'snapshot': True}")
    assert value == {"snapshot": True}
