"""First installation from a pinned offline bundle, at the trusted Pi console.

No ON commands, valve commands, remote installation, rollback or automatic retry.
A failed attempt is retained for local review before any subsequent installation.
"""
# ruff: noqa: BLE001, S110
from __future__ import annotations

import argparse
import grp
import hashlib
import importlib.util
import json
import os
import platform
import pwd
import re
import secrets
import signal
import socket
import sqlite3
import ssl
import stat
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

FIXED_FILES = frozenset({
    "install_light.py", "operator_checks.py", "runtime-install.lock",
    "light-controller.service", "light-gpio.service", "light-camera.conf",
    "recipient-public.pem", "README", "wait_executor.py",
})
PAIR_PATH = Path("/opt/rpi-freez-protect/deployment/node-red/paired_gpio_daemon.py")
PAIR_HASH = "ef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f"
PAIR_PYTHON = "/opt/freeze-protect-paired-gpio/venv-2.3.0/bin/python3"
BENCH_MARKER = Path("/root/light-gpio21-commissioning.started")
ATTEMPT = Path("/root/independent-light-install.started")
ROOT = Path("/opt/independent-light")
CONFIG = Path("/etc/independent-light")
STATE = Path("/var/lib/independent-light")
RUNTIME = Path("/run/independent-light")
UNITS = ("light-gpio.service", "light-controller.service")
UNIT_DIR = Path("/etc/systemd/system")
NGINX_AVAILABLE = Path("/etc/nginx/sites-available/light-camera.conf")
NGINX_ENABLED = Path("/etc/nginx/sites-enabled/light-camera.conf")
ACCOUNT = "independent-light"
ENDPOINT = "https://192.168.114.192:8443/api/v1/lights/events/unifi"
SOURCE = "6797d43f03968103e40003f1"


# Exact reviewed diagnostics only; arbitrary exception messages are never public.
SAFE_STOP_CODES = frozenset({
    "BENCH_EVIDENCE_IDENTITY", "BENCH_LEVEL", "BENCH_LIGHT_DIRECTION",
    "BENCH_MARKER_PATH", "BENCH_PAIR_CHANGED", "BENCH_RECEIPT", "BENCH_SAMPLE",
    "BENCH_SAMPLES", "BENCH_SEQUENCE", "BENCH_UNEXPECTED_MISMATCH",
    "BOTH_LOADS_DISCONNECTED_REQUIRED", "CANONICAL_CHIP_REQUIRED",
    "DUPLICATE_JSON_KEY", "EXECUTOR_SERVICE_INACTIVE", "EXECUTOR_SOCKET_IDENTITY",
    "EXECUTOR_STARTUP_TIMEOUT", "EXISTING_BASELINE_CHANGED", "EXISTING_LIGHT_ACCOUNT",
    "EXISTING_LIGHT_UNIT", "GPIO_GROUP_REQUIRED", "GPIO_IDENTITY", "HOST_MODEL",
    "HOST_RUNTIME", "INSTALL_INTERRUPTED", "INVALID_RECORD", "LIGHT_ACCOUNT_GROUPS",
    "LIGHT_HTTP_STATUS", "LIGHT_INITIAL_OFF_REQUIRED", "LIGHT_OFF_READBACK_FAILED",
    "LIGHT_OWNERSHIP", "LIGHT_SERVICE_INACTIVE", "LIGHT_STARTUP_TIMEOUT",
    "LIGHT_STATUS_SIZE", "MANIFEST_PIN_MISMATCH", "MANIFEST_PIN_REQUIRED",
    "PACKAGE_DIRECTORY", "PACKAGE_EXTRA_FILES", "PACKAGE_FILES", "PACKAGE_HASH",
    "PACKAGE_HASH_FORMAT", "PACKAGE_SPECIAL_FILE", "PACKAGE_SYMLINK",
    "PAIRED_BASELINE_CHANGED", "PAIRED_OWNERSHIP", "PAIRED_PID",
    "PAIRED_PROCESS_BASELINE", "PENDING_DAEMON_RELOAD",
    "PREVIOUS_INSTALL_REQUIRES_REVIEW", "RECIPIENT_RSA4096_REQUIRED",
    "ROOT_CONSOLE_REQUIRED", "SERVICES_REQUIRED", "TLS_INGRESS_POLICY",
    "TLS_INGRESS_UNAVAILABLE", "TOKEN_COLLISION", "UNRELATED_FILE_ADDED",
    "UNTRUSTED_DATA_PATH", "UNTRUSTED_LINK", "UNTRUSTED_NULL_DEVICE",
    "UNTRUSTED_PATH", "DB_INTEGRITY", "DB_INVALID", "DEVELOPMENT_MODE",
    "DUPLICATE_ENV_KEY", "DURABLE_STOP_REQUIRED", "ENV_SYNTAX", "ENV_WORLD_READABLE",
    "HTTP_REJECTED", "IDENTITY_INVALID", "IDENTITY_MISMATCH", "INVALID_STATUS",
    "MISSING_DISPLAY_TOKEN", "OVERSIZE_STATUS", "USER_OFF_REQUIRED",
    "WRONG_DB", "WRONG_MODE",
})


