#!/usr/bin/env python3
"""Bounded Node-RED client for the exclusive paired GPIO daemon."""

from __future__ import annotations

import argparse
import json
import socket
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_SOCKET = Path("/run/freeze-protect/paired-gpio.sock")
REQUEST_TTL_S = 1.0
SOCKET_TIMEOUT_S = 1.25
PROTOCOL_VERSION = 2


def request(
    command: str,
    socket_path: Path = DEFAULT_SOCKET,
    *,
    clock: Callable[[], float] = time.time,
    deadline_unix_ms: float | None = None,
    supply_action: str | None = None,
) -> dict[str, Any]:
    if command not in {"DRAIN", "SUPPLY"}:
        return {"ok": False, "error": "command must be DRAIN or SUPPLY"}
    if (command == "SUPPLY" and supply_action not in {"begin", "renew"}) or (
        command == "DRAIN" and supply_action is not None
    ):
        return {"ok": False, "command": command, "error": "invalid supply action"}
    payload = {
        "command": command,
        "protocol_version": PROTOCOL_VERSION,
        "deadline_unix_ms": (
            deadline_unix_ms
            if deadline_unix_ms is not None
            else (clock() + REQUEST_TTL_S) * 1000
        ),
    }
    if supply_action is not None:
        payload["supply_action"] = supply_action
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(SOCKET_TIMEOUT_S)
            connection.connect(str(socket_path))
            connection.sendall(json.dumps(payload, sort_keys=True).encode("utf-8"))
            connection.shutdown(socket.SHUT_WR)
            response = connection.recv(4096)
        decoded = json.loads(response.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise TypeError("daemon response must be an object")
        return _validate_receipt(decoded, command, supply_action)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        return {"ok": False, "command": command, "error": str(error)}


def _validate_receipt(
    decoded: dict[str, Any], command: str, supply_action: str | None
) -> dict[str, Any]:
    if decoded.get("ok") is not True:
        return decoded
    expected = 0 if command == "SUPPLY" else 1
    gpio = decoded.get("gpio")
    if (
        type(decoded.get("protocol_version")) is not int
        or decoded["protocol_version"] != PROTOCOL_VERSION
        or decoded.get("command") != command
        or decoded.get("supply_action") != supply_action
        or not isinstance(gpio, dict)
        or gpio.get("26") != expected
        or gpio.get("20") != expected
    ):
        return {
            "ok": False,
            "command": command,
            "error": "daemon receipt protocol or readback mismatch",
        }
    return decoded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("DRAIN", "SUPPLY"))
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--deadline-unix-ms", type=float)
    parser.add_argument("--supply-action", choices=("begin", "renew"))
    arguments = parser.parse_args()
    print(
        json.dumps(
            request(
                arguments.command,
                arguments.socket,
                deadline_unix_ms=arguments.deadline_unix_ms,
                supply_action=arguments.supply_action,
            ),
            sort_keys=True,
        )
    )
    # Failures are structured stdout messages consumed by the Node-RED flow.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
