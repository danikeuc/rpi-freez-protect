"""Root-console diagnostic patch; fixed targets, GET-only verification, no auto retry."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import math
import os
import re
import sqlite3
import stat
import tempfile
import time
from contextlib import closing
from pathlib import Path

SUPPORT = Path(__file__).resolve().parent.parent / "recovery/recover_controllers.py"
SPEC = importlib.util.spec_from_file_location("diagnostic_support", SUPPORT)
assert SPEC and SPEC.loader
support = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(support)
require = support.require
TARGETS = {
    "light_controller.py": support.BASE / "controller.py",
    "node_red.py": Path(
        "/opt/rpi-freez-protect/.venv/lib/python3.13/site-packages/freeze_protect/adapters/node_red.py"
    ),
}
MARKER = Path("/root/controller-fault-diagnostics-v1.started")
RESTART_UNITS = ("light-controller.service", "freeze-protect.service")


def preflight(light, shower, minimum=300):
    support.require_light_recovered(light)
    require(light["manual_remaining_seconds"] >= minimum, "MANUAL_OFF_TIME_REQUIRED")
    support.require_shower_recovered(shower)


def read_row(path, query):
    with closing(
        sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    ) as db:
        rows = db.execute(query).fetchall()
        require(len(rows) == 1, "DURABLE_STATE_INVALID")
        return json.loads(rows[0][0])


def durable_off(light_db, shower_db, minimum=120):
    light = read_row(light_db, "SELECT data FROM state")
    until, saved = light.get("manual_until"), light.get("saved_at")
    now = time.time()
    require(
        light.get("mode") == "MANUAL_OFF"
        and light.get("fault") is False
        and type(until) in (int, float)
        and math.isfinite(until)
        and minimum <= until - now <= 7200
        and type(saved) in (int, float)
        and math.isfinite(saved)
        and saved <= now + 5,
        "DURABLE_MANUAL_OFF_REQUIRED",
    )
    shower = read_row(
        shower_db, "SELECT payload_json FROM weather_control WHERE singleton=1"
    )
    require(
        shower.get("user_off") is True
        and shower.get("fault_inhibited") is False
        and shower.get("active_marker") is None,
        "DURABLE_USER_OFF_REQUIRED",
    )
    return shower["settings"]


def validate_sources(package, manifest):
    require(set(manifest) == set(TARGETS), "MANIFEST_INVALID")
    for name, target in TARGETS.items():
        support.secure(target)
        support.secure(package / name)
        require(support.sha(target) == manifest[name]["before"], "BASELINE_CHANGED")
        require(
            support.sha(package / name) == manifest[name]["after"], "PACKAGE_CHANGED"
        )
        compile((package / name).read_bytes(), name, "exec")


def replace_source(source, target):
    meta = target.stat()
    fd, temporary = tempfile.mkstemp(prefix=".diagnostics-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(source.read_bytes())
            os.fchmod(stream.fileno(), stat.S_IMODE(meta.st_mode))
            os.fchown(stream.fileno(), meta.st_uid, meta.st_gid)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def readiness(api):
    for attempt in range(20):
        try:
            preflight(
                api("light", "status"), api("shower", "display/status"), minimum=60
            )
            return
        except OSError:
            require(attempt < 19, "STARTUP_TIMEOUT")
            time.sleep(0.25)


def install_locked(package):
    manifest = json.loads((package / "baseline.json").read_text())
    validate_sources(package, manifest)
    light, shower = (
        support.environment(support.ENV),
        support.environment(support.SHOWER_ENV),
    )
    require(
        light.get("LIGHT_DB_PATH") == str(support.DB)
        and shower.get("FREEZE_PROTECT_DB_PATH") == str(support.SHOWER_DB)
        and shower.get("FREEZE_PROTECT_CONTROL_MODE") == "weather_assisted",
        "CONFIGURATION_CHANGED",
    )
    api = support.API(light, shower)
    support.active_units()
    preflight(api("light", "status"), api("shower", "display/status"))
    support.drain_check()
    support.clock_check()
    settings = api("light", "settings")
    env_hashes = {str(f): support.sha(f) for f in (support.ENV, support.SHOWER_ENV)}
    identity = support.SHOWER_DB.with_name(support.SHOWER_DB.name + ".weather-identity")
    require(
        identity.is_file() and not identity.is_symlink(), "WEATHER_IDENTITY_REQUIRED"
    )
    identity_bytes = identity.read_bytes()
    require(
        re.fullmatch(rb"[0-9a-f]{32}", identity_bytes) is not None,
        "WEATHER_IDENTITY_INVALID",
    )
    evidence = Path(
        tempfile.mkdtemp(prefix="controller-fault-diagnostics.", dir="/root")
    )
    os.chmod(evidence, 0o700)

    def record(name, value):
        support.private(evidence / name, json.dumps(value).encode())

    support.private(MARKER, str(evidence).encode())
    print("BACKUP_DIRECTORY=" + str(evidence), flush=True)
    record(
        "before.json",
        {"source": manifest, "environment_hashes": env_hashes, "settings": settings},
    )
    # Backups complete before any stop. Then take a second, quiescent DB snapshot.
    for source, name in ((support.DB, "light"), (support.SHOWER_DB, "shower")):
        support.backup_db(source, evidence / (name + "-live.db"))
    for name, target in TARGETS.items():
        support.private(evidence / name, target.read_bytes())
        require(
            support.sha(evidence / name) == manifest[name]["before"], "BACKUP_MISMATCH"
        )
    support.private(evidence / "shower.db.weather-identity", identity_bytes)
    preflight(api("light", "status"), api("shower", "display/status"))
    started = time.monotonic()
    wall = time.time()
    record("stop-started.json", {})
    for unit in RESTART_UNITS:
        support.run("systemctl", "stop", unit)
        require(
            support.run("systemctl", "show", unit, "--property=ActiveState", "--value")
            == "inactive",
            "STOP_UNCONFIRMED",
        )
    support.drain_check()
    for source, name in ((support.DB, "light"), (support.SHOWER_DB, "shower")):
        support.backup_db(source, evidence / (name + ".db"))
    weather_settings = durable_off(support.DB, support.SHOWER_DB)
    validate_sources(package, manifest)
    record("install-started.json", {})
    for name, target in TARGETS.items():
        replace_source(package / name, target)
        require(support.sha(target) == manifest[name]["after"], "INSTALL_HASH_MISMATCH")
    require(
        {str(f): support.sha(f) for f in (support.ENV, support.SHOWER_ENV)}
        == env_hashes,
        "ENV_CHANGED",
    )
    require(identity.read_bytes() == identity_bytes, "WEATHER_IDENTITY_CHANGED")
    # No start if the operator changed durable inhibition or the clock jumped.
    require(time.monotonic() - started < 90, "MAINTENANCE_WINDOW_EXPIRED")
    require(
        abs((time.time() - wall) - (time.monotonic() - started)) <= 0.5,
        "CLOCK_UNSTABLE",
    )
    durable_off(support.DB, support.SHOWER_DB)
    for unit in reversed(RESTART_UNITS):
        support.run("systemctl", "start", unit)
    readiness(api)
    support.active_units()
    support.drain_check()
    require(api("light", "settings") == settings, "SETTINGS_CHANGED")
    require(
        durable_off(support.DB, support.SHOWER_DB, minimum=60) == weather_settings,
        "WEATHER_SETTINGS_CHANGED",
    )
    require(
        {str(f): support.sha(f) for f in (support.ENV, support.SHOWER_ENV)}
        == env_hashes,
        "ENV_CHANGED",
    )
    require(identity.read_bytes() == identity_bytes, "WEATHER_IDENTITY_CHANGED")
    result = {
        "result": "CONTROLLER_FAULT_DIAGNOSTICS_INSTALLED",
        "backup": str(evidence),
        "light_health": "OK",
        "light_mode": "MANUAL_OFF",
        "shower_operation": "USER_OFF",
        "shower_command": "DRAIN",
        "gpio20": "high",
        "gpio21": "high",
        "gpio26": "high",
        "source_hashes": {
            name: support.sha(target) for name, target in TARGETS.items()
        },
        "api_writes": 0,
        "startup_commands": "NORMAL_OFF_AND_DRAIN",
        "original_fault_cause": "NOT_RESOLVED",
        "physical_acceptance": "NOT_TESTED",
    }
    record("success.json", result)
    print(json.dumps(result))


def install(package):
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    os.umask(0o077)
    require(
        Path("/proc/device-tree/model").read_bytes().rstrip(b"\0\n")
        == b"Raspberry Pi 4 Model B Rev 1.1",
        "WRONG_HOST",
    )
    support.secure(package)
    support.secure(SUPPORT)
    require(not os.path.lexists(MARKER), "PRIOR_ATTEMPT_REVIEW_REQUIRED")
    support.secure(support.LOCK.parent)
    fd = os.open(support.LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+"):
        support.secure(support.LOCK)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not os.path.lexists(MARKER), "PRIOR_ATTEMPT_REVIEW_REQUIRED")
        install_locked(package)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loads-disconnected", action="store_true")
    args = parser.parse_args()
    require(args.loads_disconnected, "LOADS_DISCONNECTED_REQUIRED")
    install(Path(__file__).resolve().parent)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - do not expose credentials from errors
        code = (
            str(exc)
            if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Z_]+", str(exc))
            else type(exc).__name__
        )
        print(
            "CONTROLLER_DIAGNOSTICS_STOPPED="
            + code
            + "; no automatic retry or rollback"
        )
        raise SystemExit(1) from None
