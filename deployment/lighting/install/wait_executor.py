"""Wait for the local light executor socket before systemd starts the controller."""
from __future__ import annotations

import socket
import time
from pathlib import Path

SOCKET = Path('/run/independent-light/executor.sock')


def wait_ready(path=SOCKET, timeout=12.0):
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                peer.settimeout(min(0.25, max(0.001, deadline - time.monotonic())))
                peer.connect(str(path))
            return
        except (FileNotFoundError, ConnectionRefusedError, TimeoutError):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('light executor readiness deadline') from None
            time.sleep(min(0.1, remaining))


if __name__ == '__main__':
    wait_ready()
