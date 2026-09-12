from __future__ import annotations

import importlib.util
import json
import socket
from pathlib import Path
from types import ModuleType

import pytest


CLIENT_PATH = (
    Path(__file__).parents[2]
    / "deployment"
    / "node-red"
    / "paired_gpio_client.py"
)


def load_client() -> ModuleType:
    spec = importlib.util.spec_from_file_location("paired_gpio_client", CLIENT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_client_sends_a_short_expiry_and_returns_verified_daemon_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = load_client()
    socket_path = tmp_path / "paired-gpio.sock"
    connection = FakeSocket()
    monkeypatch.setattr(client.socket, "socket", lambda *_args: connection)

    result = client.request("DRAIN", socket_path, clock=lambda: 10.0)

    assert json.loads(connection.sent.decode("utf-8")) == {
        "command": "DRAIN",
        "deadline_unix_ms": 11000.0,
    }
    assert result == {"ok": True, "command": "DRAIN", "gpio": {"26": 1, "20": 1}}


class FakeSocket:
    def __init__(self) -> None:
        self.sent = b""

    def __enter__(self) -> FakeSocket:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def settimeout(self, _timeout: float) -> None:
        return None

    def connect(self, _path: str) -> None:
        return None

    def sendall(self, payload: bytes) -> None:
        self.sent = payload

    def shutdown(self, _how: int) -> None:
        return None

    def recv(self, _size: int) -> bytes:
        return json.dumps(
            {"ok": True, "command": "DRAIN", "gpio": {"26": 1, "20": 1}}
        ).encode("utf-8")
