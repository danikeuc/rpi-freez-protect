import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[2] / "deployment/lighting/commission_gpio21.py"
spec = importlib.util.spec_from_file_location("commission_gpio21", PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def sample(levels=(1, 1, 1), functions=(1, 1, 1)):
    pins = (20, 21, 26)
    return {
        str(pin): {"level": v, "function": f}
        for pin, v, f in zip(pins, levels, functions, strict=True)
    }


def test_readback_accepts_only_paired_high_outputs():
    m.check_sample(sample(), 1)
    m.check_sample(sample((1, 0, 1)), 0)
    m.check_sample(sample(functions=(1, 0, 1)), 1, released=True)
    for bad in [
        sample((0, 1, 1)),
        sample((1, 1, 0)),
        sample((0, 1, 0)),
        sample(functions=(0, 1, 1)),
        sample((1, 0, 1)),
    ]:
        with pytest.raises(RuntimeError):
            m.check_sample(bad, 1)


def test_read_only_register_decode():
    word = (1 << 20) | (1 << 26)
    fsel = 1 | (1 << 3) | (1 << 18)
    assert m.decode(fsel, word) == sample((1, 0, 1))


def test_require_acknowledges_both_disconnected():
    with pytest.raises(RuntimeError, match="BOTH_LOADS"):
        m.approval(False, True)
    with pytest.raises(RuntimeError, match="BOTH_LOADS"):
        m.approval(True, False)
    m.approval(True, True)


def test_worker_only_owns_21_and_finishes_off():
    trace = []

    class Request:
        def set_value(self, pin, value):
            trace.append((pin, value))

        def get_value(self, pin):
            return trace[-1][1] if trace else 0

        def release(self):
            trace.append("release")

    class Driver:
        def request_lines(self, chip, consumer, config):
            assert chip == "/dev/gpiochip0"
            assert list(config) == [21]
            assert config[21]["output_value"] == 0
            assert config[21]["active_low"] is True
            assert config[21]["direction"] == 1
            return Request()

        @staticmethod
        def LineSettings(**kw):
            return kw

    line = SimpleNamespace(
        Direction=SimpleNamespace(OUTPUT=1), Value=SimpleNamespace(ACTIVE=1, INACTIVE=0)
    )
    acks = []
    m.worker_session(Driver(), line, iter(["on", "off", "close"]).__next__, acks.append)
    assert acks == ["off", "on", "off"]
    assert trace == [(21, 1), (21, 0), (21, 0), "release"]


def test_worker_input_failure_still_turns_off():
    class Request:
        def set_value(self, pin, value):
            assert pin == 21
            calls.append(value)

        def get_value(self, pin):
            return 0

        def release(self):
            calls.append("released")

    calls = []
    driver = SimpleNamespace(
        request_lines=lambda *a, **kw: Request(), LineSettings=lambda **kw: kw
    )
    line = SimpleNamespace(
        Direction=SimpleNamespace(OUTPUT=1), Value=SimpleNamespace(ACTIVE=1, INACTIVE=0)
    )

    def broken():
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        m.worker_session(driver, line, broken, lambda ack: None)
    assert calls == [0, "released"]


@pytest.mark.parametrize("scenario", ["pass", "bench_fail", "off_fail", "marker_fail"])
def test_main_durable_gate_and_cleanup(tmp_path, monkeypatch, capsys, scenario):
    import json
    import os
    import stat

    phases = []
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    checks_path = PATH.parents[1] / "paired-gpio-migration/operator_checks.py"
    cspec = importlib.util.spec_from_file_location("bench_checks_test", checks_path)
    checks = importlib.util.module_from_spec(cspec)
    cspec.loader.exec_module(checks)
    monkeypatch.setattr(m, "checks", lambda: checks)
    monkeypatch.setattr(m, "secure", lambda _: None)
    monkeypatch.setattr(m, "preflight", lambda _: None)
    monkeypatch.setattr(m, "LOCK", tmp_path / "started")
    monkeypatch.setattr(m.tempfile, "mkdtemp", lambda **kw: str(evidence))
    monkeypatch.setattr(
        sys, "argv", ["bench", "--valves-disconnected", "--lamp-disconnected"]
    )

    class Sampler:
        def __init__(self):
            self.rows = []

        def close(self):
            phases.append("closed")

    monkeypatch.setattr(m, "Sampler", Sampler)
    sync = os.fsync

    def fsync(fd):
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        phases.append("sync_dir" if directory else "sync_file")
        if directory and scenario == "marker_fail":
            raise OSError("test directory sync failure")
        sync(fd)

    monkeypatch.setattr(os, "fsync", fsync)

    def bench(sampler):
        phases.append("bench")
        if scenario == "bench_fail":
            raise RuntimeError("CRASH_RELEASE_FAILED")

    def off(sampler):
        phases.append("off")
        if scenario == "off_fail":
            raise RuntimeError("OFF_FAILED")

    monkeypatch.setattr(m, "bench", bench)
    monkeypatch.setattr(m, "restore_off", off)
    previous_umask = os.umask(0o077)
    try:
        result = m.main()
    finally:
        os.umask(previous_umask)
    receipt = json.loads(capsys.readouterr().out)
    assert phases[:2] == ["sync_file", "sync_dir"]
    if scenario == "marker_fail":
        assert "bench" not in phases
        assert receipt["attempted_gpio21"] is False
    else:
        assert phases[2:4] == ["bench", "off"]
    assert receipt["final_off_readback"] is (scenario in {"pass", "bench_fail"})
    assert result == (0 if scenario == "pass" else 1)
    if scenario == "bench_fail":
        assert receipt["result"] == "CRASH_RELEASE_FAILED"
