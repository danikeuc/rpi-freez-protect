"""One reviewed continuation of the asf8pjxk pre-stop timeout; not a general retry."""

import argparse
import fcntl
import importlib.util
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "diagnostics_install", HERE / "install_diagnostics.py"
)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
support = installer.support
require = support.require
PRIOR = Path("/root/controller-fault-diagnostics.asf8pjxk")


def review(package):
    support.secure(PRIOR)
    support.secure(installer.MARKER)
    require(installer.MARKER.read_text() == str(PRIOR), "OTHER_ATTEMPT")
    for name in (
        "stop-started.json",
        "install-started.json",
        "success.json",
        "reviewed-started-marker",
        "continuation-reviewed.json",
    ):
        require(not os.path.lexists(PRIOR / name), "ATTEMPT_NOT_PRE_STOP")
    support.secure(PRIOR / "before.json")
    before = json.loads((PRIOR / "before.json").read_text())
    manifest = json.loads((package / "baseline.json").read_text())
    require(before["source"] == manifest, "BASELINE_RECORD_CHANGED")
    installer.validate_sources(package, manifest)
    for name in manifest:
        support.secure(PRIOR / name)
        require(support.sha(PRIOR / name) == manifest[name]["before"], "BACKUP_CHANGED")
    require(
        before["environment_hashes"]
        == {str(f): support.sha(f) for f in (support.ENV, support.SHOWER_ENV)},
        "ENV_CHANGED",
    )
    api = support.API(
        support.environment(support.ENV), support.environment(support.SHOWER_ENV)
    )
    support.active_units()
    installer.preflight(
        api("light", "status"), api("shower", "display/status"), minimum=600
    )
    require(api("light", "settings") == before["settings"], "SETTINGS_CHANGED")
    support.drain_check()
    installer.durable_off(support.DB, support.SHOWER_DB, minimum=600)
    return {
        "review": "PRE_STOP_ONLY_VERIFIED",
        "prior": str(PRIOR),
        "baseline_unchanged": True,
    }


def continue_locked(package):
    result = review(package)
    # Preserve both old evidence and its marker. This is a single explicit continuation.
    support.private(PRIOR / "continuation-reviewed.json", json.dumps(result).encode())
    os.rename(installer.MARKER, PRIOR / "reviewed-started-marker")
    for directory in (installer.MARKER.parent, PRIOR):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    print(
        "PREVIOUS_ATTEMPT_REVIEWED; unchanged sources; prior backup preserved",
        flush=True,
    )
    installer.install_locked(package)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loads-disconnected", action="store_true")
    args = parser.parse_args()
    require(
        args.loads_disconnected and os.geteuid() == 0,
        "ROOT_AND_DISCONNECTED_LOADS_REQUIRED",
    )
    os.umask(0o077)
    require(
        Path("/proc/device-tree/model").read_bytes().rstrip(b"\0\n")
        == b"Raspberry Pi 4 Model B Rev 1.1",
        "WRONG_HOST",
    )
    support.secure(HERE)
    support.secure(installer.SUPPORT)
    support.secure(support.LOCK.parent)
    fd = os.open(support.LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+"):
        support.secure(support.LOCK)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        continue_locked(HERE)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never expose raw private errors
        code = (
            str(exc)
            if isinstance(exc, RuntimeError) and re.fullmatch(r"[A-Z_]+", str(exc))
            else type(exc).__name__
        )
        print(
            "DIAGNOSTICS_CONTINUATION_STOPPED="
            + code
            + "; no automatic retry or rollback"
        )
        raise SystemExit(1) from None
