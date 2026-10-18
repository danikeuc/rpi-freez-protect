import importlib.util
import json
import stat
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("controller_access", ROOT / "deployment/maintenance-access/maintenance.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
SECRET = "PrivateCredentialMustNeverAppearHere0123456789"

@pytest.fixture
def fixture(monkeypatch):
    class TrustedPath:
        parents = ()
        def __init__(self, path):
            assert path in ("/etc/rpi-freeze-protect/environment", "/etc/independent-light/controller.env")
        def lstat(self):
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o600, st_size=500)
        stat = lstat
        def read_text(self):
            return "FREEZE_PROTECT_ADMIN_TOKEN=" + SECRET + "\nLIGHT_SETTINGS_TOKEN=" + SECRET
    monkeypatch.setattr(m, "Path", TrustedPath)
    calls = []
    bodies = {
        "status": {"health": "FAULT", "mode": "AUTO", "reason": "clock_or_lease_fault",
                   "gpio_on": False, "token": SECRET, "request_id": SECRET},
        "history": {"items": [{"at": "2026-10-18T01:02:03+00:00", "source": "fault",
                               "reason": "clock_or_lease_fault", "token": SECRET}]},
        "events": {"items": [{"occurred_at": "2026-10-18T01:02:03+00:00",
                              "event_type": "actuator_failed", "payload": {"reason": "startup_drain_failed", "token": SECRET}}]},
    }
    class Response:
        status = 200
        def __init__(self, body):
            self.body = json.dumps(body).encode()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, count):
            return self.body[:count]
    class Client:
        def open(self, request, timeout):
            assert timeout == 2
            assert request.get_method() == "GET"
            assert request.full_url.startswith(("http://127.0.0.1:8000/api/v1/", "http://127.0.0.1:8002/api/v1/lights/"))
            calls.append(request)
            key = request.full_url.split("/")[-1].split("?")[0]
            return Response(bodies[key])
    handlers = []
    def opener(*args):
        handlers.extend(args)
        return Client()
    monkeypatch.setattr(urllib.request, "build_opener", opener)
    journal_calls = []
    def journal(args, **kwargs):
        journal_calls.append(args)
        assert args[0] == "/usr/bin/journalctl"
        assert kwargs["timeout"] == 5
        return SimpleNamespace(returncode=0, stdout=json.dumps({"MESSAGE": "clock discontinuity " + SECRET, "__REALTIME_TIMESTAMP": "1792285323000000"}).encode())
    monkeypatch.setattr(m.subprocess, "run", journal)
    return calls, bodies, handlers, journal_calls, TrustedPath


def test_fixed_gets_no_credentials_or_raw_logs(fixture):
    result = m.controller_diagnostic()
    encoded = json.dumps(result)
    assert SECRET not in encoded
    assert result["diagnostic_version"] == 1
    assert result["actuator_commands"] == result["configuration_writes"] == 0
    assert "clock_or_lease_fault" in encoded
    assert "startup_drain_failed" in encoded
    assert '"clock_jump"' in encoded
    assert len(fixture[0]) == 4
    assert len(fixture[3]) == 1
    assert all("127.0.0.1" in r.full_url for r in fixture[0])


def test_unknown_strings_and_invalid_scalars_never_exported(fixture):
    fixture[1]["status"].update(reason=SECRET, mode=SECRET, gpio_on=SECRET, revision=SECRET,
                               at=SECRET, remaining_seconds=2**63)
    fixture[1]["events"]["items"][0]["payload"]["reason"] = SECRET
    encoded = json.dumps(m.controller_diagnostic())
    assert SECRET not in encoded
    assert "UNCLASSIFIED" in encoded
    assert str(2**63) not in encoded


def test_redirect_and_proxy_disabled(fixture):
    m.controller_diagnostic()
    proxy = next(h for h in fixture[2] if isinstance(h, urllib.request.ProxyHandler))
    assert proxy.proxies == {}
    redirect = next(h for h in fixture[2] if isinstance(h, urllib.request.HTTPRedirectHandler))
    with pytest.raises(RuntimeError):
        redirect.redirect_request(None, None, 302, "", {}, "https://example.com")


def test_environment_symlink_rejected_without_http(fixture, monkeypatch):
    monkeypatch.setattr(fixture[4], "lstat", lambda self: SimpleNamespace(st_uid=0, st_mode=stat.S_IFLNK | 0o777))
    result = m.controller_diagnostic()
    assert fixture[0] == []
    assert len([r for r in result["checks"] if r.get("error_type") == "RuntimeError"]) == 2


def test_failure_text_not_exported(fixture, monkeypatch):
    def fail(*args):
        raise urllib.error.URLError(SECRET)
    monkeypatch.setattr(urllib.request, "build_opener", fail)
    result = m.controller_diagnostic()
    assert SECRET not in json.dumps(result)
    assert len([r for r in result["checks"] if r.get("error_type") == "URLError"]) == 2


def test_extra_arguments_still_rejected(monkeypatch):
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.sys, "argv", ["maintenance.py", "status", "/etc/shadow"])
    with pytest.raises(RuntimeError, match="COMMAND_REJECTED"):
        m.main()
