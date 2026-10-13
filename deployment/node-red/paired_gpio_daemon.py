#!/usr/bin/env python3
"""Exclusive, atomic GPIO 20/26 executor for the paired-valve bridge."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import mmap
import os
import re
import socket
import stat
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
    """Only paired latch stores and level reads; never GPIO configuration."""

    def __init__(self, expected_device: int) -> None:
        self._fd = os.open("/dev/gpiomem", os.O_RDWR | os.O_SYNC | os.O_CLOEXEC)
        try:
            info = os.fstat(self._fd)
            if not stat.S_ISCHR(info.st_mode) or info.st_rdev != expected_device:
                raise ValueError("gpiomem identity changed after validation")
            self._memory = mmap.mmap(
                self._fd,
                mmap.PAGESIZE,
                flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
            )
        except BaseException:
            os.close(self._fd)
            raise

    def read32(self, offset: int) -> int:
        if offset != GPLEV0:
            raise ValueError("only paired level readback is permitted")
        return struct.unpack_from("<I", self._memory, offset)[0] & PAIR_MASK

    def write32(self, offset: int, value: int) -> None:
        if offset not in (GPSET0, GPCLR0) or value != PAIR_MASK:
            raise ValueError("only a fixed paired latch write is permitted")
        struct.pack_into("<I", self._memory, offset, value)

    def close(self) -> None:
        # If unmapping fails, retain ownership; the caller must not release lines.
        self._memory.close()
        os.close(self._fd)


DEVICE_TREE = Path("/sys/firmware/devicetree/base")
SYS_DEV_CHAR = Path("/sys/dev/char")
GPIOMEM_CLASS = Path("/sys/class/gpiomem/gpiomem")
GPIOMEM_DRIVER = Path("/sys/bus/platform/drivers/rpi-gpiomem")


def _compatible(node: Path) -> set[str]:
    return set(node.joinpath("compatible").read_bytes().decode("ascii").split("\0"))


def _device_node(device: int) -> Path:
    path = SYS_DEV_CHAR / f"{os.major(device)}:{os.minor(device)}" / "device"
    return path.resolve(strict=True)


def validate_platform(chip_fd: int, chip_label: str) -> int:
    """Bind opened gpiochip and fixed gpiomem device to the same BCM GPIO bank.

    Missing sysfs/DT metadata is unsupported, not permission to guess a mapping.
    """
    compatible = _compatible(DEVICE_TREE)
    supported = {"brcm,bcm2835", "brcm,bcm2836", "brcm,bcm2837", "brcm,bcm2711"}
    if (
        not compatible.intersection(supported)
        or "brcm,bcm2712" in compatible
        or not any(item.startswith("raspberrypi,") for item in compatible)
    ):
        raise ValueError("unsupported BCM platform")
    chip_info = os.fstat(chip_fd)
    memory_info = os.stat("/dev/gpiomem")
    if not stat.S_ISCHR(chip_info.st_mode) or not stat.S_ISCHR(memory_info.st_mode):
        raise ValueError("GPIO devices must be character devices")
    chip_device = _device_node(chip_info.st_rdev)
    # The legacy gpiomem class device has no parent. Bind it using the
    # driver's unique legacy platform instance and its registered dev number.
    memory_id = f"{os.major(memory_info.st_rdev)}:{os.minor(memory_info.st_rdev)}"
    if (
        (GPIOMEM_CLASS / "dev").read_text().strip() != memory_id
        or (SYS_DEV_CHAR / memory_id).resolve(strict=True) != GPIOMEM_CLASS.resolve(strict=True)
    ):
        raise ValueError("gpiomem character device identity mismatch")
    bound = [path for path in GPIOMEM_DRIVER.iterdir() if (path / "of_node").exists()]
    if len(bound) != 1:
        raise ValueError("missing or ambiguous gpiomem platform driver")
    chip_node = (chip_device / "of_node").resolve(strict=True)
    memory_node = (bound[0] / "of_node").resolve(strict=True)
    if chip_node.parent != memory_node.parent:
        raise ValueError("GPIO chip and gpiomem buses differ")
    parent = chip_node.parent
    if (
        (parent / "#address-cells").read_bytes() != struct.pack(">I", 1)
        or (parent / "#size-cells").read_bytes() != struct.pack(">I", 1)
    ):
        raise ValueError("unsupported GPIO device-tree addressing")
    expected = "brcm,bcm2711-gpio" if chip_label == "pinctrl-bcm2711" else "brcm,bcm2835-gpio"
    if (
        expected not in _compatible(chip_node)
        or "brcm,bcm2835-gpiomem" not in _compatible(memory_node)
        or (chip_device / "driver").resolve(strict=True).name != "pinctrl-bcm2835"
    ):
        raise ValueError("unsupported GPIO driver or bank")
    for node in (chip_node, memory_node):
        reg = (node / "reg").read_bytes()
        if len(reg) != 8 or struct.unpack(">II", reg)[0] != 0x7E200000:
            raise ValueError("GPIO register bank does not match gpiomem")
    if struct.unpack(">II", (memory_node / "reg").read_bytes())[1] < mmap.PAGESIZE:
        raise ValueError("gpiomem register range is too small")
    return memory_info.st_rdev


# On an unexpected failed unmap, keep strong references until process exit.
# Releasing a live request while MMIO remains mapped would break ownership.
_UNCLOSED_HARDWARE: list[Any] = []


class KernelOwnedPair:
    """Hold exclusive kernel ownership throughout every raw register access."""

    def __init__(self, chip_path: str, profile: str) -> None:
        if profile != "bcm2835-gpiomem-v1" or not re.fullmatch(
            r"/dev/gpiochip[0-9]+", chip_path
        ):
            raise ValueError("explicit verified paired GPIO chip/profile required")
        gpiod = importlib.import_module("gpiod")
        version = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", gpiod.__version__)
        if version is None or not (2, 3) <= tuple(map(int, version.groups()[:2])) < (3, 0):
            raise RuntimeError("paired GPIO requires libgpiod Python >=2.3,<3")
        line = importlib.import_module("gpiod.line")
        self.chip = gpiod.Chip(chip_path)
        self.request: Any = None
        self.registers: GpiomemRegisters | None = None
        self.gpio: PairedGpio | None = None
        try:
            info = self.chip.get_info()
            profiles = {"pinctrl-bcm2835": 54, "pinctrl-bcm2711": 58}
            if profiles.get(info.label) != info.num_lines or info.name != Path(chip_path).name:
                raise ValueError("unsupported GPIO chip metadata")
            for pin in PINS:
                metadata = self.chip.get_line_info(pin)
                if metadata.offset != pin or metadata.name != f"GPIO{pin}" or metadata.used:
                    raise ValueError("paired line identity mismatch or already owned")
            memory_device = validate_platform(self.chip.fd, info.label)
            # AS_IS reserves both lines without an initial sequential value write.
            self.request = self.chip.request_lines(
                consumer="freeze-protect-pair",
                config={PINS: gpiod.LineSettings(
                    direction=line.Direction.AS_IS,
                    bias=line.Bias.AS_IS,
                    edge_detection=line.Edge.NONE,
                    active_low=False,
                )},
            )
            self.registers = GpiomemRegisters(memory_device)
            self.gpio = PairedGpio(self.registers)
            # Preload together before kernel direction changes. Input levels are
            # not expected to reflect this latch until outputs are configured.
            self.registers.write32(GPSET0, PAIR_MASK)
            self.request.reconfigure_lines({PINS: gpiod.LineSettings(
                direction=line.Direction.OUTPUT,
                active_low=False,
                output_value=line.Value.ACTIVE,
            )})
            self.gpio.write_and_verify("DRAIN")
        except BaseException:
            self.close(suppress_errors=True)
            raise

    def close(self, *, suppress_errors: bool = False) -> None:
        errors: list[BaseException] = []
        if self.registers is not None:
            try:
                if self.gpio is not None:
                    self.gpio.write_and_verify("DRAIN")
            except BaseException as error:  # noqa: BLE001 - preserve ownership and original failure.
                errors.append(error)
            try:
                self.registers.close()
            except BaseException as error:  # noqa: BLE001 - preserve ownership and original failure.
                errors.append(error)
                _UNCLOSED_HARDWARE.append(self)
                # Never explicitly release ownership after an unsuccessful unmap.
                if not suppress_errors:
                    raise errors[0]
                for failure in errors:
                    print(f"paired cleanup failed: {failure}", file=sys.stderr)
                return
            self.registers = None
            self.gpio = None
        try:
            if self.request is not None:
                self.request.release()
                self.request = None
        except BaseException as error:  # noqa: BLE001 - preserve ownership and original failure.
            errors.append(error)
        try:
            self.chip.close()
        except BaseException as error:  # noqa: BLE001 - preserve ownership and original failure.
            errors.append(error)
        if errors and not suppress_errors:
            raise errors[0]
        for error in errors:
            print(f"paired cleanup failed: {error}", file=sys.stderr)


class PairedGpio:
    def __init__(self, registers: Registers) -> None:
        self._registers = registers

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
        self._drain_pending = False

    def _drain(self) -> dict[str, Any]:
        self._expires_at = None
        self._drain_verified = False
        # Revoking SUPPLY must not discard an unconfirmed safe-state request.
        self._drain_pending = True
        levels = self._gpio.write_and_verify("DRAIN")
        self._drain_pending = False
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
        if not self._drain_pending and (
            self._expires_at is None or self._clock() < self._expires_at
        ):
            return False
        # The existing socket loop retries pending DRAIN even without Hub traffic.
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
                print(f"pending or expired lease DRAIN failed: {error}", file=sys.stderr)
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
    hardware = KernelOwnedPair(
        os.environ.get("PAIRED_GPIO_CHIP", ""),
        os.environ.get("PAIRED_GPIO_PROFILE", ""),
    )
    try:
        assert hardware.gpio is not None
        run_daemon(Path(arguments.socket), hardware.gpio)
    except BaseException:
        hardware.close(suppress_errors=True)
        raise
    else:
        hardware.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
