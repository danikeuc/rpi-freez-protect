"""Bounded read-only DietPi health snapshot. No raw journal or environment export."""

from __future__ import annotations

import json
import os
import platform
import re
import selectors
import shutil
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

UNITS = (
    "ssh.service",
    "nginx.service",
    "node-red.service",
    "freeze-protect.service",
    "freeze-protect-pair-gpio.service",
    "light-controller.service",
    "light-gpio.service",
    "systemd-timesyncd.service",
    "chrony.service",
    "systemd-networkd.service",
    "NetworkManager.service",
    "networking.service",
)
PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "Result",
    "NRestarts",
    "ExecMainStatus",
    "MemoryCurrent",
    "TasksCurrent",
    "NeedDaemonReload",
    "ActiveEnterTimestampMonotonic",
)
PATTERNS = {
    "oom": ("out of memory", "oom-kill", "killed process"),
    "storage_io": (
        "i/o error",
        "buffer i/o",
        "mmc timeout",
        "ext4-fs error",
        "blk_update_request",
    ),
    "filesystem_readonly": ("remounting filesystem read-only", "read-only file system"),
    "disk_full": ("no space left on device",),
    "undervoltage": ("under-voltage", "undervoltage"),
    "thermal": ("critical temperature", "thermal throttling", "over-temperature"),
    "kernel_fault": (
        "kernel panic",
        "kernel oops",
        "watchdog: bug",
        "soft lockup",
        "hung task",
    ),
    "clock_change": (
        "time jumped",
        "clock discontinuity",
        "clock was stepped",
        "time has been changed",
    ),
    "service_failure": (
        "main process exited",
        "failed with result",
        "start request repeated too quickly",
    ),
    "network_link": ("link is down", "carrier lost", "lost carrier", "dhcp lease lost"),
    "auth_failure": ("failed password", "authentication failure", "failed publickey"),
    "controller_failure": (
        "actuator_failure",
        "startup_drain_failed",
        "clock_or_lease_fault",
    ),
}


def emit(section, **data):
    print(json.dumps({"section": section, **data}, ensure_ascii=True), flush=True)


def read(path, limit=32768):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("size limit")
    return data.decode("utf-8", errors="replace").strip()


def number(path):
    try:
        return int(read(path, 128))
    except (OSError, ValueError):
        return None


def command(args, timeout=6, limit=1048576):
    binary = shutil.which(args[0], path="/usr/sbin:/usr/bin:/sbin:/bin")
    if not binary:
        return {"available": False}, b""
    with subprocess.Popen(
        [binary, *args[1:]],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"},
        cwd="/",
    ) as proc:
        assert proc.stdout
        output = bytearray()
        deadline = time.monotonic() + timeout
        stopped = None
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    stopped = "TIMEOUT"
                    break
                ready = selector.select(min(left, 0.2))
                if not ready:
                    continue
                block = os.read(
                    proc.stdout.fileno(), min(65536, limit + 1 - len(output))
                )
                if not block:
                    break
                output.extend(block)
                if len(output) > limit:
                    stopped = "OUTPUT_LIMIT"
                    break
        if stopped:
            proc.kill()
        try:
            code = proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait()
        return {"available": True, "exit": code, "limit": stopped}, bytes(
            output[:limit]
        )


