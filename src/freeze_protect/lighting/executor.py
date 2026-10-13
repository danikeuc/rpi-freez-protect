from __future__ import annotations

import importlib
import os
import re
import selectors
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from .models import Identifier, StrictModel


class Receipt(StrictModel):
    protocol_version: Literal[1]
    request_id: Identifier
    command: Literal["OFF", "ON"]
    gpio21: bool
    generation: Identifier
    lease_id: Identifier | None
    fence_id: Identifier | None = None

    @field_validator("protocol_version", mode="before")
    @classmethod
    def integer_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("integer protocol version required")
        return value


class Output(Protocol):
    def off(self) -> Receipt: ...
    def begin(self) -> Receipt: ...
    def renew(self) -> Receipt: ...


class UnavailableOutput:
    def off(self) -> Receipt:
        raise OSError("executor unavailable")

    def begin(self) -> Receipt:
        raise OSError("executor unavailable")

    def renew(self) -> Receipt:
        raise OSError("executor unavailable")


class ExecutorClock(Protocol):
    def time(self) -> float: ...
    def monotonic(self) -> float: ...


class WallClock:
    def time(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()


class WireRequest(StrictModel):
    protocol_version: Literal[1]
    request_id: Identifier
    command: Literal["OFF", "ON"]
    action: Literal["begin", "renew"] | None = None
    deadline_unix_ms: int = Field(strict=True, gt=0)
    generation: Identifier | None = None
    lease_id: Identifier | None = None
    fence_id: Identifier | None = None

    @field_validator("protocol_version", mode="before")
    @classmethod
    def integer_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("integer protocol version required")
        return value

    @model_validator(mode="after")
    def shape(self) -> WireRequest:
        if self.command == "OFF" and (
            self.action or self.generation or self.lease_id or self.fence_id
        ):
            raise ValueError("OFF has no lease fields")
        if self.command == "ON" and (
            self.action is None or self.generation is None or self.fence_id is None
        ):
            raise ValueError("ON requires action and generation")
        if self.action == "renew" and self.lease_id is None:
            raise ValueError("renew requires lease identity")
        if self.action == "begin" and self.lease_id is not None:
            raise ValueError("begin has no lease identity")
        return self


class Line(Protocol):
    def set(self, on: bool) -> None: ...
    def get(self) -> bool: ...
    def close(self) -> None: ...


class LeaseExecutor:
    MAX_LEASE_SECONDS = 3.0

    def __init__(self, line: Line, clock: ExecutorClock | None = None) -> None:
        self.line, self.clock = line, clock or WallClock()
        self.generation = uuid.uuid4().hex
        self.lease_id: str | None = None
        self.fence_id: str | None = None
        self.until = 0.0
        self.armed = False
        self.seen: dict[str, float] = {}
        self.off_requests: dict[str, str] = {}
        self.last_wall, self.last_mono = self.clock.time(), self.clock.monotonic()
        self._off()

    def _off(self) -> None:
        # Revoke FIRST: a failed write/ack cannot leave an eligible renewal.
        self.lease_id, self.until, self.armed, self.fence_id = None, 0.0, False, None
        self.line.set(False)
        if self.line.get():
            raise OSError("OFF readback mismatch")

    def tick(self) -> None:
        wall, mono = self.clock.time(), self.clock.monotonic()
        if (
            mono < self.last_mono
            or abs((wall - self.last_wall) - (mono - self.last_mono)) > 5
        ):
            self._off()
        self.last_wall, self.last_mono = wall, mono
        if self.lease_id and (mono >= self.until or not self.line.get()):
            self._off()

    def handle(self, request: WireRequest) -> Receipt:
        self.tick()
        now = self.clock.time() * 1000
        prior_fence = self.fence_id
        if request.command == "OFF":
            self._off()
        try:
            if not now <= request.deadline_unix_ms <= now + 1000:
                raise ValueError("stale request deadline")
            mono = self.clock.monotonic()
            self.seen = {
                key: expiry for key, expiry in self.seen.items() if expiry > mono
            }
            self.off_requests = {
                key: value
                for key, value in self.off_requests.items()
                if key in self.seen
            }
            duplicate_off = (
                request.command == "OFF"
                and self.off_requests.get(request.request_id)
                == request.model_dump_json()
            )
            if (request.request_id in self.seen and not duplicate_off) or (
                len(self.seen) >= 4096 and request.request_id not in self.seen
            ):
                raise ValueError("duplicate or full request cache")
            self.seen[request.request_id] = mono + 10
            if request.command == "OFF":
                self.fence_id = (
                    prior_fence if duplicate_off and prior_fence else uuid.uuid4().hex
                )
                self.off_requests[request.request_id] = request.model_dump_json()
                self.armed = True
            else:
                if (
                    request.generation != self.generation
                    or not self.armed
                    or request.fence_id != self.fence_id
                ):
                    raise ValueError("fresh OFF or correct generation required")
                if request.action == "renew":
                    if (
                        request.lease_id != self.lease_id
                        or not self.lease_id
                        or mono >= self.until
                    ):
                        raise ValueError("expired or unknown lease")
                else:
                    self.lease_id = uuid.uuid4().hex
                self.until = mono + self.MAX_LEASE_SECONDS
                self.line.set(True)
                if not self.line.get():
                    raise OSError("ON readback mismatch")
            return Receipt(
                protocol_version=1,
                request_id=request.request_id,
                command=request.command,
                gpio21=self.line.get(),
                generation=self.generation,
                lease_id=self.lease_id,
                fence_id=self.fence_id,
            )
        except Exception:
            self._off()
            raise

    def close(self) -> None:
        try:
            self._off()
        finally:
            self.line.close()


class ExecutorClient:
    """No automatic retry. Every OFF forgets local eligibility before sending."""

    def __init__(self, path: Path, clock: ExecutorClock | None = None) -> None:
        self.path, self.clock = path, clock or WallClock()
        self.generation: str | None = None
        self.lease_id: str | None = None
        self.fence_id: str | None = None

    def _request(
        self,
        command: Literal["OFF", "ON"],
        action: Literal["begin", "renew"] | None = None,
    ) -> Receipt:
        request = WireRequest(
            protocol_version=1,
            request_id=uuid.uuid4().hex,
            command=command,
            action=action,
            deadline_unix_ms=int(self.clock.time() * 1000 + 500),
            generation=self.generation if command == "ON" else None,
            lease_id=self.lease_id if action == "renew" else None,
            fence_id=self.fence_id if command == "ON" else None,
        )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(0.25)
            peer.connect(str(self.path))
            peer.sendall(request.model_dump_json().encode() + b"\n")
            data = bytearray()
            start = self.clock.monotonic()
            while b"\n" not in data:
                if self.clock.monotonic() - start > 0.25:
                    raise TimeoutError("receipt timeout")
                chunk = peer.recv(2049 - len(data))
                if not chunk or len(data) + len(chunk) > 2048:
                    raise OSError("receipt missing or oversized")
                data.extend(chunk)
            if data.count(b"\n") != 1 or not data.endswith(b"\n"):
                raise OSError("invalid receipt frame")
            receipt = Receipt.model_validate_json(data[:-1])
        if (
            receipt.request_id != request.request_id
            or receipt.command != command
            or receipt.gpio21 != (command == "ON")
        ):
            raise OSError("mismatched receipt")
        if not receipt.fence_id:
            raise OSError("missing OFF fence")
        if command == "ON" and receipt.fence_id != self.fence_id:
            raise OSError("mismatched OFF fence")
        if command == "ON" and (
            receipt.generation != self.generation or not receipt.lease_id
        ):
            raise OSError("mismatched executor generation")
        if action == "renew" and receipt.lease_id != self.lease_id:
            raise OSError("mismatched lease identity")
        if command == "OFF" and receipt.lease_id is not None:
            raise OSError("OFF retained lease")
        self.generation, self.lease_id, self.fence_id = (
            receipt.generation,
            receipt.lease_id,
            receipt.fence_id,
        )
        return receipt

    def off(self) -> Receipt:
        self.generation, self.lease_id, self.fence_id = None, None, None
        return self._request("OFF")

    def begin(self) -> Receipt:
        try:
            return self._request("ON", "begin")
        except Exception:
            self.generation, self.lease_id, self.fence_id = None, None, None
            raise

    def renew(self) -> Receipt:
        try:
            return self._request("ON", "renew")
        except Exception:
            self.generation, self.lease_id, self.fence_id = None, None, None
            raise


class ExecutorServer:
    """Nonblocking clients have a total 250 ms frame budget; lease tick is separate."""

    def __init__(self, path: Path, executor: LeaseExecutor) -> None:
        self.path, self.executor = path, executor
        self.stopping = threading.Event()

    def stop(self) -> None:
        self.stopping.set()

    def serve(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Never remove an existing endpoint: a second owner must fail closed.
        with (
            socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener,
            selectors.DefaultSelector() as selector,
        ):
            listener.bind(str(self.path))
            os.chmod(self.path, 0o600)
            listener.listen(16)
            listener.setblocking(False)
            selector.register(listener, selectors.EVENT_READ)
            peers: dict[socket.socket, tuple[bytearray, float]] = {}

            def drop(peer: socket.socket) -> None:
                selector.unregister(peer)
                peers.pop(peer)
                peer.close()

            try:
                while not self.stopping.is_set():
                    self.executor.tick()
                    for peer, (_, deadline) in list(peers.items()):
                        if time.monotonic() >= deadline:
                            drop(peer)
                    for key, _ in selector.select(0.02):
                        if key.fileobj is listener:
                            peer, _ = listener.accept()
                            if len(peers) >= 32:
                                peer.close()
                            else:
                                peer.setblocking(False)
                                peers[peer] = (bytearray(), time.monotonic() + 0.25)
                                selector.register(peer, selectors.EVENT_READ)
                            continue
                        ready = key.fileobj
                        assert isinstance(ready, socket.socket)
                        peer = ready
                        data, _ = peers[peer]
                        try:
                            chunk = peer.recv(2049 - len(data))
                            data.extend(chunk)
                            if not chunk or len(data) > 2048:
                                drop(peer)
                            elif b"\n" in data:
                                if data.count(b"\n") != 1 or not data.endswith(b"\n"):
                                    raise ValueError("invalid request frame")
                                request = WireRequest.model_validate_json(data[:-1])
                                receipt = self.executor.handle(request)
                                peer.send(receipt.model_dump_json().encode() + b"\n")
                                drop(peer)
                        except (OSError, ValueError):
                            # Malformed requests cannot keep an old lease alive.
                            self.executor._off()
                            if peer in peers:
                                drop(peer)
            finally:
                for peer in list(peers):
                    drop(peer)
                self.executor.close()
                self.path.unlink(missing_ok=True)


class GpiodLine:
    """Optional libgpiod 2 backend: own ONLY offset21, atomically inactive."""

    def __init__(self, chip: str, *, commissioned: bool, active_low: bool) -> None:
        if (
            not commissioned
            or not active_low
            or not re.fullmatch(r"/dev/gpiochip[0-9]+", chip)
        ):
            raise ValueError("explicit GPIO21 commissioning configuration required")
        self.closed = False
        gpiod = importlib.import_module("gpiod")
        line = importlib.import_module("gpiod.line")
        self.active, self.inactive = line.Value.ACTIVE, line.Value.INACTIVE
        self.request = gpiod.request_lines(
            chip,
            consumer="independent-light-gpio21",
            config={
                21: gpiod.LineSettings(
                    direction=line.Direction.OUTPUT,
                    active_low=True,
                    output_value=self.inactive,
                )
            },
        )
        if self.get():
            self.request.release()
            raise OSError("initial inactive readback mismatch")

    def set(self, on: bool) -> None:
        self.request.set_value(21, self.active if on else self.inactive)

    def get(self) -> bool:
        return bool(self.request.get_value(21) == self.active)

    def close(self) -> None:
        if self.closed:
            return
        try:
            self.set(False)
        finally:
            self.closed = True
            self.request.release()


def run() -> None:
    line = GpiodLine(
        os.environ.get("LIGHT_GPIO_CHIP", ""),
        commissioned=os.environ.get("LIGHT_GPIO21_ENABLED") == "commissioned",
        active_low=os.environ.get("LIGHT_GPIO21_ACTIVE_LOW") == "true",
    )
    server = ExecutorServer(
        Path(
            os.environ.get(
                "LIGHT_EXECUTOR_SOCKET", "/run/independent-light/executor.sock"
            )
        ),
        LeaseExecutor(line),
    )
    try:
        server.serve()
    finally:
        line.close()


if __name__ == "__main__":
    run()