def safe_stop_code(error):
    if (type(error) is RuntimeError and len(error.args) == 1
            and type(error.args[0]) is str and error.args[0] in SAFE_STOP_CODES):
        return error.args[0]
    return "LIGHT_INSTALL_FAILED"


def require(value, code):
    if not value:
        raise RuntimeError(code)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def secure(path):
    """Every ancestor must be root controlled; links are never followed."""
    path = Path(path)
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, "UNTRUSTED_PATH")


def read_json(path, limit=8 * 1024 * 1024):
    secure(path)
    require(path.is_file() and path.stat().st_size <= limit, "INVALID_RECORD")
    return json.loads(path.read_bytes(), object_pairs_hook=unique_keys)


def unique_keys(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "DUPLICATE_JSON_KEY")
        value[key] = item
    return value


def verify_package(directory, expected_manifest):
    secure(directory)
    manifest_path = directory / "manifest.json"
    require(re.fullmatch(r"[0-9a-f]{64}", expected_manifest) is not None,
            "MANIFEST_PIN_REQUIRED")
    secure(manifest_path)
    require(digest(manifest_path) == expected_manifest, "MANIFEST_PIN_MISMATCH")
    files = read_json(manifest_path, 1024 * 1024)
    require(isinstance(files, dict) and FIXED_FILES <= files.keys(), "PACKAGE_FILES")
    wheels = set(files) - FIXED_FILES
    require(wheels and all(re.fullmatch(r"wheelhouse/[A-Za-z0-9_.+-]+\.whl", name)
                           for name in wheels), "PACKAGE_FILES")
    actual = set()
    for member in directory.rglob("*"):
        require(not member.is_symlink(), "PACKAGE_SYMLINK")
        if member.is_dir():
            require(member == directory / "wheelhouse", "PACKAGE_DIRECTORY")
        else:
            require(member.is_file(), "PACKAGE_SPECIAL_FILE")
            actual.add(member.relative_to(directory).as_posix())
    require(actual == set(files) | {"manifest.json", "SHA256SUMS"}
            or actual == set(files) | {"manifest.json"}, "PACKAGE_EXTRA_FILES")
    for name, identity in files.items():
        require(isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{64}", identity),
                "PACKAGE_HASH_FORMAT")
        path = directory / name
        secure(path)
        require(path.is_file() and not path.is_symlink() and digest(path) == identity,
                "PACKAGE_HASH")
    return files