def properties(raw, allowed):
    result = {}
    for line in raw.decode(errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if sep and key in allowed and re.fullmatch(r"[A-Za-z0-9_.:+ /-]{1,100}", value):
            result[key] = value
    return result


def journal_summary(raw):
    counts, first, last = Counter(), {}, {}
    malformed = 0
    entries = 0
    for line in raw.splitlines():
        try:
            row = json.loads(line)
            message = row.get("MESSAGE", "")
            if not isinstance(message, str):
                continue
            entries += 1
            message = message.lower()
            stamp = str(row.get("__REALTIME_TIMESTAMP", ""))
            stamp = int(stamp) if stamp.isdigit() and len(stamp) <= 20 else None
            for name, patterns in PATTERNS.items():
                if any(pattern in message for pattern in patterns):
                    counts[name] += 1
                    if stamp is not None:
                        first[name] = min(first.get(name, stamp), stamp)
                        last[name] = max(last.get(name, stamp), stamp)
        except (ValueError, TypeError, AttributeError):
            malformed += 1
    return {
        "entries_read": entries,
        "malformed": malformed,
        "categories": dict(counts),
        "first_us": first,
        "last_us": last,
        "raw_messages_exported": False,
    }


def system():
    release = properties(
        read("/etc/os-release").replace('"', "").encode(),
        {"ID", "VERSION_ID", "PRETTY_NAME"},
    )
    dietpi = {}
    try:
        for line in read("/boot/dietpi/.version").splitlines():
            key, _, value = line.partition("=")
            if (
                key
                in {
                    "G_DIETPI_VERSION_CORE",
                    "G_DIETPI_VERSION_SUB",
                    "G_DIETPI_VERSION_RC",
                }
                and value.isdigit()
            ):
                dietpi[key] = int(value)
    except OSError:
        pass
    emit(
        "system",
        utc=datetime.now(UTC).isoformat(),
        kernel=platform.release(),
        architecture=platform.machine(),
        os=release,
        dietpi=dietpi,
        uptime_seconds=float(read("/proc/uptime").split()[0]),
        load_average=list(os.getloadavg()),
        logical_cpus=os.cpu_count(),
        model=read("/proc/device-tree/model", 256).strip("\0"),
    )
    memory = {}
    for line in read("/proc/meminfo").splitlines():
        name, _, value = line.partition(":")
        if name in {
            "MemTotal",
            "MemAvailable",
            "SwapTotal",
            "SwapFree",
            "Dirty",
            "Writeback",
        }:
            memory[name + "_kib"] = int(value.split()[0])
    emit("memory", **memory)
    for name in ("cpu", "memory", "io"):
        try:
            values = read("/proc/pressure/" + name, 1024)
            emit(
                "pressure",
                resource=name,
                data=values if re.fullmatch(r"[a-z0-9=. \n]+", values) else "INVALID",
            )
        except OSError:
            emit("pressure", resource=name, available=False)
    emit(
        "temperature", cpu_millicelsius=number("/sys/class/thermal/thermal_zone0/temp")
    )
    meta, raw = command(["vcgencmd", "get_throttled"])
    match = re.fullmatch(rb"throttled=(0x[0-9a-fA-F]+)\s*", raw)
    emit(
        "power_throttling",
        **meta,
        raw_mask=match[1].decode() if match else None,
        historical_flags_are_not_current_fault_proof=True,
    )


def storage():
    for name in (
        "/",
        "/boot",
        "/var/lib/rpi-freeze-protect",
        "/var/lib/independent-light",
    ):
        try:
            info = os.statvfs(name)
            emit(
                "storage",
                path=name,
                total_bytes=info.f_blocks * info.f_frsize,
                available_bytes=info.f_bavail * info.f_frsize,
                inode_total=info.f_files,
                inode_available=info.f_favail,
                readonly=bool(info.f_flag & os.ST_RDONLY),
            )
        except OSError:
            emit("storage", path=name, available=False)
    meta, raw = command(["dpkg", "--audit"])
    emit("package_audit", **meta, findings_present=bool(raw.strip()))
    emit("reboot_marker", present=Path("/run/reboot-required").exists())


def services():
    meta, raw = command(
        ["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"]
    )
    names = [
        line.split()[0]
        for line in raw.decode(errors="replace").splitlines()
        if line.split()
    ]
    emit(
        "failed_units",
        **meta,
        units=[n for n in names if re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", n)][:100],
    )
    for unit in UNITS:
        meta, raw = command(
            [
                "systemctl",
                "show",
                unit,
                "--no-pager",
                "--property=" + ",".join(PROPERTIES),
            ]
        )
        emit("unit", unit=unit, **meta, properties=properties(raw, set(PROPERTIES)))
    meta, raw = command(
        [
            "timedatectl",
            "show",
            "--property=NTPSynchronized",
            "--property=NTP",
            "--property=Timezone",
            "--property=LocalRTC",
        ]
    )
    emit(
        "clock",
        **meta,
        properties=properties(raw, {"NTPSynchronized", "NTP", "Timezone", "LocalRTC"}),
    )
    for name, args in (
        ("sshd_syntax", ["sshd", "-t"]),
        ("sudoers_syntax", ["visudo", "-c"]),
    ):
        meta, _ = command(args)
        emit(name, **meta)


def network():
    for interface in sorted(Path("/sys/class/net").iterdir()):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", interface.name):
            continue
        try:
            state = read(interface / "operstate", 32)
            stats = {
                name: number(interface / "statistics" / name)
                for name in (
                    "rx_errors",
                    "tx_errors",
                    "rx_dropped",
                    "tx_dropped",
                    "rx_packets",
                    "tx_packets",
                )
            }
            emit(
                "network_interface",
                name=interface.name,
                state=state
                if state
                in {
                    "up",
                    "down",
                    "unknown",
                    "dormant",
                    "lowerlayerdown",
                    "notpresent",
                    "testing",
                }
                else "OTHER",
                counters=stats,
            )
        except OSError:
            emit("network_interface", name=interface.name, available=False)
    meta, raw = command(["ss", "-H", "-ltn"])
    bindings = []
    for line in raw.decode(errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        host, _, port = fields[3].rpartition(":")
        if not port.isdigit():
            continue
        scope = (
            "loopback"
            if host in ("127.0.0.1", "[::1]", "::1")
            else "wildcard"
            if host in ("*", "0.0.0.0", "[::]", "::")
            else "specific_address"
        )
        bindings.append({"port": int(port), "scope": scope})
    emit("tcp_listeners", **meta, bindings=bindings[:100], addresses_exported=False)


def journals():
    for label, flags in (
        ("kernel_this_boot", ["-k", "-b"]),
        ("system_last_24h", ["--since", "24 hours ago"]),
    ):
        meta, raw = command(
            ["journalctl", "--no-pager", "-o", "json", "-n", "3000", *flags],
            timeout=10,
            limit=4 * 1024 * 1024,
        )
        emit("journal", window=label, **meta, **journal_summary(raw), max_entries=3000)


def main():
    emit(
        "scope",
        version=1,
        root=os.geteuid() == 0,
        configuration_writes=0,
        actuator_commands=0,
        limitations=[
            "snapshot only",
            "bounded journals",
            "no SMART media test",
            "no physical load test",
            "no network throughput test",
        ],
    )
    for collect in (system, storage, services, network, journals):
        try:
            collect()
        except Exception as exc:  # noqa: BLE001 - no raw exception messages
            emit(
                "collector_failure",
                collector=collect.__name__,
                error_type=type(exc).__name__,
            )
    emit("complete", result="DIETPI_READ_ONLY_SNAPSHOT_COMPLETE")


if __name__ == "__main__":
    main()
