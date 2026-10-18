import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("light_status", ROOT / "deployment/maintenance-access/maintenance.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def row(phase, level=1, function=1):
    return {"monotonic": 1.0, "phase": phase,
            "pins": {"20": {"level": 1, "function": 1},
                     "21": {"level": level, "function": function},
                     "26": {"level": 1, "function": 1}}}


def receipt():
    return {"result": "LIGHT_LEVEL_MISMATCH", "attempted_gpio21": True,
            "final_off_readback": True, "physical_acceptance": "NOT_VERIFIED",
            "automation_enabled": False, "evidence": "/root/light-gpio21-bench.test"}


def test_level_mismatch_preserves_first_failure_and_final_off():
    rows = [row("startup_off"), row("on", 0), row("command_off"),
            row("normal_release"), row("startup_off"), row("on_before_crash", 0),
            row("crash_release", 0, 0), row("final_owned_off"), row("final_released_off")]
    result = m.summarize_light_bench(receipt(), rows, None)
    assert result["first_failure"]["phase"] == "crash_release"
    assert result["first_failure"]["code"] == "LIGHT_LEVEL_MISMATCH"
    assert result["final_off_readback"] is True
    assert result["phase_summary"][0]["samples"] == 2
    assert result["observation"] == "HISTORICAL_SAMPLES"


@pytest.mark.parametrize("phase,level,function", [
    ("startup_off", 1, 1), ("on", 0, 1), ("command_off", 1, 1),
    ("normal_release", 1, 0), ("on_before_crash", 0, 1),
    ("crash_release", 1, 0), ("final_owned_off", 1, 1),
    ("final_released_off", 1, 0)])
def test_expected_phase(phase, level, function):
    assert m.summarize_light_bench(receipt(), [row(phase, level, function)], None)["first_failure"] is None


def test_paired_mismatch_has_priority():
    sample = row("on", 1)
    sample["pins"]["26"]["level"] = 0
    assert m.summarize_light_bench(receipt(), [sample], None)["first_failure"]["code"] == "PAIRED_DRAIN_CHANGED"


@pytest.mark.parametrize("bad", [True, -1, 2, "secret"])
def test_invalid_pin_values(bad):
    sample = row("startup_off")
    sample["pins"]["21"]["level"] = bad
    with pytest.raises(ValueError):
        m.summarize_light_bench(receipt(), [sample], None)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True, "secret"])
def test_invalid_time(bad):
    sample = row("startup_off")
    sample["monotonic"] = bad
    with pytest.raises(ValueError):
        m.summarize_light_bench(receipt(), [sample], None)


def test_no_unclassified_payload_echo():
    data = receipt()
    data.update(result="secret", physical_acceptance="secret", extra="secret")
    diag = {"error_type": "secret", "message": "secret",
            "frames": [{"file": "/secret", "line": 2}, {"file": "commission_gpio21.py", "line": 299}]}
    result = m.summarize_light_bench(data, [], diag)
    assert "secret" not in json.dumps(result)
    assert result["result"] == "UNCLASSIFIED"
    assert result["frames"] == [{"file": "commission_gpio21.py", "line": 299}]


@pytest.mark.parametrize("key", ["attempted_gpio21", "final_off_readback"])
def test_receipt_bool_not_integer(key):
    data = receipt()
    data[key] = 1
    with pytest.raises(ValueError):
        m.summarize_light_bench(data, [], None)


def test_unknown_phase_and_row_overflow():
    with pytest.raises(ValueError):
        m.summarize_light_bench(receipt(), [row("secret")], None)
    with pytest.raises(ValueError):
        m.summarize_light_bench(receipt(), [row("on", 0)] * 10001, None)


@pytest.fixture
def disk(tmp_path, monkeypatch):
    # Trust only this isolated test tree; production root stays pinned to uid0.
    monkeypatch.setattr(m, "LIGHT_ROOT", tmp_path)
    monkeypatch.setattr(m, "_ROOT_UID", os.getuid())
    # /tmp parents are intentionally writable; root anchor is opened component-wise.
    original = m._trusted_info
    def check(info, directory=False):
        if directory and (info.st_mode & 0o1000 or info.st_uid == 0):
            return
        return original(info, directory)
    monkeypatch.setattr(m, "_trusted_info", check)
    directory = tmp_path / "light-gpio21-bench.test"
    directory.mkdir(mode=0o700)
    marker = tmp_path / "light-gpio21-commissioning.started"
    marker.write_text(str(directory))
    (directory / "receipt.json").write_text(json.dumps({**receipt(), "evidence": str(directory)}))
    (directory / "samples.json").write_text(json.dumps([row("crash_release", 0), row("final_owned_off"), row("final_released_off")]))
    return tmp_path, directory, marker


