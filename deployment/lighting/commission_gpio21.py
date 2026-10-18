"""Bounded disconnected-load GPIO21 bench; never writes GPIO20/26."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import mmap
import os
import re
import select
import stat
import struct
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

PYTHON = "/opt/freeze-protect-paired-gpio/venv-2.3.0/bin/python3"
PAIR = Path("/opt/rpi-freez-protect/deployment/node-red/paired_gpio_daemon.py")
PAIR_HASH = "ef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f"
LOCK = Path("/root/light-gpio21-commissioning.started")


def require(value, code):
    if not value:
        raise RuntimeError(code)


def approval(valves, light):
    require(valves is True and light is True, "BOTH_LOADS_MUST_BE_DISCONNECTED")


def decode(fsel, levels):
    return {
        str(pin): {
            "level": (levels >> pin) & 1,
            "function": (fsel >> ((pin - 20) * 3)) & 7,
        }
        for pin in (20, 21, 26)
    }


def check_sample(sample, light_level, released=False):
    require(
        all(sample[str(pin)] == {"level": 1, "function": 1} for pin in (20, 26)),
        "PAIRED_DRAIN_CHANGED",
    )
    require(sample["21"]["level"] == light_level, "LIGHT_LEVEL_MISMATCH")
    require(
        sample["21"]["function"] in ((0, 1) if released else (1,)),
        "LIGHT_FUNCTION_MISMATCH",
    )


class Sampler:
    def __init__(self):
        self.fd = os.open("/dev/gpiomem", os.O_RDONLY | os.O_CLOEXEC)
        self.mapping = mmap.mmap(self.fd, 4096, access=mmap.ACCESS_READ)
        self.rows = []

    def read(self, label):
        fsel = struct.unpack_from("<I", self.mapping, 8)[0]
        levels = struct.unpack_from("<I", self.mapping, 0x34)[0]
        value = decode(fsel, levels)
        self.rows.append({"monotonic": time.monotonic(), "phase": label, "pins": value})
        return value

    def watch(self, label, duration, light_level, released=False):
        until = time.monotonic() + duration
        while True:
            check_sample(self.read(label), light_level, released)
            if time.monotonic() >= until:
                return
            time.sleep(0.002)

    def close(self):
        self.mapping.close()
        os.close(self.fd)


def worker_session(gpiod, line, receive, emit):
    request = gpiod.request_lines(
        "/dev/gpiochip0",
        consumer="light-commissioning-gpio21",
        config={
            21: gpiod.LineSettings(
                direction=line.Direction.OUTPUT,
                active_low=True,
                output_value=line.Value.INACTIVE,
            )
        },
    )
    try:
        require(request.get_value(21) == line.Value.INACTIVE, "INITIAL_OFF_READBACK")
        emit("off")
        while True:
            command = receive()
            if command == "close":
                return
            require(command in ("on", "off"), "UNKNOWN_WORKER_COMMAND")
            value = line.Value.ACTIVE if command == "on" else line.Value.INACTIVE
            request.set_value(21, value)
            require(request.get_value(21) == value, "WORKER_READBACK")
            emit(command)
    finally:
        try:
            request.set_value(21, line.Value.INACTIVE)
        finally:
            request.release()


def worker():
    import gpiod
    import gpiod.line

    def receive():
        require(bool(select.select([sys.stdin], [], [], 2)[0]), "WORKER_IDLE_TIMEOUT")
        value = sys.stdin.readline(16)
        return "close" if not value else value.strip()

    worker_session(gpiod, gpiod.line, receive, lambda ack: print(ack, flush=True))


class Child:
    def __init__(self):
        self.process = subprocess.Popen(
            [PYTHON, "-I", "-B", str(Path(__file__).resolve()), "--worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )

    def ack(self, expected):
        fd = self.process.stdout.fileno()
        deadline, data = time.monotonic() + 2, b""
        while b"\n" not in data:
            remaining = deadline - time.monotonic()
            require(
                remaining > 0 and select.select([fd], [], [], remaining)[0],
                "WORKER_TIMEOUT",
            )
            chunk = os.read(fd, 32)
            require(chunk and len(data) + len(chunk) <= 32, "WORKER_FRAME")
            data += chunk
        require(data == (expected + "\n").encode(), "WORKER_ACK")

    def command(self, value):
        self.process.stdin.write((value + "\n").encode())
        self.process.stdin.flush()

    def finish(self, crash=False):
        if self.process.poll() is None:
            if crash:
                self.process.kill()
            else:
                self.command("close")
        try:
            code = self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
            raise RuntimeError("WORKER_EXIT_TIMEOUT") from None
        finally:
            self.process.stdin.close()
            self.process.stdout.close()
        require(code == (-9 if crash else 0), "WORKER_EXIT")


def secure(path):
    for part in (path, *path.parents):
        info = part.lstat()
        require(
            not stat.S_ISLNK(info.st_mode)
            and info.st_uid == 0
            and not info.st_mode & 0o022,
            "UNTRUSTED_INPUT",
        )


def checks():
    path = Path(__file__).with_name("operator_checks.py").resolve()
    secure(path)
    spec = importlib.util.spec_from_file_location("operator_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight(c):
    import gpiod

    require(os.geteuid() == 0, "ROOT_DIETPI_REQUIRED")
    require(
        Path("/proc/device-tree/model").read_bytes().rstrip(b"\0\n")
        == b"Raspberry Pi 4 Model B Rev 1.1",
        "WRONG_HOST",
    )
    require(importlib.metadata.version("gpiod") == "2.3.0", "GPIOD_VERSION")
    secure(PAIR)
    require(
        hashlib.sha256(PAIR.read_bytes()).hexdigest() == PAIR_HASH,
        "PAIRED_BASELINE_CHANGED",
    )
    require(c.active(c.PAIR) and c.active(c.HUB), "SERVICES_REQUIRED")
    c.status(c.config())
    c.persistent_stop()
    c.pair_high()
    c.flow()
    with gpiod.Chip("/dev/gpiochip0") as chip:
        require(chip.get_info().name == "gpiochip0", "CHIP_IDENTITY")
        for pin in (20, 26):
            info = chip.get_line_info(pin)
            require(
                info.used
                and info.consumer == "freeze-protect-pair"
                and info.name == "GPIO" + str(pin),
                "PAIRED_OWNERSHIP",
            )
        info = chip.get_line_info(21)
        require(not info.used and info.name == "GPIO21", "GPIO21_BUSY_OR_UNKNOWN")


def bench(sampler):
    for crash in (False, True):
        child = Child()
        try:
            child.ack("off")
            sampler.watch("startup_off", 0.15, 1)
            child.command("on")
            child.ack("on")
            sampler.watch("on_before_crash" if crash else "on", 0.5, 0)
            if not crash:
                child.command("off")
                child.ack("off")
                sampler.watch("command_off", 0.15, 1)
            child.finish(crash=crash)
            sampler.watch(
                "crash_release" if crash else "normal_release", 0.3, 1, released=True
            )
        finally:
            if child.process.poll() is None:
                child.finish(crash=True)


def restore_off(sampler):
    child = Child()
    try:
        child.ack("off")
        sampler.watch("final_owned_off", 0.1, 1)
        child.finish()
        sampler.watch("final_released_off", 0.1, 1, released=True)
    finally:
        if child.process.poll() is None:
            child.finish(crash=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--valves-disconnected", action="store_true")
    parser.add_argument("--lamp-disconnected", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    os.umask(0o077)
    if args.worker:
        worker()
        return 0
    evidence, sampler, started = None, None, False
    code, off = "PREFLIGHT", False
    try:
        approval(args.valves_disconnected, args.lamp_disconnected)
        secure(Path(__file__).resolve())
        evidence = Path(tempfile.mkdtemp(prefix="light-gpio21-bench.", dir="/root"))
        c = checks()
        c.LOG = evidence / "private.log"
        preflight(c)
        sampler = Sampler()
        # No new run after a previous hardware attempt without explicit local review.
        c.durable(LOCK, str(evidence))
        started = True
        try:
            bench(sampler)
        finally:
            restore_off(sampler)
            off = True
        preflight(c)
        code = "GPIO21_DISCONNECTED_DRIVER_PASS"
        result = 0
    except BaseException as error:  # noqa: BLE001 - preserve cleanup receipt on interruption
        text = str(error)
        code = (
            text
            if re.fullmatch(r"[A-Z0-9_]{1,80}", text)
            else "INSPECT_PRIVATE_EVIDENCE"
        )
        result = 1
        if evidence:
            (evidence / "diagnostic.json").write_text(
                json.dumps(
                    {
                        "error_type": type(error).__name__,
                        "frames": [
                            {"file": Path(frame.filename).name, "line": frame.lineno}
                            for frame in traceback.extract_tb(error.__traceback__)
                        ],
                    }
                )
            )
    finally:
        receipt = {
            "result": code,
            "attempted_gpio21": started,
            "final_off_readback": off,
            "physical_acceptance": "NOT_VERIFIED",
            "automation_enabled": False,
            "evidence": str(evidence) if evidence else None,
        }
        if evidence:
            if sampler:
                (evidence / "samples.json").write_text(json.dumps(sampler.rows))
            (evidence / "receipt.json").write_text(json.dumps(receipt))
        if sampler:
            sampler.close()
        print(json.dumps(receipt))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
