import json
import uuid

import pytest
from conftest import Clock

from freeze_protect.lighting.executor import ExecutorClient, LeaseExecutor, WireRequest


class Line:
    def __init__(self):
        self.on = False
        self.writes = []
        self.fail = False

    def set(self, on):
        self.writes.append(on)
        self.on = on
        if self.fail:
            raise OSError("write fault")

    def get(self):
        return self.on

    def close(self):
        self.set(False)


def request(clock, command="OFF", action=None, **extra):
    return WireRequest.model_validate(
        dict(
            protocol_version=1,
            request_id=uuid.uuid4().hex,
            command=command,
            action=action,
            **{"deadline_unix_ms": int(clock.time() * 1000 + 500), **extra},
        )
    )


def test_lease_expires_and_cannot_be_revived_without_fresh_off():
    clock, line = Clock(), Line()
    e = LeaseExecutor(line, clock)
    assert line.writes == [False]
    off = e.handle(request(clock))
    on = e.handle(
        request(clock, "ON", "begin", generation=off.generation, fence_id=off.fence_id)
    )
    assert line.on and on.lease_id
    clock.advance(3.1)
    e.tick()
    assert not line.on
    with pytest.raises(ValueError):
        e.handle(
            request(
                clock,
                "ON",
                "renew",
                generation=on.generation,
                fence_id=on.fence_id,
                lease_id=on.lease_id,
            )
        )
    with pytest.raises(ValueError):
        e.handle(
            request(
                clock, "ON", "begin", generation=on.generation, fence_id=on.fence_id
            )
        )
    fresh = e.handle(request(clock))
    assert e.handle(
        request(
            clock, "ON", "begin", generation=fresh.generation, fence_id=fresh.fence_id
        )
    ).gpio21


def test_expired_wrong_generation_and_readback_fault_request_off():
    clock, line = Clock(), Line()
    e = LeaseExecutor(line, clock)
    off = e.handle(request(clock))
    with pytest.raises(ValueError):
        e.handle(
            request(clock, "ON", "begin", generation="wrong", fence_id=off.fence_id)
        )
    assert not line.on
    off = e.handle(request(clock))
    on = e.handle(
        request(clock, "ON", "begin", generation=off.generation, fence_id=off.fence_id)
    )
    with pytest.raises(ValueError):
        e.handle(
            request(
                clock,
                "ON",
                "renew",
                generation=on.generation,
                fence_id=on.fence_id,
                lease_id=on.lease_id,
                deadline_unix_ms=int(clock.time() * 1000 - 1),
            )
        )
    assert not line.on
    line.fail = True
    with pytest.raises(OSError):
        e.handle(request(clock))
    assert e.lease_id is None


def test_protocol_strict_bounds():
    clock = Clock()
    with pytest.raises(ValueError):
        WireRequest.model_validate({"protocol_version": True, "command": "OFF"})
    with pytest.raises(ValueError):
        request(clock, "ON", "invalid")


def test_socket_fragmented_request_and_client_receipt_validation(tmp_path):
    import socket
    import threading
    import time

    from freeze_protect.lighting.executor import ExecutorServer

    clock, line = Clock(), Line()
    server = ExecutorServer(tmp_path / "light.sock", LeaseExecutor(line, clock))
    worker = threading.Thread(target=server.serve, daemon=True)
    worker.start()
    for _ in range(100):
        try:
            with socket.socket(socket.AF_UNIX) as readiness:
                readiness.connect(str(server.path))
            break
        except (FileNotFoundError, ConnectionRefusedError):
            time.sleep(0.005)
    try:
        client = ExecutorClient(server.path, clock)
        assert not client.off().gpio21
        assert client.begin().gpio21
        assert client.renew().gpio21
        with socket.socket(socket.AF_UNIX) as peer:
            peer.settimeout(1)
            peer.connect(str(server.path))
            payload = request(clock).model_dump_json().encode() + b"\n"
            peer.sendall(payload[:10])
            peer.sendall(payload[10:])
            assert json.loads(peer.recv(2048))["gpio21"] is False
        with socket.socket(socket.AF_UNIX) as slow:
            slow.connect(str(server.path))
            slow.sendall(b"{")
            time.sleep(0.35)
            assert not client.off().gpio21
        with socket.socket(socket.AF_UNIX) as huge:
            huge.connect(str(server.path))
            huge.sendall(b"x" * 2049)
            time.sleep(0.05)
        assert not client.off().gpio21
    finally:
        server.stop()
        worker.join(2)
        assert not worker.is_alive()
        assert not line.on


def test_gpiod_backend_requests_only_gpio21_inactive_and_requires_gate(monkeypatch):
    from types import SimpleNamespace

    from freeze_protect.lighting.executor import GpiodLine

    operations = []

    class Request:
        value = "inactive"

        def get_value(self, pin):
            operations.append(("get", pin))
            return self.value

        def set_value(self, pin, value):
            operations.append(("set", pin, value))
            self.value = value

        def release(self):
            operations.append(("release",))

    def request_lines(chip, **kwargs):
        operations.append(("request", chip, kwargs))
        return Request()

    gpiod = SimpleNamespace(request_lines=request_lines, LineSettings=lambda **kw: kw)
    line_module = SimpleNamespace(
        Value=SimpleNamespace(ACTIVE="active", INACTIVE="inactive"),
        Direction=SimpleNamespace(OUTPUT="output"),
    )
    monkeypatch.setattr(
        "freeze_protect.lighting.executor.importlib.import_module",
        lambda name: gpiod if name == "gpiod" else line_module,
    )
    with pytest.raises(ValueError):
        GpiodLine("/dev/gpiochip0", commissioned=False, active_low=True)
    assert operations == []
    line = GpiodLine("/dev/gpiochip0", commissioned=True, active_low=True)
    configuration = operations[0][2]["config"]
    assert set(configuration) == {21}
    assert configuration[21]["output_value"] == "inactive"
    assert configuration[21]["active_low"] is True
    line.set(True)
    assert line.get()
    line.close()
    assert all(op[1] == 21 for op in operations if op[0] in {"get", "set"})


