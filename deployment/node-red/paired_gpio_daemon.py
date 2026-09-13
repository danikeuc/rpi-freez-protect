#!/usr/bin/env python3
"""Exclusive, atomic GPIO 20/26 executor for the paired-valve bridge."""

from __future__ import annotations

import argparse
import json
import math
import mmap
import os
import socket
import struct
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

PINS = (26, 20)
PAIR_MASK = sum(1 << pin for pin in PINS)
FSEL2 = 0x08
GPSET0 = 0x1C
GPCLR0 = 0x28
GPLEV0 = 0x34
MAX_SUPPLY_TTL_S = 1.5
SOCKET_TIMEOUT_S = 1.0
DEFAULT_SOCKET = "/run/freeze-protect/paired-gpio.sock"


class Registers(Protocol):
    def read32(self, offset: int) -> int: ...

    def write32(self, offset: int, value: int) -> None: ...


class GpiomemRegisters:
    def __init__(self, device_path: str = "/dev/gpiomem") -> None:
        self._fd = os.open(device_path, os.O_RDWR | os.O_SYNC)
        self._memory = mmap.mmap(
            self._fd,
            mmap.PAGESIZE,
            flags=mmap.MAP_SHARED,
            prot=mmap.PROT_READ | mmap.PROT_WRITE,
        )

    def read32(self, offset: int) -> int:
        return struct.unpack_from("<I", self._memory, offset)[0]

    def write32(self, offset: int, value: int) -> None:
        struct.pack_into("<I", self._memory, offset, value)

    def close(self) -> None:
        self._memory.close()
        os.close(self._fd)


class PairedGpio:
    def __init__(self, registers: Registers) -> None:
        self._registers = registers

    def configure_outputs(self) -> None:
        value = self._registers.read32(FSEL2)
        for pin in PINS:
            shift = (pin % 10) * 3
            value = (value & ~(0b111 << shift)) | (0b001 << shift)
        self._registers.write32(FSEL2, value)

    def write_and_verify(self, command: str) -> dict[str, int]:
        if command not in {"DRAIN", "SUPPLY"}:
            raise ValueError("command must be DRAIN or SUPPLY")
        expected_level = 1 if command == "DRAIN" else 0
        # One GPSET0/GPCLR0 write changes the two BCM output latches together.
        self._registers.write32(GPSET0 if expected_level else GPCLR0, PAIR_MASK)
        levels = self._registers.read32(GPLEV0)
        result = {str(pin): 1 if levels & (1 << pin) else 0 for pin in PINS}
        if any(level != expected_level for level in result.values()):
            raise RuntimeError(f"paired GPIO readback did not confirm {command}")
        return result


def unix_time_ms() -> float:
    return time.time() * 1000


def execute_request(
    request: object,
    gpio: PairedGpio,
    *,
    clock: Callable[[], float] = unix_time_ms,
) -> dict[str, Any]:
    if not isinstance(request, dict):
        return {"ok": False, "error": "request must be an object"}
    command = request.get("command")
    deadline = request.get("deadline_unix_ms")
    if command not in {"DRAIN", "SUPPLY"}:
        return {"ok": False, "error": "command must be DRAIN or SUPPLY"}
    if isinstance(deadline, bool) or not isinstance(deadline, int | float):
        return {"ok": False, "command": command, "error": "deadline is invalid"}
    now = clock()
    if not math.isfinite(deadline):
        return {"ok": False, "command": command, "error": "deadline is invalid"}
    if command == "SUPPLY" and (
        deadline <= now or deadline - now > MAX_SUPPLY_TTL_S * 1000
    ):
        return {"ok": False, "command": command, "error": "SUPPLY request expired"}
    try:
        levels = gpio.write_and_verify(command)
    except Exception as error:
        try:
            gpio.write_and_verify("DRAIN")
        except Exception:
            pass
        return {"ok": False, "command": command, "error": str(error)}
    return {"ok": True, "command": command, "gpio": levels}


def serve(socket_path: Path, gpio: PairedGpio) -> None:
    socket_path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o660)
        listener.listen(8)
        while True:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(SOCKET_TIMEOUT_S)
                try:
                    raw = connection.recv(4096)
                    request = json.loads(raw.decode("utf-8"))
                    result = execute_request(request, gpio)
                except Exception as error:
                    result = {"ok": False, "error": str(error)}
                connection.sendall(json.dumps(result, sort_keys=True).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    arguments = parser.parse_args()
    registers = GpiomemRegisters()
    gpio = PairedGpio(registers)
    try:
        gpio.configure_outputs()
        gpio.write_and_verify("DRAIN")
        serve(Path(arguments.socket), gpio)
    finally:
        registers.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