def validate_bench(receipt, rows):
    """Accept the documented exception while preserving the original failed result."""
    require(isinstance(receipt, dict)
            and receipt.get("result") == "LIGHT_LEVEL_MISMATCH"
            and receipt.get("attempted_gpio21") is True
            and receipt.get("final_off_readback") is True
            and receipt.get("automation_enabled") is False
            and receipt.get("physical_acceptance") == "NOT_VERIFIED", "BENCH_RECEIPT")
    sequence = ("startup_off", "on", "command_off", "normal_release", "startup_off",
                "on_before_crash", "crash_release", "final_owned_off", "final_released_off")
    require(isinstance(rows, list) and 9 <= len(rows) <= 100000, "BENCH_SAMPLES")
    phases, first_bad = [], None
    for row in rows:
        require(isinstance(row, dict), "BENCH_SAMPLE")
        phase, pins = row.get("phase"), row.get("pins")
        require(phase in sequence and isinstance(pins, dict), "BENCH_SAMPLE")
        if not phases or phases[-1] != phase:
            phases.append(phase)
        require(all(pins.get(str(pin)) == {"level": 1, "function": 1}
                    for pin in (20, 26)), "BENCH_PAIR_CHANGED")
        light = pins.get("21", {})
        allowed = (0, 1) if phase.endswith("release") or phase == "final_released_off" else (1,)
        require(light.get("function") in allowed, "BENCH_LIGHT_DIRECTION")
        expected = 0 if phase in ("on", "on_before_crash") else 1
        require(type(light.get("level")) is int and light["level"] in (0, 1),
                "BENCH_LEVEL")
        if light["level"] != expected:
            first_bad = first_bad or phase
            require(phase == "crash_release", "BENCH_UNEXPECTED_MISMATCH")
    require(tuple(phases) == sequence and first_bad == "crash_release",
            "BENCH_SEQUENCE")


def bench_evidence():
    secure(BENCH_MARKER)
    value = BENCH_MARKER.read_text().strip()
    require(re.fullmatch(r"/root/light-gpio21-bench\.[A-Za-z0-9_]+", value),
            "BENCH_MARKER_PATH")
    directory = Path(value)
    receipt = read_json(directory / "receipt.json")
    require(receipt.get("evidence") == value, "BENCH_EVIDENCE_IDENTITY")
    rows = read_json(directory / "samples.json")
    validate_bench(receipt, rows)
    return directory


