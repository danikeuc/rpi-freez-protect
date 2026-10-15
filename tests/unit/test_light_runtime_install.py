"""Offline installer safety gates; no hardware or network access."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deployment/lighting/install/install_light.py"


@pytest.fixture
def installer():
    assert SCRIPT.is_file(), "root-console lighting installer is missing"
    spec = importlib.util.spec_from_file_location("test_light_installer", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample(phase, light=1):
    return {"phase": phase, "pins": {
        "20": {"level": 1, "function": 1},
        "26": {"level": 1, "function": 1},
        "21": {"level": light, "function": 1},
    }}


def evidence():
    receipt = {"result": "LIGHT_LEVEL_MISMATCH", "attempted_gpio21": True,
               "final_off_readback": True, "automation_enabled": False,
               "physical_acceptance": "NOT_VERIFIED"}
    rows = [sample("startup_off"), sample("on", 0), sample("command_off"),
            sample("normal_release"), sample("startup_off"),
            sample("on_before_crash", 0), sample("crash_release", 0),
            sample("final_owned_off"), sample("final_released_off")]
    return receipt, rows


def test_accepts_only_documented_crash_release_exception(installer):
    receipt, rows = evidence()
    installer.validate_bench(receipt, rows)
    assert receipt["result"] == "LIGHT_LEVEL_MISMATCH"


@pytest.mark.parametrize("change", ["pair", "early", "final", "missing", "pass", "direction"])
def test_rejects_unsafe_or_incomplete_bench(installer, change):
    receipt, rows = evidence()
    if change == "pair":
        rows[3]["pins"]["26"]["level"] = 0
    elif change == "early":
        rows[0]["pins"]["21"]["level"] = 0
    elif change == "final":
        receipt["final_off_readback"] = False
    elif change == "missing":
        rows.pop()
    elif change == "pass":
        receipt["result"] = "PASS"
    else:
        rows[1]["pins"]["21"]["function"] = 0
    with pytest.raises(RuntimeError):
        installer.validate_bench(receipt, rows)


def test_status_uses_real_status_fields(installer):
    value = {"capability": "independent_light_v1", "mode": "AUTO",
             "desired_on": False, "gpio_on": False, "health": "OK",
             "remaining_seconds": 0, "manual_remaining_seconds": 0}
    installer.validate_light_status(value)
    for key, bad in [("gpio_on", None), ("desired_on", True), ("health", "FAULT"),
                     ("mode", "MANUAL_ON"), ("remaining_seconds", True)]:
        with pytest.raises(RuntimeError):
            installer.validate_light_status({**value, key: bad})


def test_manifest_rejects_extra_traversal_missing_and_wrong_hash(installer, tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "secure", lambda path: None)
    names = set(installer.FIXED_FILES) | {"wheelhouse/light-1.0.0-py3-none-any.whl"}
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("payload")
    manifest = {name: installer.digest(tmp_path / name) for name in names}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    installer.verify_package(tmp_path, installer.digest(path))
    for bad in [{**manifest, "../escape": "a"*64},
                {**manifest, "extra.py": "a"*64},
                {name: value for name, value in manifest.items() if name != "operator_checks.py"},
                {**manifest, "operator_checks.py": "0"*64}]:
        path.write_text(json.dumps(bad))
        with pytest.raises(RuntimeError):
            installer.verify_package(tmp_path, installer.digest(path))


def test_manifest_rejects_symlink_even_with_matching_bytes(installer, tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "secure", lambda path: None)
    for name in installer.FIXED_FILES:
        (tmp_path / name).write_text("payload")
    (tmp_path / "wheelhouse").mkdir()
    (tmp_path / "wheelhouse/a.whl").write_text("wheel")
    (tmp_path / "README").unlink()
    (tmp_path / "README").symlink_to("operator_checks.py")
    files = set(installer.FIXED_FILES) | {"wheelhouse/a.whl"}
    (tmp_path / "manifest.json").write_text(json.dumps({
        name: installer.digest(tmp_path / name) for name in files}))
    with pytest.raises(RuntimeError):
        installer.verify_package(tmp_path, installer.digest(tmp_path / "manifest.json"))


def test_cleanup_never_claims_off_without_readback_and_only_stops_new_units(installer):
    class Checks:
        def __init__(self):
            self.commands = []
        def run(self, args, **kwargs):
            self.commands.append(args)
            return ""
        def pair_high(self):
            raise RuntimeError("failed")
    checks = Checks()
    assert installer.cleanup(checks, started=True) is False
    assert checks.commands[0] == [
        "systemctl", "stop", "light-controller.service", "light-gpio.service"]
    assert all("freeze-protect.service" not in command for command in checks.commands)
    checks.commands.clear()
    assert installer.cleanup(checks, started=False) is False
    assert checks.commands == []


def setup_run(installer, tmp_path, monkeypatch, *, failure=None):
    from types import SimpleNamespace
    events = []
    saved = {}
    def run(args, **kwargs):
        events.append(tuple(args))
        if failure == tuple(args):
            raise RuntimeError("DO_NOT_LEAK_TOKEN")
        return ""
    checks = SimpleNamespace(run=run, LOG=None,
                             durable=lambda path, data: saved.update({path.name: data}))
    for name, result in (("host_identity", {}), ("verify_package", {}),
                         ("load_checks", checks), ("bench_evidence", tmp_path),
                         ("preserved_files", {}), ("configure", "PRIVATE_DISPLAY_TOKEN")):
        monkeypatch.setattr(installer, name, lambda *a, result=result, **k: result)
    for name in ("fresh_target", "paired_preflight", "backup", "verify_preserved",
                 "private_file", "initial_off", "wait_executor", "light_high", "verify_ingress"):
        monkeypatch.setattr(installer, name, lambda *a, name=name, **k: events.append(name))
    checks.pair_high = lambda: events.append("pair_high")
    monkeypatch.setattr(installer.tempfile, "mkdtemp", lambda **kw: str(tmp_path))
    monkeypatch.setattr(installer.signal, "signal", lambda *args: None)
    monkeypatch.setattr(installer.os, "umask", lambda mask: 0o022)
    monkeypatch.setattr(installer, "NGINX_ENABLED", SimpleNamespace(
        symlink_to=lambda path: events.append("enable_nginx_site")))
    return events, saved


def test_success_starts_only_new_services_and_exports_sanitized_receipt(installer, tmp_path, monkeypatch, capsys):
    events, saved = setup_run(installer, tmp_path, monkeypatch)
    result = installer.main(["--valves-disconnected", "--lamp-disconnected",
                             "--manifest-sha256", "a"*64])
    assert result == 0
    start = ("systemctl", "start", "light-gpio.service")
    controller = ("systemctl", "start", "light-controller.service")
    assert events.index(start) < events.index("wait_executor") < events.index(controller)
    assert events.index("initial_off") < events.index("enable_nginx_site")
    commands = [event for event in events if isinstance(event, tuple)]
    assert [cmd for cmd in commands if cmd[:2] == ("systemctl", "start")] == [start, controller]
    public = capsys.readouterr().out
    assert "PRIVATE_DISPLAY_TOKEN" not in public
    assert json.loads(public)["final_off_readback"] is True
    assert "before-mutation.json" in saved and "before-start.json" in saved


def test_ambiguous_start_failure_stops_new_units_without_retry(installer, tmp_path, monkeypatch, capsys):
    failure = ("systemctl", "start", "light-gpio.service")
    events, saved = setup_run(installer, tmp_path, monkeypatch, failure=failure)
    assert installer.main(["--valves-disconnected", "--lamp-disconnected",
                           "--manifest-sha256", "a"*64]) == 1
    assert events.count(failure) == 1
    assert ("systemctl", "stop", "light-controller.service", "light-gpio.service") in events
    assert ("systemctl", "start", "light-controller.service") not in events
    assert "DO_NOT_LEAK_TOKEN" not in capsys.readouterr().out
    assert json.loads(saved["receipt.json"])["result"] == "LIGHT_INSTALL_FAILED"


def test_missing_disconnection_flags_causes_no_mutation(installer, tmp_path, monkeypatch, capsys):
    events, saved = setup_run(installer, tmp_path, monkeypatch)
    assert installer.main(["--manifest-sha256", "a"*64]) == 1
    assert events == [] and saved == {}
    assert json.loads(capsys.readouterr().out)["final_off_readback"] is False


def test_manifest_duplicate_keys_rejected(installer):
    with pytest.raises(RuntimeError, match="DUPLICATE_JSON_KEY"):
        json.loads('{"a":1,"a":2}', object_pairs_hook=installer.unique_keys)


def test_provisioning_is_offline_private_separate_and_camera_only(installer, tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    package = tmp_path / "package"
    package.mkdir()
    evidence_dir = tmp_path / "evidence"
    (evidence_dir / "backup").mkdir(parents=True)
    for unit in installer.UNITS:
        (package / unit).write_text("unit")
    (package / "wait_executor.py").write_text("readiness helper")
    constants = {"ROOT": tmp_path / "opt", "CONFIG": tmp_path / "etc",
                 "STATE": tmp_path / "state", "UNIT_DIR": tmp_path / "units"}
    constants["UNIT_DIR"].mkdir()
    for key, value in constants.items():
        monkeypatch.setattr(installer, key, value)
    uid, gid = os.getuid(), os.getgid()
    monkeypatch.setattr(installer.pwd, "getpwnam",
                        lambda name: SimpleNamespace(pw_uid=uid, pw_gid=gid))
    monkeypatch.setattr(installer.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=gid))
    monkeypatch.setattr(installer.os, "getgrouplist", lambda *a: [gid])
    commands, payloads = [], []
    def run(args, **kwargs):
        commands.append(args)
        if "venv" in args:
            (constants["ROOT"] / "venv").mkdir()
        if args[:2] == ["openssl", "req"]:
            Path(args[args.index("-out") + 1]).write_text("PUBLIC_CA")
            Path(args[args.index("-keyout") + 1]).write_text("PRIVATE_KEY")
        if args[:2] == ["openssl", "pkeyutl"]:
            Path(args[args.index("-out") + 1]).write_bytes(bytes(512))
            payloads.append(json.loads(kwargs["input_data"]))
        return ""
    previous_umask = os.umask(0o077)
    try:
        token = installer.configure(SimpleNamespace(run=run), package, evidence_dir)
    finally:
        os.umask(previous_umask)
    assert constants["ROOT"].stat().st_mode & 0o777 == 0o755
    assert (constants["ROOT"] / "venv").stat().st_mode & 0o777 == 0o755
    helper = constants["ROOT"] / "wait_executor.py"
    assert helper.read_text() == "readiness helper"
    assert helper.stat().st_mode & 0o777 == 0o644
    assert "wait_executor.py" in installer.FIXED_FILES
    env = constants["CONFIG"] / "controller.env"
    values = dict(line.split("=", 1) for line in env.read_text().splitlines())
    assert env.stat().st_mode & 0o777 == 0o600
    tokens = [values["LIGHT_" + role + "_TOKEN"] for role in ("DISPLAY", "CAMERA", "SETTINGS")]
    assert len(set(tokens)) == 3 and all(len(value) == 64 for value in tokens)
    assert token == values["LIGHT_DISPLAY_TOKEN"]
    assert payloads == [{"camera_token": values["LIGHT_CAMERA_TOKEN"],
                         "endpoint": installer.ENDPOINT,
                         "ca_sha256": installer.digest(evidence_dir / "backup/provisioning/server.crt")}]
    pip = next(command for command in commands if "pip" in command)
    assert all(flag in pip for flag in ("--isolated", "--no-index", "--require-hashes",
                                        "--only-binary=:all:"))
    assert not any("usermod" in command for command in commands)
    assert not any(token in str(commands) for token in tokens)
    assert "TOKEN" not in (constants["CONFIG"] / "executor.env").read_text()


def test_receipt_write_failure_stops_new_services(installer, tmp_path, monkeypatch, capsys):
    events, _ = setup_run(installer, tmp_path, monkeypatch)
    original = installer.checkpoint
    def checkpoint(c, evidence, name, value):
        if name == "receipt":
            raise OSError("DO_NOT_LEAK_STORAGE")
        original(c, evidence, name, value)
    monkeypatch.setattr(installer, "checkpoint", checkpoint)
    assert installer.main(["--valves-disconnected", "--lamp-disconnected",
                           "--manifest-sha256", "a"*64]) == 1
    assert ("systemctl", "stop", "light-controller.service", "light-gpio.service") in events
    assert "DO_NOT_LEAK_STORAGE" not in capsys.readouterr().out


def test_tls_acceptance_uses_pinned_ca_and_never_submits_authenticated_event(installer, monkeypatch):
    import urllib.error
    from types import SimpleNamespace
    calls = []
    ca_paths = []
    monkeypatch.setattr(installer.ssl, "create_default_context",
                        lambda **kwargs: ca_paths.append(kwargs["cafile"]) or object())
    monkeypatch.setattr(installer.urllib.request, "HTTPSHandler", lambda **kw: object())
    def open_request(request, **kwargs):
        calls.append(request)
        status = 401 if request.method == "POST" else (405 if request.full_url == installer.ENDPOINT else 404)
        raise urllib.error.HTTPError(request.full_url, status, "expected", {}, None)
    monkeypatch.setattr(installer.urllib.request, "build_opener",
                        lambda *a: SimpleNamespace(open=open_request))
    installer.verify_ingress(SimpleNamespace(NoRedirect=lambda: object()))
    assert ca_paths == [str(installer.CONFIG / "tls/server.crt")]
    assert [request.method for request in calls] == ["POST", "GET", "GET"]
    assert all(not request.has_header("Authorization") for request in calls)
    assert calls[0].data == b"{}"


def test_masked_units_accept_only_canonical_dev_null_target(installer):
    import stat
    record = installer.link_target_record(Path("/dev/null"))
    assert record == {"kind": stat.S_IFCHR}
    with pytest.raises(RuntimeError, match="UNTRUSTED_PATH"):
        installer.link_target_record(Path("/dev/zero"))
