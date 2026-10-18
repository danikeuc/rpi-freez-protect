"""Single-use root-console migration to continuous time sync; OFF/DRAIN only."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import re
import stat
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

CONFIG = Path("/boot/dietpi.txt")
MARKER = Path("/root/freeze-time-sync-v1.started")
SERVICE = "freeze-protect-time-ready.service"
CONTROLLERS = ("light-controller.service", "freeze-protect.service")
DESTINATIONS = {
    "time_ready.py": Path("/usr/local/lib/freeze-protect-time-ready.py"),
    "time-ready.service": Path("/etc/systemd/system") / SERVICE,
    "light_dropin": Path(
        "/etc/systemd/system/light-controller.service.d/35-time-ready.conf"
    ),
    "shower_dropin": Path(
        "/etc/systemd/system/freeze-protect.service.d/35-time-ready.conf"
    ),
}
BASELINE = {
    "/opt/independent-light/venv/lib/python3.13/site-packages/freeze_protect/lighting/controller.py": "21795415098d09e294c0e0aa486b7f675f26d786e4b08a07693213d49c2a9ce9",
    "/opt/rpi-freez-protect/.venv/lib/python3.13/site-packages/freeze_protect/adapters/node_red.py": "a7be7bafdd890db267035d0273c8a2ea874d5c1bc762ad7620c4b3f84c19ede1",
}


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def updated_config(data):
    matches = list(re.finditer(rb"(?m)^[ \t]*CONFIG_NTP_MODE=([^\r\n]*)", data))
    require(len(matches) == 1 and matches[0][1] == b"2", "NTP_BASELINE_CHANGED")
    a, b = matches[0].span(1)
    return data[:a] + b"4" + data[b:]


def transition(ops):
    for phase in (
        "preflight",
        "backup",
        "inhibit",
        "stop",
        "verify_stopped",
        "apply",
        "synchronize",
        "verify_durable",
        "start",
        "verify_after",
    ):
        print("PHASE=" + phase, flush=True)
        getattr(ops, phase)()


def load_support():
    path = (
        Path(__file__).resolve().parent.parent
        / "lighting/diagnostics/install_diagnostics.py"
    )
    spec = importlib.util.spec_from_file_location("time_sync_support", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Host:
    def __init__(self, package):
        self.package = package
        self.diag = load_support()
        self.s = self.diag.support
        self.evidence = None
        self.api_writes = 0

    def record(self, name, data):
        require(self.evidence is not None, "EVIDENCE_REQUIRED")
        self.s.private(self.evidence / name, json.dumps(data).encode())

    def run(self, *args, timeout=20):
        result = subprocess.run(
            args,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
        )
        require(result.returncode == 0, "COMMAND_FAILED")
        return result.stdout.decode().strip()

    def assert_baseline(self):
        for name, digest in BASELINE.items():
            self.s.secure(Path(name))
            require(self.s.sha(Path(name)) == digest, "CONTROLLER_BASELINE_CHANGED")

    def preflight(self):
        self.s.secure(CONFIG)
        require(CONFIG.is_file() and CONFIG.stat().st_size < 262144, "CONFIG_INVALID")
        self.before = CONFIG.read_bytes()
        self.after = updated_config(self.before)
        for target in DESTINATIONS.values():
            require(not os.path.lexists(target), "TIME_GATE_ALREADY_PRESENT")
            parent = target.parent if target.parent.exists() else target.parent.parent
            self.s.secure(parent)
        self.assert_baseline()
        self.s.active_units()
        for package in ("systemd-timesyncd", "dbus"):
            require(
                self.run("dpkg-query", "-W", "-f=${db:Status-Status}", package)
                == "installed",
                "TIME_DEPENDENCY_MISSING",
            )
        require(
            self.run(
                "systemctl",
                "show",
                "systemd-timesyncd.service",
                "--property=LoadState",
                "--value",
            )
            == "loaded",
            "TIMESYNCD_NOT_LOADED",
        )
        require(
            self.run("systemctl", "is-enabled", "systemd-timesyncd.service")
            == "enabled",
            "TIMESYNCD_ENABLEMENT_CHANGED",
        )
        require(
            self.run(
                "systemctl",
                "show",
                "systemd-timesyncd.service",
                "--property=ActiveState",
                "--value",
            )
            == "inactive",
            "TIMESYNCD_ALREADY_ACTIVE",
        )
        for name in ("time_ready.py", "time-ready.service", "35-time-ready.conf"):
            self.s.secure(self.package / name)
        compile((self.package / "time_ready.py").read_bytes(), "time_ready.py", "exec")
        light, shower = (
            self.s.environment(self.s.ENV),
            self.s.environment(self.s.SHOWER_ENV),
        )
        require(
            light.get("LIGHT_DB_PATH") == str(self.s.DB)
            and shower.get("FREEZE_PROTECT_DB_PATH") == str(self.s.SHOWER_DB),
            "DATABASE_PATH_CHANGED",
        )
        self.api = self.s.API(light, shower)
        current = self.api("light", "status")
        require(
            current.get("health") == "OK"
            and current.get("desired_on") is False
            and current.get("gpio_on") is False,
            "LIGHT_HEALTHY_OFF_REQUIRED",
        )
        self.s.require_shower_recovered(self.api("shower", "display/status"))
        self.s.drain_check()
        self.settings = self.api("light", "settings")
        self.env_hashes = {
            str(p): self.s.sha(p) for p in (self.s.ENV, self.s.SHOWER_ENV)
        }
        self.identity = self.s.SHOWER_DB.with_name(
            self.s.SHOWER_DB.name + ".weather-identity"
        )
        require(
            self.identity.is_file() and not self.identity.is_symlink(),
            "WEATHER_IDENTITY_REQUIRED",
        )
        self.identity_bytes = self.identity.read_bytes()

    def backup(self):
        self.evidence = Path(tempfile.mkdtemp(prefix="freeze-time-sync.", dir="/root"))
        os.chmod(self.evidence, 0o700)
        self.s.private(MARKER, str(self.evidence).encode())
        print("BACKUP_DIRECTORY=" + str(self.evidence), flush=True)
        self.s.private(self.evidence / "dietpi.txt", self.before)
        meta = CONFIG.stat()
        self.record(
            "before.json",
            {
                "config_uid": meta.st_uid,
                "config_gid": meta.st_gid,
                "config_mode": stat.S_IMODE(meta.st_mode),
                "timesyncd_enabled": True,
                "timesyncd_active": False,
                "settings": self.settings,
                "environment_hashes": self.env_hashes,
            },
        )
        self.s.backup_db(self.s.DB, self.evidence / "light-live.db")
        self.s.backup_db(self.s.SHOWER_DB, self.evidence / "shower-live.db")
        self.s.private(
            self.evidence / "shower.db.weather-identity", self.identity_bytes
        )

    def inhibit(self):
        current = self.api("light", "status")
        require(
            current.get("health") == "OK"
            and current.get("desired_on") is False
            and current.get("gpio_on") is False,
            "LIGHT_CHANGED",
        )
        if (
            current.get("mode") != "MANUAL_OFF"
            or current.get("manual_remaining_seconds", 0) < 600
        ):
            self.record("manual-off-requested.json", {"revision": current["revision"]})
            self.api_writes += 1
            self.s.require_light_recovered(
                self.api(
                    "light",
                    "actions",
                    {
                        "request_id": str(uuid.uuid4()),
                        "expected_revision": current["revision"],
                        "action": "manual_off",
                    },
                )
            )
        self.diag.preflight(
            self.api("light", "status"),
            self.api("shower", "display/status"),
            minimum=600,
        )
        self.s.drain_check()

    def stop(self):
        self.record("stop-started.json", {})
        for unit in CONTROLLERS:
            self.run("systemctl", "stop", unit)

    def verify_stopped(self):
        for unit in CONTROLLERS:
            require(
                self.run("systemctl", "show", unit, "--property=ActiveState", "--value")
                == "inactive",
                "STOP_UNCONFIRMED",
            )
        self.s.drain_check()
        self.s.backup_db(self.s.DB, self.evidence / "light-stopped.db")
        self.s.backup_db(self.s.SHOWER_DB, self.evidence / "shower-stopped.db")
        self.weather_settings = self.diag.durable_off(
            self.s.DB, self.s.SHOWER_DB, minimum=300
        )
        self.start_mono = time.monotonic()

    def apply(self):
        require(CONFIG.read_bytes() == self.before, "CONFIG_CHANGED")
        self.record("apply-started.json", {})
        for name, target in DESTINATIONS.items():
            target.parent.mkdir(mode=0o755, exist_ok=True)
            self.s.secure(target.parent)
            source = self.package / (
                "35-time-ready.conf" if name.endswith("dropin") else name
            )
            self.s.private(target, source.read_bytes())
            os.chmod(target, 0o644)
        temporary = self.evidence / "dietpi-after.txt"
        self.s.private(temporary, self.after)
        self.diag.replace_source(temporary, CONFIG)
        require(CONFIG.read_bytes() == self.after, "CONFIG_WRITE_MISMATCH")
        self.run(
            "systemd-analyze",
            "verify",
            str(DESTINATIONS["time-ready.service"]),
            "/etc/systemd/system/freeze-protect.service",
            "/etc/systemd/system/light-controller.service",
        )
        self.run("systemctl", "daemon-reload")
        for unit in CONTROLLERS:
            deps = self.run(
                "systemctl", "show", unit, "--property=Requires", "--value"
            ).split()
            order = self.run(
                "systemctl", "show", unit, "--property=After", "--value"
            ).split()
            require(SERVICE in deps and SERVICE in order, "TIME_GATE_NOT_EFFECTIVE")

    def synchronize(self):
        # Already enabled on this DietPi baseline. Preserve NTP servers and all other config.
        self.run("systemctl", "start", "systemd-timesyncd.service")
        self.run("systemctl", "start", SERVICE, timeout=70)
        require(
            self.run("timedatectl", "show", "--property=NTPSynchronized", "--value")
            == "yes",
            "TIME_NOT_SYNCHRONIZED",
        )
        self.s.clock_check()

    def verify_durable(self):
        require(time.monotonic() - self.start_mono < 180, "MAINTENANCE_WINDOW_EXPIRED")
        require(
            self.diag.durable_off(self.s.DB, self.s.SHOWER_DB, minimum=120)
            == self.weather_settings,
            "DURABLE_STATE_CHANGED",
        )
        require(
            {str(p): self.s.sha(p) for p in (self.s.ENV, self.s.SHOWER_ENV)}
            == self.env_hashes,
            "ENV_CHANGED",
        )
        require(
            self.identity.read_bytes() == self.identity_bytes,
            "WEATHER_IDENTITY_CHANGED",
        )
        self.s.drain_check()
        self.assert_baseline()

    def start(self):
        self.record("start-requested.json", {})
        for unit in reversed(CONTROLLERS):
            self.run("systemctl", "start", unit, timeout=85)

    def verify_after(self):
        self.diag.readiness(self.api)
        self.s.active_units()
        self.verify_durable()
        require(self.api("light", "settings") == self.settings, "SETTINGS_CHANGED")
        require(CONFIG.read_bytes() == self.after, "CONFIG_CHANGED")
        require(
            self.run("systemctl", "is-active", "systemd-timesyncd.service") == "active",
            "TIME_SERVICE_INACTIVE",
        )
        require(
            self.run("timedatectl", "show", "--property=NTPSynchronized", "--value")
            == "yes",
            "TIME_NOT_SYNCHRONIZED",
        )
        result = {
            "result": "CONTINUOUS_TIME_SYNC_INSTALLED",
            "backup": str(self.evidence),
            "ntp_mode": 4,
            "time_synchronized": True,
            "light_mode": "MANUAL_OFF",
            "light_health": "OK",
            "shower_operation": "USER_OFF",
            "shower_command": "DRAIN",
            "gpio20": "high",
            "gpio21": "high",
            "gpio26": "high",
            "api_manual_off_writes": self.api_writes,
            "cold_boot_acceptance": "NOT_TESTED",
            "physical_acceptance": "NOT_TESTED",
        }
        self.record("success.json", result)
        print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loads-disconnected", action="store_true")
    args = parser.parse_args()
    require(args.loads_disconnected, "LOADS_DISCONNECTED_REQUIRED")
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    os.umask(0o077)
    require(
        Path("/proc/device-tree/model").read_bytes().rstrip(b"\0\n")
        == b"Raspberry Pi 4 Model B Rev 1.1",
        "WRONG_HOST",
    )
    host = Host(Path(__file__).resolve().parent)
    host.s.secure(host.package)
    host.s.secure(host.s.LOCK.parent)
    require(not os.path.lexists(MARKER), "PRIOR_ATTEMPT_REVIEW_REQUIRED")
    fd = os.open(host.s.LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+"):
        host.s.secure(host.s.LOCK)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not os.path.lexists(MARKER), "PRIOR_ATTEMPT_REVIEW_REQUIRED")
        try:
            transition(host)
        except Exception as exc:
            if host.evidence is not None:
                host.record(
                    "failed.json",
                    {"error_type": type(exc).__name__, "message": str(exc)},
                )
            raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never expose secret-bearing errors
        code = (
            str(exc)
            if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Z_]+", str(exc))
            else type(exc).__name__
        )
        print(
            "TIME_SYNC_STOPPED="
            + code
            + "; inspect backup; no automatic retry or rollback",
            flush=True,
        )
        raise SystemExit(1) from None
