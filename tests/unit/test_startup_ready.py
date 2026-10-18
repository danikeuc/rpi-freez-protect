from errno import ECONNREFUSED
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import ActuatorCommand, ActuatorReceipt
from freeze_protect.startup_ready import wait_for_drain


def receipt(level=1):
    return ActuatorReceipt(command=ActuatorCommand.DRAIN, request_id="ready",
                           gpio_26=level, gpio_20=level, flow_revision="test",
                           protocol_version=2, supply_action=None)


def refused():
    error = AdapterError("request failed")
    error.__cause__ = URLError(ConnectionRefusedError(ECONNREFUSED, "refused"))
    return error


def test_waits_for_closed_listener_then_requires_paired_drain():
    driver = Mock()
    driver.command.side_effect = [refused(), refused(), receipt()]
    now = [0.0]
    def sleep(seconds):
        now[0] += seconds
    wait_for_drain(driver, clock=lambda: now[0], sleep=sleep, timeout=3)
    assert driver.command.call_count == 3
    assert all(call.args == (ActuatorCommand.DRAIN,) for call in driver.command.call_args_list)


def test_closed_listener_is_bounded():
    driver = Mock()
    driver.command.side_effect = refused()
    now = [0.0]
    def sleep(seconds):
        now[0] += seconds
    with pytest.raises(RuntimeError, match="NODE_RED_NOT_READY"):
        wait_for_drain(driver, clock=lambda: now[0], sleep=sleep, timeout=2)
    assert driver.command.call_count == 2


@pytest.mark.parametrize("failure", [AdapterError("receipt mismatch"),
                                    AdapterError("HTTP 503"), TimeoutError()])
def test_other_failures_are_not_retried(failure):
    driver = Mock()
    driver.command.side_effect = failure
    with pytest.raises(type(failure)):
        wait_for_drain(driver)
    assert driver.command.call_count == 1


def test_incorrect_gpio_receipt_stops_immediately():
    driver = Mock()
    driver.command.return_value = SimpleNamespace(command=ActuatorCommand.DRAIN,
        protocol_version=2, supply_action=None, gpio_26=0, gpio_20=0)
    with pytest.raises(RuntimeError, match="DRAIN_RECEIPT_INVALID"):
        wait_for_drain(driver)
    assert driver.command.call_count == 1


def test_late_success_does_not_report_ready():
    driver = Mock()
    driver.command.return_value = receipt()
    ticks = iter([0.0, 0.0, 61.0])
    with pytest.raises(RuntimeError, match="NODE_RED_NOT_READY"):
        wait_for_drain(driver, clock=lambda: next(ticks))


def test_readiness_preserves_service_fault_policy():
    from pathlib import Path
    unit = Path("deployment/systemd/freeze-protect.service").read_text()
    assert "ExecStartPre=/opt/rpi-freez-protect/.venv/bin/python -m freeze_protect.startup_ready" in unit
    assert "TimeoutStartSec=75" in unit
