import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "followup",
    Path(__file__).resolve().parents[2]
    / "deployment/diagnostics/clock_startup_followup.py",
)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def entry(wall, mono, message="secret token not exported", boot="a" * 32):
    return json.dumps(
        {
            "__REALTIME_TIMESTAMP": str(wall),
            "__MONOTONIC_TIMESTAMP": str(mono),
            "_BOOT_ID": boot,
            "MESSAGE": message,
        }
    ).encode()


def test_clock_jump_uses_same_boot_monotonic_and_omits_raw_message():
    raw = b"\n".join(
        [
            entry(100_000_000, 1_000_000),
            entry(151_000_000, 2_000_000, "Time has been changed secret=abc"),
        ]
    )
    result = audit.journal_evidence(raw)
    assert result["clock_candidates"][0]["wall_minus_monotonic_seconds"] == 50
    assert result["clock_candidates"][0]["sample_gap_seconds"] == 1
    assert result["events"][0]["categories"] == ["clock_change"]
    assert "secret" not in str(result) and "abc" not in str(result)


def test_clock_does_not_compare_across_boot_or_reversed_monotonic():
    raw = b"\n".join(
        [
            entry(100_000_000, 9_000_000),
            entry(151_000_000, 1_000_000),
            entry(201_000_000, 2_000_000, boot="b" * 32),
        ]
    )
    assert audit.journal_evidence(raw)["clock_candidates"] == []


def test_light_numeric_diagnostic_and_node_versions():
    raw = b"\n".join(
        [
            entry(
                100,
                100,
                "light clock discontinuity wall_delta_s=-12.5 monotonic_delta_s=0.2",
            ),
            entry(200, 200, "18 Oct - [info] Node.js  version: v22.20.0"),
            entry(300, 300, "Node-RED version: v5.0.7"),
        ]
    )
    result = audit.journal_evidence(raw)
    assert result["events"][0]["light_wall_delta_s"] == -12.5
    assert [r["version"] for r in result["versions_from_logs"]] == [
        "v22.20.0",
        "v5.0.7",
    ]


def test_corrupt_and_nonfinite_journal_are_bounded():
    assert audit.journal_evidence(b"not json\n[]")["entries_parsed"] == 0
    result = audit.journal_evidence(
        entry(
            100, 100, "light clock discontinuity wall_delta_s=1e999 monotonic_delta_s=1"
        )
    )
    assert "light_wall_delta_s" not in result["events"][0]


def test_package_metadata_does_not_export_repository_credentials():
    assert audit.held_packages(b"linux-image-rpi-v8\thold\ncurl\tinstall\n") == [
        "linux-image-rpi-v8"
    ]
    result = audit.upgrade_candidates(
        b"linux-image-rpi-v8/private-secret 1:6.18.50-1 arm64 [upgradable from: 1:6.18.39-1]\n"
    )
    assert result == [{"package": "linux-image-rpi-v8", "candidate": "1:6.18.50-1"}]


def test_package_probe_only_simulates_and_reports_incomplete(monkeypatch):
    calls, rows = [], []

    def command(args, **kwargs):
        calls.append(args)
        return {"exit": -9, "limit": "TIMEOUT"}, b""

    monkeypatch.setattr(audit, "command", command)
    monkeypatch.setattr(
        audit, "emit", lambda section, **data: rows.append((section, data))
    )
    audit.packages()
    assert calls == [
        ["dpkg", "--get-selections"],
        ["apt", "list", "--upgradable"],
        ["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"],
    ]
    assert rows[-1][1]["unplanned_candidates"] is None
