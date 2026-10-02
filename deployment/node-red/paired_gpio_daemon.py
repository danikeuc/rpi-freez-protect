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
import sys
import time
from collections.abc import Callable
from pathlib import Path
from signal import SIGINT, SIGTERM, getsignal, signal
from threading import Event
from typing import Any, Protocol

PINS = (26, 20)
PAIR_MASK = sum(1 << pin for pin in PINS)
FSEL2 = 0x08
GPSET0 = 0x1C
GPCLR0 = 0x28
GPLEV0 = 0x34
MAX_SUPPLY_TTL_S = 1.5
SUPPLY_LEASE_S = 60.0
SOCKET_TIMEOUT_S = 1.0
DEFAULT_SOCKET = "/run/freeze-protect/paired-gpio.sock"
PROTOCOL_VERSION = 2


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


class SupplyLease:
    """Sole lease authority for the paired outputs."""

    def __init__(
        self,
        gpio: PairedGpio,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._gpio = gpio
        self._clock = clock
        self._expires_at: float | None = None
        self._drain_verified = False

    def _drain(self) -> dict[str, Any]:
        self._expires_at = None
        self._drain_verified = False
        levels = self._gpio.write_and_verify("DRAIN")
        self._drain_verified = True
        return {
            "ok": True,
            "command": "DRAIN",
            "gpio": levels,
            "protocol_version": PROTOCOL_VERSION,
        }

    def execute(self, command: str, supply_action: str | None = None) -> dict[str, Any]:
        if command == "DRAIN":
            if supply_action is not None:
                return {
                    "ok": False,
                    "command": command,
                    "error": "DRAIN has no supply action",
                }
            try:
                return self._drain()
            except Exception as error:  # noqa: BLE001 - GPIO backends can fail arbitrarily.
                return {"ok": False, "command": command, "error": str(error)}
        if command != "SUPPLY" or supply_action not in {"begin", "renew"}:
            return {"ok": False, "command": command, "error": "invalid SUPPLY action"}
        try:
            self.enforce()
        except Exception as error:  # noqa: BLE001 - lease expiry DRAIN must fail closed.
            return {"ok": False, "command": command, "error": str(error)}
        if supply_action == "begin":
            allowed = self._expires_at is None and self._drain_verified
        else:
            allowed = self._expires_at is not None and self._clock() < self._expires_at
        if not allowed:
            return {
                "ok": False,
                "command": command,
                "error": "SUPPLY lease state rejects action",
            }
        self._expires_at = None
        self._drain_verified = False
        try:
            levels = self._gpio.write_and_verify("SUPPLY")
        except Exception as error:  # noqa: BLE001 - attempt paired DRAIN after failed write.
            try:
                self._drain()
            except Exception as drain_error:  # noqa: BLE001 - preserve both failures.
                return {
                    "ok": False,
                    "command": command,
                    "error": str(error),
                    "drain_error": str(drain_error),
                }
            return {"ok": False, "command": command, "error": str(error)}
        self._expires_at = self._clock() + SUPPLY_LEASE_S
        return {
            "ok": True,
            "command": command,
            "supply_action": supply_action,
            "gpio": levels,
            "protocol_version": PROTOCOL_VERSION,
        }

    def enforce(self) -> bool:
        if self._expires_at is None or self._clock() < self._expires_at:
            return False
        self._expires_at = None
        self._drain_verified = False
        self._drain()
        return True


def unix_time_ms() -> float:
    return time.time() * 1000


def execute_request(
    request: object,
    lease: SupplyLease,
    *,
    clock: Callable[[], float] = unix_time_ms,
) -> dict[str, Any]:
    if not isinstance(request, dict):
        return {"ok": False, "error": "request must be an object"}
    command = request.get("command")
    deadline = request.get("deadline_unix_ms")
    if command not in {"DRAIN", "SUPPLY"}:
        return {"ok": False, "error": "command must be DRAIN or SUPPLY"}
    if command == "SUPPLY":
        try:
            lease.enforce()  # Recheck after the socket's blocking recv.
        except Exception as error:  # noqa: BLE001 - no SUPPLY after failed expiry DRAIN.
            return {"ok": False, "command": command, "error": str(error)}
    if isinstance(deadline, bool) or not isinstance(deadline, int | float):
        return {"ok": False, "command": command, "error": "deadline is invalid"}
    now = clock()
    if not math.isfinite(deadline):
        return {"ok": False, "command": command, "error": "deadline is invalid"}
    if command == "SUPPLY" and (
        deadline <= now or deadline - now > MAX_SUPPLY_TTL_S * 1000
    ):
        return {"ok": False, "command": command, "error": "SUPPLY request expired"}
    if command == "SUPPLY" and (
        type(request.get("protocol_version")) is not int
        or request["protocol_version"] != PROTOCOL_VERSION
    ):
        return {"ok": False, "command": command, "error": "protocol version mismatch"}
    if command == "DRAIN" and request.get("supply_action") is not None:
        return {"ok": False, "command": command, "error": "DRAIN has no supply action"}
    return lease.execute(command, request.get("supply_action"))


def serve(
    socket_path: Path,
    gpio: PairedGpio,
    *,
    stop_requested: Callable[[], bool] = lambda: False,
) -> None:
    socket_path.unlink(missing_ok=True)
    lease = SupplyLease(gpio)
    startup = lease.execute("DRAIN")
    if not startup.get("ok"):
        raise RuntimeError("startup paired DRAIN failed")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o660)
        listener.listen(8)
        listener.settimeout(0.1)
        while not stop_requested():
            try:
                lease.enforce()
            except Exception as error:  # noqa: BLE001 - allow a later DRAIN retry.
                print(f"lease expiry DRAIN failed: {error}", file=sys.stderr)
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            with connection:
                connection.settimeout(SOCKET_TIMEOUT_S)
                try:
                    raw = connection.recv(4096)
                    request = json.loads(raw.decode("utf-8"))
                    # A blocked recv may cross expiry; SUPPLY enforces again below.
                    result = execute_request(request, lease)
                except Exception as error:  # noqa: BLE001 - keep daemon responsive.
                    result = {"ok": False, "error": str(error)}
                try:
                    connection.sendall(
                        json.dumps(result, sort_keys=True).encode("utf-8")
                    )
                except OSError:
                    pass  # The independent lease still expires if a receipt is lost.


def run_daemon(socket_path: Path, gpio: PairedGpio) -> None:
    stop = Event()
    previous_handlers = {signum: getsignal(signum) for signum in (SIGTERM, SIGINT)}

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    for signum in previous_handlers:
        signal(signum, request_stop)
    try:
        gpio.write_and_verify("DRAIN")
        serve(socket_path, gpio, stop_requested=stop.is_set)
    finally:
        try:
            gpio.write_and_verify("DRAIN")
        except Exception as error:  # noqa: BLE001 - termination remains best effort.
            print(f"emergency DRAIN failed during shutdown: {error}", file=sys.stderr)
        for signum, previous_handler in previous_handlers.items():
            signal(signum, previous_handler)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    arguments = parser.parse_args()
    registers = GpiomemRegisters()
    gpio = PairedGpio(registers)
    try:
        gpio.configure_outputs()
        run_daemon(Path(arguments.socket), gpio)
    finally:
        registers.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
