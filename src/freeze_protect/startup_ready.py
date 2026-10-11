"""Bounded Node-RED DRAIN readiness gate, before Hub process startup.

The retry/acceptance window is 60 seconds, not a hard request wall-clock limit.
The service imposes the outer 75-second startup limit.
Only a refused TCP connection is retried. Invalid/failed receipts fail this
process. No database, fault recovery, forecast or SUPPLY action is performed.
"""
from __future__ import annotations

import errno
import os
import time
from collections.abc import Callable
from urllib.error import URLError

from freeze_protect.adapters.node_red import NodeRedActuatorDriver
from freeze_protect.application.ports import ActuatorDriver, AdapterError
from freeze_protect.domain.models import ActuatorCommand


def wait_for_drain(
    driver: ActuatorDriver,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    timeout: float = 60.0,
) -> None:
    deadline = clock() + timeout
    while clock() < deadline:
        try:
            receipt = driver.command(ActuatorCommand.DRAIN)
        except AdapterError as error:
            cause = error.__cause__
            reason = cause.reason if isinstance(cause, URLError) else cause
            if not isinstance(reason, OSError) or reason.errno != errno.ECONNREFUSED:
                raise
            remaining = deadline - clock()
            if remaining > 0:
                sleep(min(1.0, remaining))
            continue
        if (receipt.command is not ActuatorCommand.DRAIN
                or receipt.protocol_version != 2 or receipt.supply_action is not None
                or (receipt.gpio_26, receipt.gpio_20) != (1, 1)):
            raise RuntimeError("DRAIN_RECEIPT_INVALID")
        if clock() >= deadline:
            break
        return
    raise RuntimeError("NODE_RED_NOT_READY")


def main() -> int:
    try:
        driver = NodeRedActuatorDriver(
            os.environ["FREEZE_PROTECT_NODE_RED_URL"],
            os.environ["FREEZE_PROTECT_NODE_RED_TOKEN"],
            timeout_s=3.0,
        )
        wait_for_drain(driver)
    except (KeyError, ValueError, AdapterError, OSError, RuntimeError):
        # Exception text can contain transport/configuration data. Log a fixed code.
        print("NODE_RED_DRAIN_READINESS_FAILED", flush=True)
        return 1
    print("NODE_RED_DRAIN_READY", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