def load_checks(directory):
    spec = importlib.util.spec_from_file_location("light_operator_checks",
                                                 directory / "operator_checks.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def show(c, service, key):
    return c.run(["systemctl", "show", service, "--property=" + key, "--value"])


def host_identity():
    require(os.geteuid() == 0, "ROOT_CONSOLE_REQUIRED")
    require(platform.machine() == "aarch64" and sys.version_info[:2] == (3, 13),
            "HOST_RUNTIME")
    require(Path("/proc/device-tree/model").read_bytes().rstrip(b"\0\n")
            == b"Raspberry Pi 4 Model B Rev 1.1", "HOST_MODEL")
    chip = Path("/dev/gpiochip0")
    require(not chip.is_symlink() and stat.S_ISCHR(chip.stat().st_mode),
            "CANONICAL_CHIP_REQUIRED")
    return {"model": "Raspberry Pi 4 Model B Rev 1.1",
            "kernel": platform.release(), "python": platform.python_version(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}


def paired_preflight(c, *, light_active=False):
    secure(PAIR_PATH)
    require(digest(PAIR_PATH) == PAIR_HASH, "PAIRED_BASELINE_CHANGED")
    require(all(c.active(service) for service in c.SERVICES), "SERVICES_REQUIRED")
    require(all(show(c, service, "NeedDaemonReload") == "no"
                for service in c.SERVICES), "PENDING_DAEMON_RELOAD")
    c.status(c.config())
    c.persistent_stop()
    c.pair_high()
    c.flow()
    pid = show(c, c.PAIR, "MainPID")
    require(re.fullmatch(r"[1-9][0-9]*", pid), "PAIRED_PID")
    actual = Path("/proc") / pid / "cmdline"
    require(actual.read_bytes().split(b"\0")[:-1] == [
        PAIR_PYTHON.encode(), b"-I", b"-B", str(PAIR_PATH).encode()],
        "PAIRED_PROCESS_BASELINE")
    # Use the already migrated interpreter only for read-only libgpiod inventory.
    code = """import gpiod,json,importlib.metadata
with gpiod.Chip('/dev/gpiochip0') as chip:
 print(json.dumps({'version':importlib.metadata.version('gpiod'),
 'chip':chip.get_info().name,'lines':{
 str(pin):{'used':chip.get_line_info(pin).used,
 'consumer':chip.get_line_info(pin).consumer,
 'name':chip.get_line_info(pin).name} for pin in (20,21,26)}}))
"""
    secure(Path(PAIR_PYTHON).resolve())
    value = json.loads(c.run([PAIR_PYTHON, "-I", "-B", "-c", code]))
    require(value.get("version") == "2.3.0" and value.get("chip") == "gpiochip0",
            "GPIO_IDENTITY")
    for pin in (20, 26):
        require(value["lines"][str(pin)] == {
            "used": True, "consumer": "freeze-protect-pair", "name": "GPIO" + str(pin)},
            "PAIRED_OWNERSHIP")
    light = value["lines"]["21"]
    require(light["name"] == "GPIO21" and light["used"] is light_active
            and (not light_active or light["consumer"] == "independent-light-gpio21"),
            "LIGHT_OWNERSHIP")


def fresh_target(c):
    paths = (ROOT, CONFIG, STATE, RUNTIME, ATTEMPT, NGINX_AVAILABLE, NGINX_ENABLED)
    for path in paths:
        secure(path.parent)
        require(not os.path.lexists(path), "PREVIOUS_INSTALL_REQUIRES_REVIEW")
    for unit in UNITS:
        require(show(c, unit, "LoadState") == "not-found"
                and show(c, unit, "MainPID") in ("0", ""), "EXISTING_LIGHT_UNIT")
        for directory in (UNIT_DIR, Path("/run/systemd/system"), Path("/usr/lib/systemd/system"),
                          Path("/lib/systemd/system")):
            for name in (unit, unit + ".d"):
                require(not os.path.lexists(directory / name), "EXISTING_LIGHT_UNIT")
    for lookup in (pwd.getpwnam, grp.getgrnam):
        try:
            lookup(ACCOUNT)
        except KeyError:
            pass
        else:
            raise RuntimeError("EXISTING_LIGHT_ACCOUNT")
    require(grp.getgrnam("gpio").gr_gid >= 0, "GPIO_GROUP_REQUIRED")
    for port in (8002, 8443):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("0.0.0.0", port))
    c.run(["nginx", "-t"])


def link_target_record(target):
    """Masked units use the one conventional writable device, never read it."""
    if target == Path("/dev/null"):
        secure(target.parent)
        info = target.lstat()
        require(stat.S_ISCHR(info.st_mode) and info.st_uid == 0
                and info.st_rdev == os.makedev(1, 3), "UNTRUSTED_NULL_DEVICE")
    else:
        secure(target)
        info = target.stat()
    record = {"kind": stat.S_IFMT(info.st_mode)}
    if stat.S_ISREG(info.st_mode):
        record["sha256"] = digest(target)
    return record


def preserved_files(c):
    flow_path = Path("/mnt/dietpi_userdata/node-red/flows.json")
    paths = {c.ENV, c.UNIT, PAIR_PATH, c.DB.with_name(c.DB.name + ".weather-identity"), flow_path,
             Path("/etc/freeze-protect/paired-gpio.env"),
             Path("/etc/freeze-protect/paired-gpio-migration-approved")}
    for directory in (Path("/etc/nginx"), UNIT_DIR):
        secure(directory)
        for path in directory.rglob("*"):
            if path.is_file() or path.is_symlink():
                paths.add(path)
    result = {}
    for path in sorted(paths):
        if path.is_symlink():
            secure(path.parent)
            require(path.lstat().st_uid == 0, "UNTRUSTED_LINK")
            target = path.resolve(strict=True)
            result[str(path)] = {"link": os.readlink(path), **link_target_record(target)}
        else:
            # These application-owned data files are inspected, never executed.
            if path in (flow_path, c.DB.with_name(c.DB.name + ".weather-identity")):
                owner = pwd.getpwnam("nodered" if path == flow_path else "freezeprotect").pw_uid
                for part in (path, *path.parents):
                    info = part.lstat()
                    require(not stat.S_ISLNK(info.st_mode) and info.st_uid in (0, owner)
                            and not info.st_mode & 0o002, "UNTRUSTED_DATA_PATH")
            else:
                secure(path)
            result[str(path)] = {"sha256": digest(path)}
    return result


def verify_preserved(c, baseline):
    current = preserved_files(c)
    # Only the explicitly new light unit files and additive nginx site are permitted.
    permitted = {str(UNIT_DIR / unit) for unit in UNITS} | {
        str(UNIT_DIR / "multi-user.target.wants" / unit) for unit in UNITS
    } | {str(NGINX_AVAILABLE), str(NGINX_ENABLED)}
    require(set(current) - set(baseline) <= permitted, "UNRELATED_FILE_ADDED")
    require(all(current.get(path) == value for path, value in baseline.items()),
            "EXISTING_BASELINE_CHANGED")


def private_file(path, content, mode=0o600):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(descriptor, "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(content.encode() if isinstance(content, str) else content)
        stream.flush()
        os.fsync(stream.fileno())


def checkpoint(c, evidence, name, value):
    c.durable(evidence / (name + ".json"), json.dumps(value, sort_keys=True))


def backup(c, evidence, baseline, bench):
    directory = evidence / "backup"
    directory.mkdir(mode=0o700)
    inventory = {}
    for index, (source, value) in enumerate(baseline.items()):
        destination = directory / str(index)
        inventory[source] = dict(value)
        if "sha256" in value:
            private_file(destination, Path(source).read_bytes())
            inventory[source]["backup"] = destination.name
    with (
        closing(sqlite3.connect(c.DB.as_uri() + "?mode=ro", uri=True)) as original,
        closing(sqlite3.connect(directory / "shower.db")) as copied,
    ):
        original.backup(copied)
    for name in ("receipt.json", "samples.json"):
        private_file(directory / ("bench-" + name), (bench / name).read_bytes())
    checkpoint(c, evidence, "baseline", inventory)


def configure(c, directory, evidence):
    c.run(["groupadd", "--system", ACCOUNT])
    c.run(["useradd", "--system", "--gid", ACCOUNT, "--home-dir", str(STATE),
           "--no-create-home", "--shell", "/usr/sbin/nologin", ACCOUNT])
    user, group = pwd.getpwnam(ACCOUNT), grp.getgrnam(ACCOUNT)
    require(user.pw_gid == group.gr_gid
            and os.getgrouplist(ACCOUNT, group.gr_gid) == [group.gr_gid],
            "LIGHT_ACCOUNT_GROUPS")
    for path, mode in ((ROOT, 0o755), (CONFIG, 0o700), (STATE, 0o700)):
        path.mkdir(mode=mode)
        os.chmod(path, mode)
    os.chown(STATE, user.pw_uid, group.gr_gid)
    c.run(["/usr/bin/python3", "-I", "-m", "venv", str(ROOT / "venv")], timeout=120)
    c.run([str(ROOT / "venv/bin/python"), "-I", "-m", "pip", "--isolated", "install",
           "--no-index", "--only-binary=:all:", "--require-hashes",
           "--find-links", str(directory / "wheelhouse"),
           "-r", str(directory / "runtime-install.lock")], timeout=240, child_umask=0o022)
    # umask 077 is required for evidence, but immutable executable trees must be readable.
    for path in [ROOT / "venv", *(ROOT / "venv").rglob("*")]:
        if not path.is_symlink():
            os.chmod(path, 0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    private_file(ROOT / "wait_executor.py", (directory / "wait_executor.py").read_bytes(), 0o644)
    tokens = {role: secrets.token_hex(32) for role in ("display", "settings", "camera")}
    require(len(set(tokens.values())) == 3, "TOKEN_COLLISION")
    environment = {
        "LIGHT_DB_PATH": str(STATE / "independent-light.db"),
        "LIGHT_EXECUTOR_SOCKET": str(RUNTIME / "executor.sock"),
        "LIGHT_ALLOWED_SOURCES": SOURCE,
        **{"LIGHT_" + role.upper() + "_TOKEN": token for role, token in tokens.items()},
    }
    private_file(CONFIG / "controller.env",
                 "".join(key + "=" + value + "\n" for key, value in environment.items()))
    private_file(CONFIG / "executor.env",
                 "LIGHT_GPIO21_ENABLED=commissioned\nLIGHT_GPIO_CHIP=/dev/gpiochip0\n"
                 "LIGHT_GPIO21_ACTIVE_LOW=true\n"
                 "LIGHT_EXECUTOR_SOCKET=/run/independent-light/executor.sock\n")
    c.run(["runuser", "-u", ACCOUNT, "--", str(ROOT / "venv/bin/python"), "-I", "-c",
           ("from pathlib import Path; from freeze_protect.lighting.store import LightStore; "
            "LightStore.provision(Path('/var/lib/independent-light/independent-light.db'))")])
    tls = CONFIG / "tls"
    tls.mkdir(mode=0o700)
    c.run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-sha256", "-nodes",
           "-days", "365", "-subj", "/CN=192.168.114.192",
           "-addext", "subjectAltName=IP:192.168.114.192",
           "-keyout", str(tls / "server.key"), "-out", str(tls / "server.crt")],
          timeout=60)
    os.chmod(tls / "server.key", 0o600)
    os.chmod(tls / "server.crt", 0o644)
    export = evidence / "backup" / "provisioning"
    export.mkdir(mode=0o700)
    certificate = (tls / "server.crt").read_bytes()
    private_file(export / "server.crt", certificate, 0o644)
    encrypted = export / "camera-token.enc"
    payload = json.dumps({"camera_token": tokens["camera"], "endpoint": ENDPOINT,
                          "ca_sha256": hashlib.sha256(certificate).hexdigest()}).encode()
    c.run(["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey",
           str(directory / "recipient-public.pem"), "-pkeyopt", "rsa_padding_mode:oaep",
           "-pkeyopt", "rsa_oaep_md:sha256", "-pkeyopt", "rsa_mgf1_md:sha256",
           "-out", str(encrypted)], input_data=payload)
    require(encrypted.stat().st_size == 512, "RECIPIENT_RSA4096_REQUIRED")
    for unit in UNITS:
        private_file(UNIT_DIR / unit, (directory / unit).read_bytes(), 0o644)
    c.run(["systemd-analyze", "verify", *(str(UNIT_DIR / unit) for unit in UNITS)])
    return tokens["display"]


def validate_light_status(value):
    require(isinstance(value, dict) and value.get("capability") == "independent_light_v1"
            and value.get("mode") == "AUTO" and value.get("desired_on") is False
            and value.get("gpio_on") is False and value.get("health") == "OK"
            and all(type(value.get(key)) is int and value[key] == 0
                    for key in ("remaining_seconds", "manual_remaining_seconds")),
            "LIGHT_INITIAL_OFF_REQUIRED")


def light_high(c):
    value = c.run(["pinctrl", "get", "21"], timeout=5)
    require(re.fullmatch(r"21: op [^\n]*\| hi // GPIO21 = output\s*", value),
            "LIGHT_OFF_READBACK_FAILED")


def wait_executor(c):
    """Wait for readiness without sending an actuator command."""
    path = RUNTIME / "executor.sock"
    deadline = time.monotonic() + 12
    while True:
        try:
            info = path.lstat()
            require(stat.S_ISSOCK(info.st_mode) and info.st_uid == pwd.getpwnam(ACCOUNT).pw_uid,
                    "EXECUTOR_SOCKET_IDENTITY")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                peer.settimeout(0.25)
                peer.connect(str(path))
            break
        except (FileNotFoundError, ConnectionRefusedError):
            require(time.monotonic() < deadline, "EXECUTOR_STARTUP_TIMEOUT")
            time.sleep(0.1)
    require(c.active("light-gpio.service"), "EXECUTOR_SERVICE_INACTIVE")
    light_high(c)
    c.pair_high()


def initial_off(c, display_token):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), c.NoRedirect())
    request = urllib.request.Request("http://127.0.0.1:8002/api/v1/lights/status",
                                    headers={"Authorization": "Bearer " + display_token})
    deadline = time.monotonic() + 12
    while True:
        try:
            with opener.open(request, timeout=2) as response:
                require(response.status == 200 and response.geturl() == request.full_url,
                        "LIGHT_HTTP_STATUS")
                raw = response.read(32769)
            require(len(raw) <= 32768, "LIGHT_STATUS_SIZE")
            validate_light_status(json.loads(raw))
            break
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError:
            # Readiness polling only; never repeat installation, activation or actions.
            require(time.monotonic() < deadline, "LIGHT_STARTUP_TIMEOUT")
            time.sleep(0.25)
    require(all(c.active(unit) for unit in UNITS), "LIGHT_SERVICE_INACTIVE")
    light_high(c)
    c.pair_high()


