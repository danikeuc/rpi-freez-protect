import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "startup_audit",
    Path(__file__).resolve().parents[2] / "deployment/diagnostics/startup_software.py",
)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_upgrade_summary_omits_repository_urls_and_only_exports_versions():
    raw = b"Inst openssl [3.5.1-1] (3.5.2-1 Debian-Security:13/stable-security [arm64])\nRemv old-package [1.0]\nConf openssl (3.5.2-1 private-token-URL)\n1 upgraded, 0 newly installed, 1 to remove and 0 not upgraded.\n"
    result = audit.simulation(raw)
    assert result["counts"] == {"Inst": 1, "Remv": 1, "Conf": 1}
    assert result["changes"][0]["candidate"] == "3.5.2-1"
    assert result["changes"][0]["security_origin_hint"] is True
    assert "private-token" not in str(result)


def test_package_inventory_counts_installed_but_filters_other_states():
    result = audit.packages(
        b"nodejs\t22.1.0\tinstalled\nold\t1\tconfig-files\ncurl\t8.1\tinstalled\n"
    )
    assert result["installed_count"] == 2
    assert result["selected"] == [
        {"name": "nodejs", "version": "22.1.0"},
        {"name": "curl", "version": "8.1"},
    ]


def test_apt_command_is_simulation_and_never_update_or_upgrade_mutation(monkeypatch):
    calls = []

    def fake(args, **kwargs):
        calls.append(args)
        return {"available": False}, b""

    monkeypatch.setattr(audit, "command", fake)
    monkeypatch.setattr(audit, "emit", lambda *args, **kwargs: None)
    audit.software()
    apt = [args for args in calls if args[0] == "apt-get"]
    assert apt == [["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"]]
    assert not any("update" in args or "install" in args for args in calls)


def test_startup_does_not_export_exec_start_credentials(monkeypatch):
    rows = []

    def fake(args, **kwargs):
        return (
            {"available": True},
            b"ExecStartPre=/secret/path --token=private\nAfter=node-red.service freeze-protect-pair-gpio.service\nActiveState=active\n",
        )

    monkeypatch.setattr(audit, "command", fake)
    monkeypatch.setattr(
        audit, "emit", lambda section, **data: rows.append((section, data))
    )
    audit.startup()
    unit = next(data for section, data in rows if section == "startup_unit")
    assert unit["properties"]["pre_start_check_present"] is True
    assert "private" not in str(rows) and "/secret" not in str(rows)
    assert "node-red.service" in unit["properties"]["After"]
