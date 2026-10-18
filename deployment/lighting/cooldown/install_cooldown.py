"""Root-console patch: manual ON expiry adds 900 seconds of camera inhibition."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

BASE = Path(
    "/opt/independent-light/venv/lib/python3.13/site-packages/freeze_protect/lighting"
)
ENV = Path("/etc/independent-light/controller.env")
DB = Path("/var/lib/independent-light/independent-light.db")
MARKER = Path("/root/light-cooldown-v1.started")
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
    for pin in ("20", "26"):
        require("| hi" in run("pinctrl", "get", pin), "DRAIN_REQUIRED")


def private(path, data):
    with path.open("xb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("REDIRECT_REJECTED")


def read_api(endpoint, token):
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(
        "http://127.0.0.1:8002/api/v1/lights/" + endpoint,
        headers={"Authorization": "Bearer " + token},
    )
    with client.open(req, timeout=3) as response:
        require(response.status == 200, "HTTP_REJECTED")
        body = response.read(32769)
        require(len(body) <= 32768, "BODY_TOO_LARGE")
    return json.loads(body)


def validate_sources(package, baseline):
    require(set(baseline) == {"models.py", "controller.py"}, "MANIFEST_INVALID")
    for name, item in baseline.items():
        secure(BASE / name)
        require(sha(BASE / name) == item["before"], "BASELINE_CHANGED")
        require(sha(package / name) == item["after"], "PACKAGE_CHANGED")
        compile((package / name).read_bytes(), name, "exec")


def install(package):
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    os.umask(0o077)
    require(
        Path("/proc/device-tree/model").read_bytes().rstrip(b"\0\n")
        == b"Raspberry Pi 4 Model B Rev 1.1",
        "WRONG_HOST",
    )
    require(not os.path.lexists(MARKER), "PRIOR_ATTEMPT_REVIEW_REQUIRED")
    baseline = json.loads((package / "baseline.json").read_text())
    validate_sources(package, baseline)
    secure(ENV)
    require(ENV.stat().st_mode & 0o077 == 0, "ENV_PERMISSIONS")
    values = dict(line.split("=", 1) for line in ENV.read_text().splitlines() if line)
    require(values.get("LIGHT_DB_PATH") == str(DB), "DATABASE_PATH_CHANGED")
    creds = [
        values.get("LIGHT_DISPLAY_TOKEN", ""),
        values.get("LIGHT_SETTINGS_TOKEN", ""),
    ]
    require(
        all(re.fullmatch(r"[A-Za-z0-9_-]{32,512}", x) for x in creds), "TOKEN_FORMAT"
    )
    require(run("systemctl", "is-active", SERVICE) == "active", "SERVICE_NOT_ACTIVE")
    st = read_api("status", creds[0])
    require(
        st.get("health") == "OK"
        and st.get("gpio_on") is False
        and st.get("desired_on") is False,
        "LIGHT_OFF_REQUIRED",
    )
    settings = read_api("settings", creds[1])
    drain_check()
    evidence = Path(tempfile.mkdtemp(prefix="light-cooldown.", dir="/root"))
    os.chmod(evidence, 0o700)
    private(MARKER, str(evidence).encode())
    private(
        evidence / "before.json",
        json.dumps(
            {"baseline": baseline, "environment_sha256": sha(ENV), "settings": settings}
        ).encode(),
    )
    print("BACKUP_DIRECTORY=" + str(evidence), flush=True)
    run("systemctl", "stop", SERVICE)
    require(
        run("systemctl", "show", SERVICE, "--property=ActiveState", "--value")
        == "inactive",
        "STOP_UNCONFIRMED",
    )
    for name in baseline:
        shutil.copy2(BASE / name, evidence / name)
        require(sha(evidence / name) == baseline[name]["before"], "BACKUP_MISMATCH")
    require(DB.is_file() and not DB.is_symlink(), "DATABASE_INVALID")
    with sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True) as source:
        require(
            source.execute("PRAGMA integrity_check").fetchone() == ("ok",),
            "DATABASE_INTEGRITY",
        )
        old_rows = source.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        with sqlite3.connect(evidence / "light.db") as dest:
            source.backup(dest)
            require(
                dest.execute("PRAGMA integrity_check").fetchone() == ("ok",),
                "BACKUP_INTEGRITY",
            )
    private(evidence / "install-started.json", b"{}")
    for name in baseline:
        target = BASE / name
        meta = target.stat()
        fd, temporary = tempfile.mkstemp(prefix=".cooldown-", dir=BASE)
        with os.fdopen(fd, "wb") as f:
            f.write((package / name).read_bytes())
            os.fchmod(f.fileno(), stat.S_IMODE(meta.st_mode))
            os.fchown(f.fileno(), meta.st_uid, meta.st_gid)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, target)
        require(sha(target) == baseline[name]["after"], "INSTALL_HASH_MISMATCH")
    directory = os.open(BASE, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    run("systemctl", "start", SERVICE)
    status = None
    for _ in range(20):
        try:
            status = read_api("status", creds[0])
            break
        except (OSError, ValueError):
            time.sleep(0.25)
    require(status and status.get("health") == "OK", "STATUS_UNCONFIRMED")
    require(read_api("settings", creds[1]) == settings, "SETTINGS_CHANGED")
    before = json.loads((evidence / "before.json").read_text())
    require(sha(ENV) == before["environment_sha256"], "ENV_CHANGED")
    require(run("systemctl", "is-active", SERVICE) == "active", "SERVICE_FAILED")
    drain_check()
    result = {
        "result": "LIGHT_COOLDOWN_INSTALLED",
        "cooldown_seconds": 900,
        "backup": str(evidence),
        "mode": status["mode"],
        "gpio_on": status["gpio_on"],
        "history_rows_before": old_rows,
        "physical_acceptance": "NOT_TESTED",
        "actuator_commands": 0,
    }
    private(evidence / "success.json", json.dumps(result).encode())
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
    except Exception as exc:  # noqa: BLE001 - redact credentials at CLI boundary
        code = (
            str(exc)
            if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Z_]+", str(exc))
            else type(exc).__name__
        )
        print("LIGHT_COOLDOWN_STOPPED=" + code + "; no automatic retry or rollback")
        raise SystemExit(1) from None