def test_read_saved_result_no_subprocess(disk, monkeypatch):
    monkeypatch.setattr(m, "run", lambda *a, **k: pytest.fail("subprocess from bench reader"))
    result = m.light_bench_diagnostic()
    assert result["result"] == "LIGHT_LEVEL_MISMATCH"
    assert result["first_failure"]["phase"] == "crash_release"


def test_missing_marker_not_requested(disk):
    disk[2].unlink()
    assert m.light_bench_diagnostic() == {"code": "NOT_REQUESTED"}


def test_marker_without_receipt_incomplete(disk):
    (disk[1] / "receipt.json").unlink()
    assert m.light_bench_diagnostic() == {"code": "INCOMPLETE"}


@pytest.mark.parametrize("member", ["receipt.json", "samples.json"])
def test_symlink_and_fifo_rejected(disk, member):
    target = disk[1] / member
    target.unlink()
    target.symlink_to("/etc/passwd")
    assert m.light_bench_diagnostic()["code"] == "UNAVAILABLE_OR_INVALID"
    target.unlink()
    os.mkfifo(target)
    assert m.light_bench_diagnostic()["code"] == "UNAVAILABLE_OR_INVALID"


def test_marker_escape_and_unsafe_mode(disk):
    disk[2].write_text("/etc")
    assert m.light_bench_diagnostic()["code"] == "UNAVAILABLE_OR_INVALID"
    disk[2].write_text(str(disk[1]))
    disk[2].chmod(0o666)
    assert m.light_bench_diagnostic()["code"] == "UNAVAILABLE_OR_INVALID"


def test_oversize_and_malformed(disk):
    target = disk[1] / "receipt.json"
    target.write_bytes(b"x" * 32769)
    assert m.light_bench_diagnostic()["code"] == "UNAVAILABLE_OR_INVALID"
    target.write_text('{"password":"secret"}')
    result = m.light_bench_diagnostic()
    assert result["code"] == "UNAVAILABLE_OR_INVALID"
    assert "secret" not in json.dumps(result)


def test_invalid_section_preserves_existing_status(disk, monkeypatch):
    disk[2].write_text("/etc")
    monkeypatch.setattr(m, "phase_status", lambda phase: {})
    monkeypatch.setattr(m, "recovery_diagnostic", lambda *a: {})
    class Result:
        stdout = b"ActiveState=active"
    monkeypatch.setattr(m, "run", lambda *a, **k: Result())
    monkeypatch.setattr(m, "ARTIFACTS", ())
    result = m.diagnostic()
    assert result["access_version"] == 1
    assert result["units"]
    assert result["light_gpio21_bench"]["code"] == "UNAVAILABLE_OR_INVALID"

def test_complete_pass_and_partial_not_accepted():
    data = {**receipt(), "result": "GPIO21_DISCONNECTED_DRIVER_PASS"}
    rows = [row(phase, 0 if phase in ("on", "on_before_crash") else 1) for phase in m.LIGHT_PHASES]
    assert m.summarize_light_bench(data, rows, None)["result"] == data["result"]
    with pytest.raises(ValueError):
        m.summarize_light_bench(data, rows[:-1], None)


def test_nonmonotonic_samples():
    rows = [row("startup_off"), row("on", 0)]
    rows[1]["monotonic"] = 0.5
    with pytest.raises(ValueError):
        m.summarize_light_bench(receipt(), rows, None)


def test_directory_symlink(disk):
    root, directory, marker = disk
    alias = root / "light-gpio21-bench.alias"
    alias.symlink_to(directory, target_is_directory=True)
    marker.write_text(str(alias))
    assert m.light_bench_diagnostic()["code"] == "UNAVAILABLE_OR_INVALID"


def test_changed_snapshot_rejected(disk, monkeypatch):
    read = m._light_read
    count = 0
    def changing(fd, name, limit):
        nonlocal count
        value = read(fd, name, limit)
        if name == "samples.json":
            count += 1
            if count == 2:
                return b"[]"
        return value
    monkeypatch.setattr(m, "_light_read", changing)
    assert m.light_bench_diagnostic()["code"] == "UNAVAILABLE_OR_INVALID"


def test_strict_trusted_info():
    import stat
    from types import SimpleNamespace
    for info in (
        SimpleNamespace(st_uid=999999, st_mode=stat.S_IFREG | 0o600),
        SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o666),
        SimpleNamespace(st_uid=0, st_mode=stat.S_IFIFO | 0o600),
    ):
        with pytest.raises(ValueError):
            m._trusted_info(info)