def verify_ingress(c):
    """Prove local TLS trust, authentication and route isolation without an event."""
    context = ssl.create_default_context(cafile=str(CONFIG / "tls/server.crt"))
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), c.NoRedirect(),
        urllib.request.HTTPSHandler(context=context))
    for method, url, expected in (
        ("POST", ENDPOINT, 401), ("GET", ENDPOINT, 405),
        ("GET", "https://192.168.114.192:8443/api/v1/lights/status", 404),
    ):
        request = urllib.request.Request(url, data=b"{}" if method == "POST" else None,
                                         method=method,
                                         headers={"Content-Type": "application/json"})
        deadline = time.monotonic() + 5
        while True:
            try:
                with opener.open(request, timeout=2) as response:
                    status_code = response.status
            except urllib.error.HTTPError as error:
                status_code = error.code
                error.close()
            except urllib.error.URLError:
                require(time.monotonic() < deadline, "TLS_INGRESS_UNAVAILABLE")
                time.sleep(0.1)
                continue
            require(status_code == expected, "TLS_INGRESS_POLICY")
            break


def remove_activation(path):
    path.unlink(missing_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def cleanup(c, *, started, commissioned=False, enable_attempted=False,
            nginx_link_created=False, outcome=None):
    """Inhibit only this attempt before stop, including partially completed starts."""
    if outcome is None:
        outcome = {}
    # Each cleanup operation is independent: a failed stop cannot retain boot activation.
    for owned, key, path in (
        (commissioned, "commissioned_marker_removed", CONFIG / "commissioned"),
        (nginx_link_created, "new_nginx_link_removed", NGINX_ENABLED),
    ):
        if owned:
            try:
                remove_activation(path)
                outcome[key] = True
            except BaseException:
                outcome[key] = False
    if enable_attempted:
        try:
            c.run(["systemctl", "disable", *UNITS])
            outcome["new_units_disabled"] = True
        except BaseException:
            outcome["new_units_disabled"] = False
    if not started:
        return False
    try:
        c.run(["systemctl", "stop", "light-controller.service", "light-gpio.service"])
    except BaseException:
        pass
    try:
        light_high(c)
        c.pair_high()
        return True
    except BaseException:
        return False


def interrupted(signum, frame):
    raise RuntimeError("INSTALL_INTERRUPTED")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--valves-disconnected", action="store_true")
    parser.add_argument("--lamp-disconnected", action="store_true")
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    evidence, c, started, off = None, None, False, False
    commissioned = enable_attempted = nginx_link_created = False
    cleanup_outcome = {}
    error_code = None
    stage, bench_result = "preflight", None
    result, code = 1, "LIGHT_INSTALL_FAILED"
    for name in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(name, interrupted)
    try:
        require(args.valves_disconnected and args.lamp_disconnected, "BOTH_LOADS_DISCONNECTED_REQUIRED")
        identity = host_identity()
        directory = Path(__file__).resolve().parent
        verify_package(directory, args.manifest_sha256)
        c = load_checks(directory)
        evidence = Path(tempfile.mkdtemp(prefix="independent-light-install.", dir="/root"))
        c.LOG = evidence / "private.log"
        checkpoint(c, evidence, "identity", identity)
        bench = bench_evidence()
        bench_result = "LIGHT_LEVEL_MISMATCH"
        fresh_target(c)
        paired_preflight(c)
        baseline = preserved_files(c)
        backup(c, evidence, baseline, bench)
        c.durable(ATTEMPT, str(evidence))
        checkpoint(c, evidence, "before-mutation", {"manifest_sha256": args.manifest_sha256,
                                                  "paired_sha256": PAIR_HASH,
                                                  "bench_result": "LIGHT_LEVEL_MISMATCH"})
        stage = "configure"
        token = configure(c, directory, evidence)
        verify_package(directory, args.manifest_sha256)
        verify_preserved(c, baseline)
        paired_preflight(c)
        checkpoint(c, evidence, "before-start", {"initial": "OFF"})
        private_file(CONFIG / "commissioned", "Disconnected-load installation; physical acceptance pending.\n")
        commissioned = True
        c.run(["systemctl", "daemon-reload"])
        stage = "activate"
        started = True  # Includes an ambiguous/failed start, so cleanup still stops the new units.
        c.run(["systemctl", "start", "light-gpio.service"])
        wait_executor(c)
        c.run(["systemctl", "start", "light-controller.service"])
        initial_off(c, token)
        paired_preflight(c, light_active=True)
        stage = "ingress"
        private_file(NGINX_AVAILABLE, (directory / "light-camera.conf").read_bytes(), 0o644)
        NGINX_ENABLED.symlink_to(NGINX_AVAILABLE)
        nginx_link_created = True
        c.run(["nginx", "-t"])
        checkpoint(c, evidence, "before-ingress", {"endpoint": ENDPOINT})
        c.run(["systemctl", "reload", "nginx.service"])
        verify_ingress(c)
        enable_attempted = True
        c.run(["systemctl", "enable", *UNITS])
        stage = "acceptance"
        initial_off(c, token)
        paired_preflight(c, light_active=True)
        verify_preserved(c, baseline)
        off, result, code = True, 0, "LIGHT_RUNTIME_INSTALLED_OFF"
    except BaseException as error:
        # Publish only an exact allowlisted constant; never serialize arbitrary text.
        error_code = safe_stop_code(error)
        if c is not None:
            off = cleanup(c, started=started, commissioned=commissioned,
                          enable_attempted=enable_attempted, nginx_link_created=nginx_link_created,
                          outcome=cleanup_outcome)
        if evidence is not None:
            try:
                private_file(evidence / "diagnostic.json", json.dumps({
                    "stage": stage,
                    "error_type": type(error).__name__,
                    "frames": [{"file": Path(frame.filename).name, "line": frame.lineno}
                               for frame in traceback.extract_tb(error.__traceback__)],
                }))
            except BaseException:
                pass
    receipt = {"result": code, "error_code": error_code,
               "failure_inhibition": cleanup_outcome if result else None, "evidence": str(evidence) if evidence else None,
               "backup": str(evidence / "backup") if evidence else None,
               "stage": stage,
               "manifest_sha256": args.manifest_sha256, "required_paired_sha256": PAIR_HASH,
               "final_off_readback": off, "physical_acceptance": "NOT_VERIFIED",
               "retained_on_after_executor_crash": "OWNER_ACCEPTED",
               "bench_result": bench_result, "camera_forwarding": "NOT_CONFIGURED"}
    if evidence is not None and c is not None:
        try:
            checkpoint(c, evidence, "receipt", receipt)
        except BaseException:
            result, receipt["result"] = 1, "LIGHT_RECEIPT_WRITE_FAILED"
            receipt["error_code"] = "LIGHT_RECEIPT_WRITE_FAILED"
            receipt["failure_inhibition"] = cleanup_outcome
            receipt["final_off_readback"] = cleanup(c, started=started, commissioned=commissioned,
                          enable_attempted=enable_attempted, nginx_link_created=nginx_link_created,
                          outcome=cleanup_outcome)
    print(json.dumps(receipt, sort_keys=True))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