def test_receipt_rejects_boolean_protocol_version():
    from freeze_protect.lighting.executor import Receipt

    with pytest.raises(ValueError):
        Receipt.model_validate(
            {
                "protocol_version": True,
                "request_id": "id",
                "command": "OFF",
                "gpio21": False,
                "generation": "gen",
                "lease_id": None,
            }
        )


def test_client_rejects_mismatched_receipt_and_forgets_eligibility(
    tmp_path, monkeypatch
):
    from freeze_protect.lighting.executor import Receipt

    clock = Clock()
    client = ExecutorClient(tmp_path / "fake.sock", clock)
    client.generation = "gen"
    client.lease_id = "lease"
    client.fence_id = "fence"

    class Peer:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def settimeout(self, timeout):
            pass

        def connect(self, path):
            pass

        def sendall(self, payload):
            pass

        def recv(self, size):
            return (
                Receipt(
                    protocol_version=1,
                    request_id="wrong",
                    command="ON",
                    gpio21=True,
                    generation="gen",
                    lease_id="lease",
                )
                .model_dump_json()
                .encode()
                + b"\n"
            )

    monkeypatch.setattr(
        "freeze_protect.lighting.executor.socket.socket", lambda *args: Peer()
    )
    with pytest.raises(OSError):
        client.renew()
    assert client.lease_id is None and client.generation is None


def test_executor_duplicate_begin_does_not_extend_lease():
    clock, line = Clock(), Line()
    executor = LeaseExecutor(line, clock)
    off = executor.handle(request(clock))
    command = request(
        clock, "ON", "begin", generation=off.generation, fence_id=off.fence_id
    )
    executor.handle(command)
    clock.advance(0.1)
    with pytest.raises(ValueError):
        executor.handle(command)
    assert not line.on and executor.lease_id is None


def test_gpiod_close_is_idempotent(monkeypatch):
    from types import SimpleNamespace

    from freeze_protect.lighting.executor import GpiodLine

    class Request:
        released = False

        def get_value(self, pin):
            return 0

        def set_value(self, pin, value):
            if self.released:
                raise OSError("released request")

        def release(self):
            self.released = True

    request = Request()
    gpiod = SimpleNamespace(
        request_lines=lambda *args, **kwargs: request, LineSettings=lambda **kw: kw
    )
    line = SimpleNamespace(
        Value=SimpleNamespace(ACTIVE=1, INACTIVE=0), Direction=SimpleNamespace(OUTPUT=1)
    )
    monkeypatch.setattr(
        "freeze_protect.lighting.executor.importlib.import_module",
        lambda name: gpiod if name == "gpiod" else line,
    )
    backend = GpiodLine("/dev/gpiochip0", commissioned=True, active_low=True)
    backend.close()
    backend.close()


def test_old_begin_cannot_cross_a_newer_off():
    clock, line = Clock(), Line()
    executor = LeaseExecutor(line, clock)
    first_off = executor.handle(request(clock))
    delayed = request(
        clock,
        "ON",
        "begin",
        generation=first_off.generation,
        fence_id=first_off.fence_id,
    )
    executor.handle(request(clock))
    with pytest.raises(ValueError):
        executor.handle(delayed)
    assert not line.on


def test_duplicate_off_keeps_current_fence_and_old_renew_is_rejected():
    clock, line = Clock(), Line()
    executor = LeaseExecutor(line, clock)
    off_request = request(clock)
    off = executor.handle(off_request)
    repeated = executor.handle(off_request)
    assert off.fence_id == repeated.fence_id
    on = executor.handle(
        request(clock, "ON", "begin", generation=off.generation, fence_id=off.fence_id)
    )
    delayed = request(
        clock,
        "ON",
        "renew",
        generation=on.generation,
        fence_id=on.fence_id,
        lease_id=on.lease_id,
    )
    executor.handle(request(clock))
    with pytest.raises(ValueError):
        executor.handle(delayed)
    assert not line.on


def test_replayed_off_after_on_revokes_pending_begin_fence():
    clock, line = Clock(), Line()
    executor = LeaseExecutor(line, clock)
    off_a = request(clock)
    first = executor.handle(off_a)
    pending_b = request(
        clock, "ON", "begin", generation=first.generation, fence_id=first.fence_id
    )
    executor.handle(
        request(
            clock, "ON", "begin", generation=first.generation, fence_id=first.fence_id
        )
    )
    replayed = executor.handle(off_a)
    assert not line.on
    with pytest.raises(ValueError):
        executor.handle(pending_b)
    assert not line.on
    assert replayed.fence_id != first.fence_id
