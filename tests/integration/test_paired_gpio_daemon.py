import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

DAEMON_PATH = (
    Path(__file__).parents[2]
    / "deployment"
    / "node-red"
    / "paired_gpio_daemon.py"
)


def load_daemon() -> ModuleType:
    spec = importlib.util.spec_from_file_location("paired_gpio_daemon", DAEMON_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRegisters:
    def __init__(self, daemon: ModuleType) -> None:
        self.daemon = daemon
        self.level = daemon.PAIR_MASK
        self.writes: list[tuple[int, int]] = []

    def read32(self, offset: int) -> int:
        if offset == self.daemon.GPLEV0:
            return self.level
        return 0

    def write32(self, offset: int, value: int) -> None:
        self.writes.append((offset, value))
        if offset == self.daemon.GPSET0:
            self.level |= value
        if offset == self.daemon.GPCLR0:
            self.level &= ~value


def test_atomic_pair_write_uses_one_masked_register_store_and_readback() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    gpio = daemon.PairedGpio(registers)
    gpio.configure_outputs()

    levels = gpio.write_and_verify("SUPPLY")

    assert levels == {"26": 0, "20": 0}
    assert registers.writes[-1] == (daemon.GPCLR0, daemon.PAIR_MASK)
    assert registers.writes.count((daemon.GPCLR0, daemon.PAIR_MASK)) == 1


def test_expired_supply_is_rejected_without_a_low_pair_write() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    gpio = daemon.PairedGpio(registers)
    gpio.configure_outputs()

    result = daemon.execute_request(
        {"command": "SUPPLY", "deadline_unix_ms": 9_000.0},
        gpio,
        clock=lambda: 10_000.0,
    )

    assert result["ok"] is False
    assert "expired" in result["error"]
    assert (daemon.GPCLR0, daemon.PAIR_MASK) not in registers.writes


def test_delayed_supply_followed_by_drain_cannot_leave_the_pair_low() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    gpio = daemon.PairedGpio(registers)
    gpio.configure_outputs()

    delayed_supply = daemon.execute_request(
        {"command": "SUPPLY", "deadline_unix_ms": 9_000.0},
        gpio,
        clock=lambda: 10_000.0,
    )
    drain = daemon.execute_request(
        {"command": "DRAIN", "deadline_unix_ms": 9_000.0},
        gpio,
        clock=lambda: 10_000.0,
    )

    assert delayed_supply["ok"] is False
    assert drain == {"ok": True, "command": "DRAIN", "gpio": {"26": 1, "20": 1}}
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK


def test_supply_lease_drains_pair_when_hub_stops_renewing() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    gpio = daemon.PairedGpio(registers)
    now = [10.0]
    lease = daemon.SupplyLease(gpio, clock=lambda: now[0])

    gpio.write_and_verify("SUPPLY")
    lease.arm(daemon.SUPPLY_LEASE_S)
    now[0] = 10.0 + daemon.SUPPLY_LEASE_S - 5.0

    assert lease.enforce() is False
    assert registers.level & daemon.PAIR_MASK == 0

    now[0] = 10.0 + daemon.SUPPLY_LEASE_S + 0.1

    assert lease.enforce() is True
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK


def test_failed_command_reports_failed_emergency_drain() -> None:
    daemon = load_daemon()

    class BrokenGpio:
        def write_and_verify(self, command: str) -> dict[str, int]:
            raise RuntimeError(f"{command} failed")

    result = daemon.execute_request(
        {"command": "SUPPLY", "deadline_unix_ms": 11_000.0},
        BrokenGpio(),
        clock=lambda: 10_000.0,
    )

    assert result["ok"] is False
    assert result["error"] == "SUPPLY failed"
    assert result["drain_error"] == "DRAIN failed"


def test_sigterm_drains_an_active_supply_before_process_exit(tmp_path: Path) -> None:
    ready_path = tmp_path / "ready"
    command_log = tmp_path / "commands.log"
    script = f"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("paired_gpio_daemon", {str(DAEMON_PATH)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FakeGpio:
    def write_and_verify(self, command):
        with Path({str(command_log)!r}).open("a", encoding="utf-8") as output:
            output.write(command + "\\n")
        level = 0 if command == "SUPPLY" else 1
        return {{"26": level, "20": level}}

def fake_serve(_socket_path, gpio, *, stop_requested):
    gpio.write_and_verify("SUPPLY")
    Path({str(ready_path)!r}).touch()
    while not stop_requested():
        module.time.sleep(0.01)

module.serve = fake_serve
module.run_daemon(Path("unused.sock"), FakeGpio())
"""
    process = subprocess.Popen([sys.executable, "-c", script])
    try:
        deadline = time.monotonic() + 5
        while not ready_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready_path.exists()

        os.kill(process.pid, signal.SIGTERM)
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert command_log.read_text(encoding="utf-8").splitlines() == [
        "DRAIN",
        "SUPPLY",
        "DRAIN",
    ]
