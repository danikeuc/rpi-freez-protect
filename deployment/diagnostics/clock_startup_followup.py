"""Read-only follow-up: clock evidence, Node-RED identity, cached package holds."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "audit", Path(__file__).with_name("startup_software.py")
)
assert spec and spec.loader
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
command, emit = support.command, support.emit
VERSION = re.compile(r"v?[0-9][0-9A-Za-z.+~:_-]{0,100}\Z")
PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.:~-]{0,150}\Z")


def journal_evidence(raw):
    rows, candidates, versions = [], [], []
    previous = None
    parsed = 0
    first_mono = last_mono = None
    patterns = {
        "clock_change": (
            "time jumped",
            "time has been changed",
            "clock was stepped",
            "clock discontinuity",
        ),
        "sync_success": (
            "initial clock synchronization",
            "synchronized to time server",
        ),
        "sync_timeout": ("timed out waiting for reply",),
        "process_failure": ("main process exited", "failed with result"),
        "light_actuator_failure": ("light actuator_failure",),
    }
    for line in raw.splitlines():
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                continue
            message = data.get("MESSAGE", "")
            if not isinstance(message, str):
                continue
            wall = int(data["__REALTIME_TIMESTAMP"])
            mono = int(data["__MONOTONIC_TIMESTAMP"])
            boot = data.get("_BOOT_ID")
            if not isinstance(boot, str) or not re.fullmatch(r"[a-f0-9]{32}", boot):
                continue
            if not (0 <= mono < 10**18 and 0 <= wall < 10**18):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        parsed += 1
        first_mono = mono if first_mono is None else first_mono
        last_mono = mono
        if previous and previous[2] == boot and mono >= previous[1]:
            deviation = ((wall - previous[0]) - (mono - previous[1])) / 1e6
            if abs(deviation) > 5:
                candidates.append(
                    {
                        "before_wall_us": previous[0],
                        "after_wall_us": wall,
                        "sample_gap_seconds": (mono - previous[1]) / 1e6,
                        "wall_minus_monotonic_seconds": deviation,
                    }
                )
        previous = wall, mono, boot
        tags = [
            tag
            for tag, needles in patterns.items()
            if any(n in message.lower() for n in needles)
        ]
        if tags:
            item = {"wall_us": wall, "monotonic_us": mono, "categories": tags}
            match = re.search(
                r"light clock discontinuity wall_delta_s=([-+0-9.e]+) monotonic_delta_s=([-+0-9.e]+)(?:$|\s)",
                message,
            )
            if match:
                try:
                    numbers = [float(v) for v in match.groups()]
                    if all(math.isfinite(n) and abs(n) < 1e12 for n in numbers):
                        item["light_wall_delta_s"], item["light_monotonic_delta_s"] = (
                            numbers
                        )
                except ValueError:
                    pass
            stage = re.search(
                r"light actuator_failure stage=(clock|expiry|renewal) kind=(clock|io_or_validation)(?:$|\s)",
                message,
            )
            if stage:
                item["stage"], item["kind"] = stage.groups()
            rows.append(item)
        ver = re.search(
            r"\b(Node-RED version|Node\.js\s+version)\s*:\s*(v?[0-9][0-9A-Za-z.+~_-]*)(?:$|\s)",
            message,
        )
        if ver:
            versions.append(
                {
                    "component": "node_red"
                    if ver[1] == "Node-RED version"
                    else "node_js",
                    "version": ver[2],
                    "wall_us": wall,
                }
            )
    return {
        "entries_parsed": parsed,
        "first_monotonic_us": first_mono,
        "last_monotonic_us": last_mono,
        "events": rows[-60:],
        "events_truncated": len(rows) > 60,
        "clock_candidates": candidates[-20:],
        "candidates_truncated": len(candidates) > 20,
        "versions_from_logs": versions[-6:],
        "clock_candidate_is_not_causation": True,
    }


def held_packages(raw):
    result = []
    for line in raw.decode(errors="replace").splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == "hold" and PACKAGE.fullmatch(fields[0]):
            result.append(fields[0])
    return result


def upgrade_candidates(raw):
    result = []
    for line in raw.decode(errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 3 or "/" not in fields[0]:
            continue
        name = fields[0].split("/", 1)[0]
        if (
            PACKAGE.fullmatch(name)
            and VERSION.fullmatch(fields[1])
            and "[upgradable from:" in line
        ):
            result.append({"package": name, "candidate": fields[1]})
    return result


def journals():
    groups = {
        "manager_current_boot": ["-b", "_PID=1"],
        "timesync_current_boot": ["-b", "-u", "systemd-timesyncd.service"],
        "light_current_boot": ["-b", "-u", "light-controller.service"],
        "node_red_current_boot": ["-b", "-u", "node-red.service"],
    }
    for group, selector in groups.items():
        meta, raw = command(
            ["journalctl", "--no-pager", "-o", "json", "-n", "4000", *selector],
            timeout=15,
            limit=8 * 1024 * 1024,
        )
        evidence = journal_evidence(raw)
        emit(
            "clock_startup_journal",
            group=group,
            **meta,
            **evidence,
            entry_cap_reached=evidence["entries_parsed"] >= 4000,
            scope="LAST_4000_ENTRIES_CURRENT_BOOT_ONLY",
        )


def node_identity():
    meta, raw = command(
        ["systemctl", "show", "node-red.service", "--property=MainPID", "--value"]
    )
    pid_text = raw.decode(errors="replace").strip()
    if not pid_text.isdigit() or not 1 < int(pid_text) < 10**9:
        emit("node_process_identity", **meta, result="PID_UNAVAILABLE")
        return
    pid = int(pid_text)
    try:
        exe = Path(f"/proc/{pid}/exe").resolve(strict=True)
        # Do not execute a service-owned executable as root or export its arguments.
        with Path(f"/proc/{pid}/cmdline").open("rb") as stream:
            args = stream.read(16385)
        if len(args) > 16384:
            raise ValueError("limit")
        sources = []
        for arg in args.split(b"\0"):
            p = Path(arg.decode(errors="replace"))
            if p.is_absolute() and p.name in ("red.js", "node-red"):
                for base in (p.parent, p.resolve().parent):
                    f = base / "package.json"
                    try:
                        package = json.loads(support.support.read(f, 262144))
                        version = package.get("version", "")
                        if (
                            package.get("name") == "node-red"
                            and isinstance(version, str)
                            and VERSION.fullmatch(version)
                        ):
                            row = {"name": "node-red", "version": version}
                            if row not in sources:
                                sources.append(row)
                    except (OSError, ValueError, TypeError):
                        continue
        emit(
            "node_process_identity",
            pid=pid,
            executable_name=exe.name if exe.name in ("node", "nodejs") else "OTHER",
            executable_outside_standard_search_path=str(exe.parent)
            not in ("/usr/bin", "/usr/sbin", "/bin", "/sbin"),
            package_metadata=sources,
            executable_invoked=False,
        )
    except (OSError, ValueError):
        emit("node_process_identity", result="UNAVAILABLE_OR_PROCESS_CHANGED")


def packages():
    meta, raw = command(["dpkg", "--get-selections"], timeout=30)
    holds = held_packages(raw)
    emit("dpkg_holds", **meta, packages=holds[:100], truncated=len(holds) > 100)
    list_meta, raw = command(
        ["apt", "list", "--upgradable"], timeout=30, limit=2 * 1024 * 1024
    )
    available = upgrade_candidates(raw)
    sim_meta, raw = command(
        ["apt-get", "-s", "-o", "Debug::NoLocking=1", "upgrade"],
        timeout=30,
        limit=2 * 1024 * 1024,
    )
    sim = support.simulation(raw)
    planned = {i["package"] for i in sim["changes"] if i["action"] == "Inst"}
    complete = (
        list_meta.get("exit") == 0
        and not list_meta.get("limit")
        and sim_meta.get("exit") == 0
        and not sim_meta.get("limit")
        and not sim["changes_truncated"]
    )
    emit(
        "cached_upgrade_gap",
        list_result=list_meta,
        simulation_result=sim_meta,
        summary=sim["summary"],
        unplanned_candidates=[i for i in available if i["package"] not in planned]
        if complete
        else None,
        reason="NOT_DETERMINED",
        indexes_refreshed=False,
    )


def time_configuration():
    for prop in ("Timezone", "NTP", "NTPSynchronized", "LocalRTC"):
        meta, raw = command(["timedatectl", "show", "--property=" + prop])
        emit(
            "time_property", **meta, properties=support.support.properties(raw, {prop})
        )
    for name in (
        "/boot/dietpi/func/dietpi-timesync",
        "/etc/cron.daily/dietpi",
        "/etc/crontab",
    ):
        try:
            data = support.support.read(name, 262144)
            # No script/cron commands, addresses or environment values are exported.
            emit(
                "time_schedule_source",
                file=name,
                text_sha256=hashlib.sha256(data.encode()).hexdigest(),
                references_timesync="dietpi-timesync" in data,
                stops_timesyncd="systemctl stop systemd-timesyncd" in data,
                schedules=[
                    list(m.groups())
                    for m in re.finditer(
                        r"(?m)^([0-9*]+)\s+([0-9*]+)\s+([0-9*]+)\s+([0-9*]+)\s+([0-9*]+)\s+root\s+.*run-parts.*cron\.daily",
                        data,
                    )
                ],
            )
        except (OSError, ValueError):
            emit("time_schedule_source", file=name, available=False)


def main():
    emit(
        "scope",
        kind="CLOCK_STARTUP_FOLLOWUP",
        actuator_commands=0,
        configuration_writes=0,
        upgrades_performed=0,
        apt_indexes_refreshed=False,
    )
    for collect in (journals, node_identity, packages, time_configuration):
        try:
            collect()
        except Exception as exc:  # noqa: BLE001
            emit(
                "collector_failure",
                collector=collect.__name__,
                error_type=type(exc).__name__,
            )
    emit("complete", result="CLOCK_STARTUP_FOLLOWUP_COMPLETE")


if __name__ == "__main__":
    main()
