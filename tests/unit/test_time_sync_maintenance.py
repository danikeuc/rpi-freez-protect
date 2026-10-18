import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "deployment/time-sync"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install = load("install_time_sync")
ready = load("time_ready")


def test_mode_change_preserves_other_bytes():
    before = b"# note\r\nCONFIG_NTP_MODE=2\r\nPRIVATE_SETTING=keep\r\n"
    assert install.updated_config(before) == before.replace(b"MODE=2", b"MODE=4")


@pytest.mark.parametrize(
    "data",
    [
        b"CONFIG_NTP_MODE=4\n",
        b"# CONFIG_NTP_MODE=2\n",
        b"CONFIG_NTP_MODE=2\nCONFIG_NTP_MODE=2\n",
        b"CONFIG_NTP_MODE=2\nCONFIG_NTP_MODE=0\n",
    ],
)
def test_config_must_have_single_expected_mode(data):
    with pytest.raises(RuntimeError):
        install.updated_config(data)


def test_time_gate_waits_and_fails_without_sync():
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds

    assert ready.wait_ready(lambda: False, lambda: clock[0], sleep, timeout=3) is False
    assert clock[0] == 3


def test_time_gate_requires_repeated_confirmation():
    values = iter([True, False, True, True, True])
    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds

    assert (
        ready.wait_ready(lambda: next(values), lambda: clock[0], sleep, timeout=10)
        is True
    )
    assert clock[0] >= 3


class Ops:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __getattr__(self, name):
        def action():
            self.calls.append(name)
            if name == self.fail:
                raise RuntimeError(name)

        return action


def test_sync_happens_only_while_controllers_stopped():
    ops = Ops()
    install.transition(ops)
    assert ops.calls == [
        "preflight",
        "backup",
        "inhibit",
        "stop",
        "verify_stopped",
        "apply",
        "synchronize",
        "verify_durable",
        "start",
        "verify_after",
    ]


@pytest.mark.parametrize(
    "failure",
    [
        "preflight",
        "backup",
        "inhibit",
        "stop",
        "verify_stopped",
        "apply",
        "synchronize",
        "verify_durable",
    ],
)
def test_failure_never_automatically_starts_or_rolls_back(failure):
    ops = Ops(failure)
    with pytest.raises(RuntimeError):
        install.transition(ops)
    assert "start" not in ops.calls and "rollback" not in ops.calls


def test_gate_probe_requires_active_service_and_synchronized_kernel(monkeypatch):
    from types import SimpleNamespace

    for active, synced, expected in (
        (b"inactive", b"yes", False),
        (b"active", b"no", False),
        (b"active", b"yes", True),
    ):

        def run(args, active=active, synced=synced, **kwargs):
            return SimpleNamespace(
                returncode=0, stdout=active if "is-active" in args else synced
            )

        monkeypatch.setattr(ready.subprocess, "run", run)
        assert ready.synchronized() is expected


def test_install_apply_preserves_existing_config_and_adds_only_named_files(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    config = tmp_path / "dietpi.txt"
    before = (
        b"CONFIG_NTP_MODE=2\nCONFIG_NTP_MIRROR=private-local-value\nOTHER=untouched\n"
    )
    config.write_bytes(before)
    monkeypatch.setattr(install, "CONFIG", config)
    dest = {k: tmp_path / "target" / k for k in install.DESTINATIONS}
    monkeypatch.setattr(install, "DESTINATIONS", dest)
    package = tmp_path / "package"
    package.mkdir()
    for name in ("time_ready.py", "time-ready.service", "35-time-ready.conf"):
        (package / name).write_text("content:" + name)
    evidence = tmp_path / "backup"
    evidence.mkdir()

    def private(p, b):
        with p.open("xb") as stream:
            stream.write(b)

    host = object.__new__(install.Host)
    host.package, host.evidence = package, evidence
    host.before, host.after = before, install.updated_config(before)
    host.s = SimpleNamespace(secure=lambda p: None, private=private)
    host.diag = SimpleNamespace(
        replace_source=lambda source, target: target.write_bytes(source.read_bytes())
    )
    host.record = lambda *args: None
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return install.SERVICE if "show" in args else ""

    host.run = run
    host.apply()
    assert config.read_bytes() == before.replace(b"MODE=2", b"MODE=4")
    assert all(p.exists() for p in dest.values())
    assert not any("start" in call or "stop" in call for call in calls)


def test_apply_rejects_configuration_drift_before_writing(tmp_path, monkeypatch):
    config = tmp_path / "dietpi.txt"
    config.write_bytes(b"CONFIG_NTP_MODE=0\n")
    monkeypatch.setattr(install, "CONFIG", config)
    host = object.__new__(install.Host)
    host.before = b"CONFIG_NTP_MODE=2\n"
    with pytest.raises(RuntimeError, match="CONFIG_CHANGED"):
        host.apply()
    assert config.read_bytes() == b"CONFIG_NTP_MODE=0\n"
