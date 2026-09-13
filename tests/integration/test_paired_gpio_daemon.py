import importlib.util
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
