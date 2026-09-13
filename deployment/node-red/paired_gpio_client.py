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


def request(
    command: str,
    socket_path: Path = DEFAULT_SOCKET,
    *,
    clock: Callable[[], float] = time.time,
    deadline_unix_ms: float | None = None,
) -> dict[str, Any]:
    if command not in {"DRAIN", "SUPPLY"}:
        return {"ok": False, "error": "command must be DRAIN or SUPPLY"}
    payload = {
        "command": command,
        "deadline_unix_ms": (
            deadline_unix_ms
            if deadline_unix_ms is not None
            else (clock() + REQUEST_TTL_S) * 1000
        ),
    }
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(SOCKET_TIMEOUT_S)
            connection.connect(str(socket_path))
            connection.sendall(json.dumps(payload, sort_keys=True).encode("utf-8"))
            connection.shutdown(socket.SHUT_WR)
            response = connection.recv(4096)
        decoded = json.loads(response.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("daemon response must be an object")
        return decoded
    except Exception as error:
        return {"ok": False, "command": command, "error": str(error)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("DRAIN", "SUPPLY"))
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--deadline-unix-ms", type=float)
    arguments = parser.parse_args()
    print(
        json.dumps(
            request(
                arguments.command,
                arguments.socket,
                deadline_unix_ms=arguments.deadline_unix_ms,
            ),
            sort_keys=True,
        )
    )
    # Failures are structured stdout messages consumed by the Node-RED flow.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
