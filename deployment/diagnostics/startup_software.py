"""Read-only startup/package audit using existing APT indexes. Never upgrades."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import time
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "snapshot_support", Path(__file__).with_name("dietpi_snapshot.py")
)
assert SPEC and SPEC.loader
support = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(support)
emit, command = support.emit, support.command
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_:~@-]{0,150}\Z")
UNIT = re.compile(
    r"[A-Za-z0-9_.@:-]+\.(?:service|target|socket|timer|mount|device|slice|path)\Z"
)
CORE = (
    "freeze-protect.service",
    "freeze-protect-pair-gpio.service",
    "node-red.service",
    "light-controller.service",
    "light-gpio.service",
    "ssh.service",
    "nginx.service",
)


def packages(raw):
    items = []
    total = 0
    for line in raw.decode(errors="replace").splitlines():
        columns = line.split("\t")
        if len(columns) != 3 or columns[2] != "installed":
            continue
        total += 1
        name, version = columns[:2]
        if (
            TOKEN.fullmatch(name)
            and TOKEN.fullmatch(version)
            and name.startswith(
                (
                    "linux-image",
                    "linux-headers",
                    "raspberrypi",
                    "raspi",
                    "rpi-",
                    "python3",
                    "nodejs",
                    "npm",
                    "nodered",
                    "systemd",
                    "openssh",
                    "nginx",
                    "openssl",
                    "libssl",
                    "curl",
                    "ca-certificates",
                    "chrony",
                    "apt",
                    "libgpiod",
                    "sudo",
                )
            )
        ):
            items.append({"name": name, "version": version})
    return {
        "installed_count": total,
        "selected": items[:150],
        "selected_truncated": len(items) > 150,
    }


def simulation(raw):
    changes = []
    counts = {"Inst": 0, "Remv": 0, "Conf": 0}
    summary = None
    for line in raw.decode(errors="replace").splitlines():
        match = re.match(r"^(Inst|Remv|Conf) ([a-z0-9][a-z0-9+.:~-]*)", line)
        if match:
            action, name = match.groups()
            counts[action] += 1
            if action == "Conf":
                continue
            old = re.search(r" \[([^] ]+)\]", line)
            new = re.search(r" \(([^ )]+)", line)
            changes.append(
                {
                    "action": action,
                    "package": name,
                    "installed": old[1] if old and TOKEN.fullmatch(old[1]) else None,
                    "candidate": new[1] if new and TOKEN.fullmatch(new[1]) else None,
                    "security_origin_hint": "security" in line.lower(),
                }
            )
        elif re.fullmatch(
            r"[0-9]+ upgraded, [0-9]+ newly installed, [0-9]+ to remove and [0-9]+ not upgraded\.",
            line,
        ):
            summary = line
    return {
        "counts": counts,
        "changes": changes[:100],
        "changes_truncated": len(changes) > 100,
        "summary": summary,
    }


def startup():
    props = (
        "LoadState",
        "ActiveState",
        "SubState",
        "UnitFileState",
        "Restart",
        "NRestarts",
        "Type",
        "User",
        "After",
        "Requires",
        "Wants",
        "BindsTo",
        "TimeoutStartUSec",
        "TimeoutStopUSec",
        "ActiveEnterTimestampMonotonic",
        "ExecStartPre",
        "NeedDaemonReload",
    )
    for unit in CORE:
        meta, raw = command(
            ["systemctl", "show", unit, "--no-pager", "--property=" + ",".join(props)]
        )
        data = {}
        for line in raw.decode(errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if not sep or key not in props:
                continue
            if key == "ExecStartPre":
                data["pre_start_check_present"] = bool(value)
            elif key in ("After", "Requires", "Wants", "BindsTo"):
                data[key] = [v for v in value.split() if UNIT.fullmatch(v)][:100]
            elif re.fullmatch(r"[A-Za-z0-9_.:@ /-]{0,100}", value):
                data[key] = value
        emit("startup_unit", unit=unit, **meta, properties=data)
    meta, raw = command(["systemd-analyze", "time"])
    # Fixed-format timings only; no command lines/environment fields.
    lines = [
        l
        for l in raw.decode(errors="replace").splitlines()
        if l.startswith(
            (
                "Startup finished in ",
                "graphical.target reached after ",
                "multi-user.target reached after ",
            )
        )
        and re.fullmatch(r"[A-Za-z0-9 .()+:=/-]{1,400}", l)
    ]
    emit("boot_time", **meta, timing_lines=lines[:4])
    meta, raw = command(["systemd-analyze", "blame", "--no-pager"])
    rows = []
    for line in raw.decode(errors="replace").splitlines():
        fields = line.split()
        if (
            fields
            and UNIT.fullmatch(fields[-1])
            and all(re.fullmatch(r"[0-9.]+(?:ms|s|min|h|us)", v) for v in fields[:-1])
        ):
            rows.append({"unit": fields[-1], "duration": " ".join(fields[:-1])})
    emit(
        "activation_durations",
        **meta,
        largest=rows[:20],
        note="activation durations can include later restarts",
    )
    for unit in (
        "apt-daily.timer",
        "apt-daily-upgrade.timer",
        "dietpi-postboot.service",
        "cron.service",
    ):
        meta, raw = command(
            [
                "systemctl",
                "show",
                unit,
                "--no-pager",
                "--property=LoadState,ActiveState,UnitFileState,LastTriggerUSec,NextElapseUSecRealtime,Result",
            ]
        )
        emit(
            "maintenance_unit",
            unit=unit,
            **meta,
            properties=support.properties(
                raw,
                {
                    "LoadState",
                    "ActiveState",
                    "UnitFileState",
                    "LastTriggerUSec",
                    "NextElapseUSecRealtime",
                    "Result",
                },
            ),
        )


def software():
    meta, raw = command(
        ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n"],
        limit=2 * 1024 * 1024,
    )
    emit("packages", **meta, **packages(raw))
    meta, raw = command(["apt-mark", "showhold"])
    emit(
        "apt_holds",
        **meta,
        packages=[
            v for v in raw.decode(errors="replace").split() if TOKEN.fullmatch(v)
        ][:100],
    )
    paths = [f for f in Path("/var/lib/apt/lists").glob("*InRelease") if f.is_file()]
    ages = [round((time.time() - f.stat().st_mtime) / 3600, 2) for f in paths]
    stamp = Path("/var/lib/apt/periodic/update-success-stamp")
    emit(
        "apt_index_age",
        inrelease_count=len(paths),
        oldest_hours=max(ages) if ages else None,
        newest_hours=min(ages) if ages else None,
        update_success_stamp_age_hours=round(
            (time.time() - stamp.stat().st_mtime) / 3600, 2
        )
        if stamp.exists()
        else None,
        freshness="NOT_REFRESHED_BY_AUDIT",
        mtime_is_not_proof_all_sources_succeeded=True,
    )
    meta, raw = command(
        ["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"],
        timeout=25,
        limit=2 * 1024 * 1024,
    )
    emit(
        "apt_upgrade_simulation",
        **meta,
        **simulation(raw),
        based_on="EXISTING_LOCAL_INDEXES",
    )
    for program in ("node", "npm", "python3", "nginx"):
        if program == "nginx":
            continue  # package inventory includes nginx; -v writes stderr
        meta, raw = command([program, "--version"])
        value = raw.decode(errors="replace").strip()
        emit(
            "runtime_version",
            program=program,
            **meta,
            version=value
            if re.fullmatch(r"(?:Python )?v?[0-9][0-9a-zA-Z.+~-]{0,50}", value)
            else None,
        )
    for path in (
        "/usr/lib/node_modules/node-red/package.json",
        "/usr/local/lib/node_modules/node-red/package.json",
    ):
        try:
            data = json.loads(support.read(path))
            v = data.get("version", "")
            emit(
                "node_red_package",
                path=path,
                version=v if isinstance(v, str) and TOKEN.fullmatch(v) else None,
            )
        except (OSError, ValueError):
            pass
    for root in (
        "/opt/rpi-freez-protect/.venv/lib/python3.13/site-packages",
        "/opt/independent-light/venv/lib/python3.13/site-packages",
    ):
        versions = []
        for f in Path(root).glob("*.dist-info/METADATA"):
            try:
                # Read metadata as text; never import installed application code.
                data = support.read(f, 262144)
                name = re.search(r"^Name: (.+)$", data, re.MULTILINE)
                ver = re.search(r"^Version: (.+)$", data, re.MULTILINE)
                if (
                    name
                    and ver
                    and TOKEN.fullmatch(name[1])
                    and TOKEN.fullmatch(ver[1])
                ):
                    versions.append({"name": name[1], "version": ver[1]})
            except (OSError, ValueError):
                continue
        emit(
            "python_environment",
            path=root,
            exists=Path(root).is_dir(),
            packages=sorted(versions, key=lambda x: x["name"])[:100],
            metadata_is_not_source_integrity=True,
        )


def identities():
    files = (
        "/opt/rpi-freez-protect/.venv/lib/python3.13/site-packages/freeze_protect/adapters/node_red.py",
        "/opt/independent-light/venv/lib/python3.13/site-packages/freeze_protect/lighting/controller.py",
        "/etc/systemd/system/freeze-protect.service",
        "/etc/systemd/system/freeze-protect.service.d/30-node-red-readiness.conf",
        "/etc/systemd/system/freeze-protect-pair-gpio.service",
        "/etc/systemd/system/light-controller.service",
        "/etc/systemd/system/light-gpio.service",
    )
    for name in files:
        try:
            with Path(name).open("rb") as stream:
                data = stream.read(1048577)
            if len(data) > 1048576:
                raise ValueError("size limit")
            emit("artifact_hash", path=name, sha256=hashlib.sha256(data).hexdigest())
        except (OSError, ValueError):
            emit("artifact_hash", path=name, available=False)
    try:
        values = {}
        for line in support.read("/boot/dietpi.txt", 131072).splitlines():
            m = re.fullmatch(
                r"(CONFIG_NTP_MODE|CONFIG_CHECK_APT_UPDATES|CONFIG_CHECK_DIETPI_UPDATES)=([0-4])",
                line,
            )
            if m:
                values[m[1]] = int(m[2])
        emit("automatic_maintenance_settings", **values)
    except OSError:
        emit("automatic_maintenance_settings", available=False)


def main():
    emit(
        "scope",
        kind="STARTUP_SOFTWARE_AUDIT",
        configuration_writes=0,
        actuator_commands=0,
        upgrades_performed=0,
        apt_indexes_refreshed=False,
    )
    for collect in (startup, software, identities):
        try:
            collect()
        except Exception as exc:  # noqa: BLE001 - no raw exception output
            emit(
                "collector_failure",
                collector=collect.__name__,
                error_type=type(exc).__name__,
            )
    emit("complete", result="STARTUP_SOFTWARE_AUDIT_COMPLETE")


if __name__ == "__main__":
    main()
