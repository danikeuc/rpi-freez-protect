"""Real daemon lease state with fake clocks and GPIO registers."""

import json
from pathlib import Path
from typing import Self

import pytest
from test_paired_gpio_client import load_client
from test_paired_gpio_daemon import FakeRegisters, load_daemon


def test_expired_lease_rejects_renew_even_after_startup_drain() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    now = [0.0]
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: now[0])
    assert lease.execute("DRAIN")["ok"] is True
    assert lease.execute("SUPPLY", "begin")["ok"] is True
    now[0] = 60.0
    assert lease.enforce() is True
    assert lease.execute("DRAIN")["ok"] is True  # bridge startup DRAIN
    low_writes = registers.writes.count((daemon.GPCLR0, daemon.PAIR_MASK))
    assert lease.execute("SUPPLY", "renew")["ok"] is False
    assert registers.writes.count((daemon.GPCLR0, daemon.PAIR_MASK)) == low_writes
    assert lease.execute("SUPPLY", "begin")["ok"] is True


def test_duplicate_begin_and_missing_mode_never_extend_active_lease() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    now = [0.0]
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: now[0])
    lease.execute("DRAIN")
    assert lease.execute("SUPPLY", "begin")["ok"] is True
    now[0] = 30.0
    assert lease.execute("SUPPLY", "begin")["ok"] is False
    assert lease.execute("SUPPLY")["ok"] is False
    now[0] = 60.0
    assert lease.enforce() is True
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK


def test_fresh_daemon_rejects_old_renew_and_failed_write_invalidates_lease() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    now = [0.0]
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: now[0])
    assert lease.execute("SUPPLY", "renew")["ok"] is False
    lease.execute("DRAIN")
    lease.execute("SUPPLY", "begin")
    original = registers.write32

    def fail_low(offset: int, value: int) -> None:
        if offset == daemon.GPCLR0:
            raise OSError("write failed")
        original(offset, value)

    registers.write32 = fail_low
    assert lease.execute("SUPPLY", "renew")["ok"] is False
    assert lease.execute("SUPPLY", "renew")["ok"] is False
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK


def test_old_or_missing_supply_contract_is_rejected_before_low_write() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: 0.0)
    lease.execute("DRAIN")
    base = {"command": "SUPPLY", "deadline_unix_ms": 1000.0}
    for fields in (
        {},
        {"protocol_version": 2},
        {"protocol_version": 1, "supply_action": "begin"},
        {"protocol_version": 2.0, "supply_action": "begin"},
        {"protocol_version": 2, "supply_action": "invalid"},
    ):
        assert (
            daemon.execute_request({**base, **fields}, lease, clock=lambda: 0.0)["ok"]
            is False
        )
    assert (daemon.GPCLR0, daemon.PAIR_MASK) not in registers.writes


def test_expiry_is_enforced_after_blocked_receive_even_for_stale_request() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    elapsed = [0.0]
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: elapsed[0])
    lease.execute("DRAIN")
    lease.execute("SUPPLY", "begin")
    elapsed[0] = 60.0
    result = daemon.execute_request(
        {
            "command": "SUPPLY",
            "protocol_version": 2,
            "supply_action": "renew",
            "deadline_unix_ms": 9000.0,
        },
        lease,
        clock=lambda: 10000.0,
    )
    assert result["ok"] is False
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK


def test_readback_failure_cannot_preserve_renew_eligibility() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    now = [0.0]
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: now[0])
    lease.execute("DRAIN")
    lease.execute("SUPPLY", "begin")
    original_read = registers.read32
    fail_once = [True]

    def failed_read(offset: int) -> int:
        if offset == daemon.GPLEV0 and fail_once[0]:
            fail_once[0] = False
            return daemon.PAIR_MASK  # SUPPLY readback appears high/high.
        return original_read(offset)

    registers.read32 = failed_read
    now[0] = 30.0
    result = lease.execute("SUPPLY", "renew")
    assert result["ok"] is False
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK
    assert lease.execute("SUPPLY", "renew")["ok"] is False


def test_client_and_daemon_agree_on_version_and_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = load_daemon()
    client = load_client()
    registers = FakeRegisters(daemon)
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: 0.0)

    class Socket:
        response = b""

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def settimeout(self, _timeout: float) -> None:
            return None

        def connect(self, _path: str) -> None:
            return None

        def sendall(self, data: bytes) -> None:
            request = json.loads(data)
            result = daemon.execute_request(request, lease, clock=lambda: 0.0)
            self.response = json.dumps(result).encode()

        def shutdown(self, _how: int) -> None:
            return None

        def recv(self, _count: int) -> bytes:
            return self.response

    monkeypatch.setattr(client.socket, "socket", lambda *_args: Socket())
    path = tmp_path / "paired.sock"
    assert client.request("DRAIN", path, clock=lambda: 0.0)["protocol_version"] == 2
    assert (
        client.request("SUPPLY", path, clock=lambda: 0.0, supply_action="begin")[
            "supply_action"
        ]
        == "begin"
    )
    assert (
        client.request("SUPPLY", path, clock=lambda: 0.0, supply_action="renew")[
            "supply_action"
        ]
        == "renew"
    )
