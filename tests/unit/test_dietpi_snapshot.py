import importlib.util
import json
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "dietpi_snapshot",
    Path(__file__).resolve().parents[2] / "deployment/diagnostics/dietpi_snapshot.py",
)
assert SPEC and SPEC.loader
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)


def test_journal_exports_categories_and_time_without_raw_secrets():
    data = b"\n".join(
        json.dumps(row).encode()
        for row in [
            {
                "MESSAGE": "Out of memory: secret-token=abc",
                "__REALTIME_TIMESTAMP": "200",
            },
            {
                "MESSAGE": "clock discontinuity Authorization Bearer private",
                "__REALTIME_TIMESTAMP": "100",
            },
            {"MESSAGE": "ordinary password: private", "__REALTIME_TIMESTAMP": "300"},
        ]
    )
    result = snapshot.journal_summary(data)
    assert result["categories"] == {"oom": 1, "clock_change": 1}
    assert result["first_us"]["clock_change"] == 100
    assert "secret" not in str(result) and "private" not in str(result)


def test_unstructured_or_binary_journal_is_not_echoed():
    result = snapshot.journal_summary(
        b"invalid secret\n[]\n" + json.dumps({"MESSAGE": [1, 2, 3]}).encode()
    )
    assert result["malformed"] == 2
    assert result["categories"] == {}


def test_service_properties_never_return_environment_or_unexpected_fields():
    result = snapshot.properties(
        b"ActiveState=active\nEnvironment=TOKEN=private\nExecStart=secret command\n",
        {"ActiveState"},
    )
    assert result == {"ActiveState": "active"}


def test_collector_command_has_a_deadline():
    meta, output = snapshot.command(
        [sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.1
    )
    assert meta["limit"] == "TIMEOUT" and output == b""


def test_collector_command_bounds_output():
    meta, output = snapshot.command(
        [sys.executable, "-c", "print('x'*10000)"], limit=100
    )
    assert meta["limit"] == "OUTPUT_LIMIT" and len(output) == 100


def test_missing_command_is_explicit():
    meta, output = snapshot.command(["unavailable-dietpi-test-program"])
    assert meta == {"available": False} and output == b""


def test_timedatectl_requests_properties_separately(monkeypatch, capsys):
    def fake(args, **kwargs):
        if args[0] == "timedatectl":
            assert "--property=NTPSynchronized" in args
            assert "--property=NTP" in args
            assert not any("," in arg for arg in args)
            return {
                "available": True,
                "exit": 0,
            }, b"NTPSynchronized=yes\nNTP=no\nTimezone=Europe/Ljubljana\nLocalRTC=no\n"
        return {"available": False}, b""

    monkeypatch.setattr(snapshot, "command", fake)
    snapshot.services()
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    clock = next(row for row in rows if row["section"] == "clock")
    assert clock["properties"]["NTPSynchronized"] == "yes"
    assert clock["properties"]["NTP"] == "no"
