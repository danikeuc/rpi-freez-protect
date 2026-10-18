"""Bounded root-console recovery. Never sends light ON or shower SUPPLY."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
import urllib.request
import uuid
from contextlib import closing
from pathlib import Path

BASE = Path(
    "/opt/independent-light/venv/lib/python3.13/site-packages/freeze_protect/lighting"
)
ENV = Path("/etc/independent-light/controller.env")
DB = Path("/var/lib/independent-light/independent-light.db")
MARKER = Path("/root/controller-off-recovery-v1.started")
SERVICE = "light-controller.service"


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def secure(path):
    for item in (path, *path.parents):
        s = item.lstat()
        require(
            s.st_uid == 0 and not stat.S_ISLNK(s.st_mode) and not s.st_mode & 0o022,
            "UNTRUSTED_PATH",
        )


def run(*args):
    result = subprocess.run(
        args,
        capture_output=True,
        timeout=20,
        check=False,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
    )
    require(result.returncode == 0, "COMMAND_FAILED")
    return result.stdout.decode().strip()


def drain_check():
    for pin in ("20", "21", "26"):
        line = run("pinctrl", "get", pin)
        require(
            "| hi" in line and "op" in line.split("|")[0].split(),
            "OUTPUT_HIGH_REQUIRED",
        )


def private(path, data):
    with path.open("xb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("REDIRECT_REJECTED")


def validate_sources(package, baseline):
    require(set(baseline) == {"models.py", "controller.py"}, "MANIFEST_INVALID")
    for name, item in baseline.items():
        secure(BASE / name)
        require(sha(BASE / name) == item["before"], "BASELINE_CHANGED")
        require(sha(package / name) == item["after"], "PACKAGE_CHANGED")
        compile((package / name).read_bytes(), name, "exec")


SHOWER_ENV = Path("/etc/rpi-freeze-protect/environment")
SHOWER_DB = Path("/var/lib/rpi-freeze-protect/freeze-protect.db")
LOCK = Path("/var/lib/freeze-protect-maintenance/operation.lock")
UNITS = (
    SERVICE,
    "light-gpio.service",
    "freeze-protect.service",
    "freeze-protect-pair-gpio.service",
    "node-red.service",
)


def require_light_fault_off(status):
    require(
        status.get("health") == "FAULT"
        and status.get("desired_on") is False
        and status.get("gpio_on") is False,
        "LIGHT_FAULT_OFF_REQUIRED",
    )
    require(
        type(status.get("revision")) is int and status["revision"] >= 0,
        "REVISION_INVALID",
    )


def require_shower_safe(status):
    require(
        status.get("mode") == "weather_assisted"
        and status.get("command") == "DRAIN"
        and (
            (status.get("operation") == "FAULT" and status.get("state") == "FAULT")
            or (
                status.get("operation") == "USER_OFF"
                and status.get("state") == "MANUAL_DRAIN"
            )
        ),
        "SHOWER_FAULT_OR_USER_OFF_REQUIRED",
    )


def require_light_recovered(status):
    require(
        status.get("health") == "OK"
        and status.get("mode") == "MANUAL_OFF"
        and status.get("desired_on") is False
        and status.get("gpio_on") is False
        and type(status.get("manual_remaining_seconds")) is int
        and status["manual_remaining_seconds"] > 0,
        "MANUAL_OFF_UNCONFIRMED",
    )


def require_shower_recovered(status):
    require_shower_safe(status)
    require(
        status.get("operation") == "USER_OFF" and status.get("reason") == "user_off",
        "USER_OFF_UNCONFIRMED",
    )


def recover(api, check_pins, record):
    light, shower = api("light", "status"), api("shower", "display/status")
    require_light_fault_off(light)
    require_shower_safe(shower)
    check_pins()
    request = {
        "request_id": str(uuid.uuid4()),
        "expected_revision": light["revision"],
        "action": "manual_off",
    }
    record("light-action-started.json", request)
    # No POST retries: timeout or malformed receipt leaves an uncertain outcome.
    require_light_recovered(api("light", "actions", request))
    light = api("light", "status")
    require_light_recovered(light)
    check_pins()
    record("light-recovered.json", light)
    shower = api("shower", "display/status")
    require_shower_safe(shower)
    if shower["operation"] == "FAULT":
        record("shower-clear-started.json", {"command": "CLEAR_FAULT"})
        receipt = api("shower", "commands/clear-fault", {})
        require(
            receipt.get("state") == "MANUAL_DRAIN"
            and receipt.get("command") == "DRAIN"
            and receipt.get("reason") == "user_off",
            "DRAIN_RECEIPT_INVALID",
        )
    shower = api("shower", "display/status")
    require_shower_recovered(shower)
    check_pins()
    record("shower-recovered.json", shower)
    return {"light": light, "shower": shower}


def environment(path):
    secure(path)
    require(path.is_file() and path.stat().st_mode & 0o077 == 0, "ENV_PERMISSIONS")
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        words = shlex.split(value, comments=True)
        require(len(words) <= 1 and key not in values, "ENV_FORMAT")
        values[key] = words[0] if words else ""
    return values


class API:
    def __init__(self, light, shower):
        self.light, self.shower = light, shower
        self.client = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()
        )

    def __call__(self, kind, endpoint, payload=None):
        allowed = {
            ("light", "status", False),
            ("light", "settings", False),
            ("light", "actions", True),
            ("shower", "display/status", False),
            ("shower", "events?limit=1000", False),
            ("shower", "commands/clear-fault", True),
        }
        require((kind, endpoint, payload is not None) in allowed, "API_ROUTE_REJECTED")
        if kind == "light":
            token = self.light[
                "LIGHT_SETTINGS_TOKEN"
                if endpoint == "settings"
                else "LIGHT_DISPLAY_TOKEN"
            ]
            headers = {"Authorization": "Bearer " + token}
            url = "http://127.0.0.1:8002/api/v1/lights/" + endpoint
            if payload is not None:
                require(payload.get("action") == "manual_off", "ACTION_REJECTED")
        else:
            display = endpoint == "display/status"
            headers = {
                "X-Display-Token" if display else "X-Admin-Token": self.shower[
                    "FREEZE_PROTECT_DISPLAY_TOKEN"
                    if display
                    else "FREEZE_PROTECT_ADMIN_TOKEN"
                ]
            }
            url = "http://127.0.0.1:8000/api/v1/" + endpoint
            if payload is not None:
                require(payload == {}, "ACTION_REJECTED")
                headers["X-Confirm-Command"] = "CLEAR_FAULT"
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, headers=headers, data=data)
        with self.client.open(request, timeout=8) as response:
            require(response.status == 200, "HTTP_REJECTED")
            body = response.read(2097153)
            require(len(body) <= 2097152, "BODY_TOO_LARGE")
        return json.loads(body)


def backup_db(source_path, target):
    require(source_path.is_file() and not source_path.is_symlink(), "DATABASE_INVALID")
    with (
        closing(
            sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, timeout=3)
        ) as source,
        closing(sqlite3.connect(target)) as dest,
    ):
        # Bound backup even if a concurrently active service is busy.
        deadline = time.monotonic() + 15

        def progress(*args):
            require(time.monotonic() < deadline, "BACKUP_TIMEOUT")

        source.backup(dest, pages=100, progress=progress, sleep=0.05)
        require(
            dest.execute("PRAGMA integrity_check").fetchone() == ("ok",),
            "BACKUP_INTEGRITY",
        )
    with target.open("rb") as stream:
        os.fsync(stream.fileno())


def require_durable_fault(path):
    with closing(
        sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    ) as db:
        rows = db.execute("SELECT data FROM state").fetchall()
        require(
            len(rows) == 1 and json.loads(rows[0][0]).get("fault") is True,
            "DURABLE_FAULT_REQUIRED",
        )


def adapter_diagnostic(events):
    patterns = {
        "connection_refused": "connection refused",
        "timeout": "timed out",
        "http_401": "http error 401",
        "http_403": "http error 403",
        "http_409": "http error 409",
        "http_503": "http error 503",
        "receipt_mismatch": "receipt does not match",
        "protocol_mismatch": "protocol version mismatch",
        "action_mismatch": "supply action mismatch",
        "invalid_receipt": "receipt is invalid",
        "invalid_response": "response is invalid",
    }
    for event in events.get("items", [])[:1000]:
        if event.get("event_type") == "relay_driver_error":
            message = str(event.get("payload", {}).get("error", "")).lower()[:8192]
            return {
                "latest_relay_failure_categories": [
                    name for name, pattern in patterns.items() if pattern in message
                ]
                or ["unclassified"]
            }
    return {"latest_relay_failure_categories": ["not_in_recent_window"]}


def clock_check():
    wall, mono = time.time(), time.monotonic()
    time.sleep(2)
    dw, dm = time.time() - wall, time.monotonic() - mono
    require(dm > 0 and abs(dw - dm) <= 0.25, "CLOCK_UNSTABLE")
    return {
        "sample_seconds": dm,
        "wall_monotonic_delta_seconds": dw - dm,
        "historical_clock_cause": "NOT_ESTABLISHED",
    }


def active_units():
    for unit in UNITS:
        require(run("systemctl", "is-active", unit) == "active", "SERVICE_NOT_ACTIVE")
        require(
            run("systemctl", "show", unit, "--property=NeedDaemonReload", "--value")
            == "no",
            "UNIT_CHANGED",
        )


def install(package):
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    os.umask(0o077)
    require(
        Path("/proc/device-tree/model").read_bytes().rstrip(b"\0\n")
        == b"Raspberry Pi 4 Model B Rev 1.1",
        "WRONG_HOST",
    )
    secure(package)
    require(not os.path.lexists(MARKER), "PRIOR_ATTEMPT_REVIEW_REQUIRED")
    secure(LOCK.parent)
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+"):
        secure(LOCK)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _install_locked(package)


def _install_locked(package):
    baseline = json.loads((package / "baseline.json").read_text())
    validate_sources(package, baseline)
    light, shower = environment(ENV), environment(SHOWER_ENV)
    require(
        light.get("LIGHT_DB_PATH") == str(DB)
        and shower.get("FREEZE_PROTECT_DB_PATH") == str(SHOWER_DB),
        "DATABASE_PATH_CHANGED",
    )
    require(
        shower.get("FREEZE_PROTECT_CONTROL_MODE") == "weather_assisted", "MODE_CHANGED"
    )
    for values, keys in (
        (light, ("LIGHT_DISPLAY_TOKEN", "LIGHT_SETTINGS_TOKEN")),
        (shower, ("FREEZE_PROTECT_ADMIN_TOKEN", "FREEZE_PROTECT_DISPLAY_TOKEN")),
    ):
        require(
            all(
                re.fullmatch(r"[A-Za-z0-9_-]{32,512}", values.get(k, "")) for k in keys
            ),
            "TOKEN_FORMAT",
        )
    api = API(light, shower)
    active_units()
    require_light_fault_off(api("light", "status"))
    require_shower_safe(api("shower", "display/status"))
    drain_check()
    timing = clock_check()
    settings = api("light", "settings")
    hashes = {str(f): sha(f) for f in (ENV, SHOWER_ENV)}
    evidence = Path(tempfile.mkdtemp(prefix="controller-off-recovery.", dir="/root"))
    os.chmod(evidence, 0o700)

    def record(name, data):
        private(evidence / name, json.dumps(data).encode())

    private(MARKER, str(evidence).encode())
    print("BACKUP_DIRECTORY=" + str(evidence), flush=True)
    record(
        "before.json",
        {
            "source": baseline,
            "environment_hashes": hashes,
            "settings": settings,
            "clock": timing,
        },
    )
    # Preserve raw adapter details only in root-private evidence, never stdout.
    events = api("shower", "events?limit=1000")
    record("shower-events-private.json", events)
    diagnostic = adapter_diagnostic(events)
    record("diagnostic.json", diagnostic)
    print(json.dumps(diagnostic), flush=True)
    backup_db(SHOWER_DB, evidence / "shower.db")
    run("systemctl", "stop", SERVICE)
    require(
        run("systemctl", "show", SERVICE, "--property=ActiveState", "--value")
        == "inactive",
        "STOP_UNCONFIRMED",
    )
    drain_check()
    backup_db(DB, evidence / "light.db")
    require_durable_fault(evidence / "light.db")
    for name in baseline:
        shutil.copy2(BASE / name, evidence / name)
        require(sha(evidence / name) == baseline[name]["before"], "BACKUP_MISMATCH")
    record("install-started.json", {})
    for name, item in baseline.items():
        if item["before"] == item["after"]:
            continue
        target = BASE / name
        meta = target.stat()
        fd, temporary = tempfile.mkstemp(prefix=".recovery-", dir=BASE)
        with os.fdopen(fd, "wb") as stream:
            stream.write((package / name).read_bytes())
            os.fchmod(stream.fileno(), stat.S_IMODE(meta.st_mode))
            os.fchown(stream.fileno(), meta.st_uid, meta.st_gid)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        require(sha(target) == item["after"], "INSTALL_HASH_MISMATCH")
    fd = os.open(BASE, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    run("systemctl", "start", SERVICE)
    # Only readiness GETs may retry; they cannot clear the fault or turn ON.
    for attempt in range(20):
        try:
            require_light_fault_off(api("light", "status"))
            break
        except OSError:
            require(attempt < 19, "STARTUP_TIMEOUT")
            time.sleep(0.25)
    result = recover(api, drain_check, record)
    active_units()
    require(api("light", "settings") == settings, "SETTINGS_CHANGED")
    require({str(f): sha(f) for f in (ENV, SHOWER_ENV)} == hashes, "ENV_CHANGED")
    require_light_recovered(api("light", "status"))
    require_shower_recovered(api("shower", "display/status"))
    drain_check()
    result = {
        "result": "CONTROLLERS_RECOVERED_OFF",
        "backup": str(evidence),
        "light_mode": result["light"]["mode"],
        "light_health": result["light"]["health"],
        "shower_operation": result["shower"]["operation"],
        "shower_command": "DRAIN",
        "gpio20": "high",
        "gpio21": "high",
        "gpio26": "high",
        "physical_acceptance": "NOT_TESTED",
        "original_fault_cause": "NOT_RESOLVED",
        "controller_sha256": sha(BASE / "controller.py"),
    }
    record("success.json", result)
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loads-disconnected", action="store_true")
    args = parser.parse_args()
    require(args.loads_disconnected, "LOADS_DISCONNECTED_REQUIRED")
    install(Path(__file__).resolve().parent)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never print secret-bearing exceptions
        code = (
            str(exc)
            if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Z_]+", str(exc))
            else type(exc).__name__
        )
        print(
            "CONTROLLER_RECOVERY_STOPPED=" + code + "; no automatic retry or rollback"
        )
        raise SystemExit(1) from None
