from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from freeze_protect.adapters.node_red import NodeRedActuatorDriver
from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import ActuatorCommand


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = json.dumps(payload).encode()
        self.status = status

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_node_red_requires_matching_paired_receipt() -> None:
    driver = NodeRedActuatorDriver(
        "http://127.0.0.1:1880/internal/freeze-protect/actuator",
        "hub-token",
        urlopen=lambda _request, _timeout: FakeResponse(
            {"command": "SUPPLY", "request_id": "r-1", "gpio": {"26": 0, "20": 1}, "flow_revision": "m1"}
        ),
    )

    with pytest.raises(AdapterError, match="receipt"):
        driver.command(ActuatorCommand.SUPPLY)


def test_node_red_sends_authenticated_post_and_parses_receipt() -> None:
    requests: list[object] = []

    def urlopen(request: object, _timeout: float) -> FakeResponse:
        requests.append(request)
        body = json.loads(request.data.decode())  # type: ignore[attr-defined]
        return FakeResponse(
            {"command": body["command"], "request_id": body["request_id"], "gpio": {"26": 1, "20": 1}, "flow_revision": "m1"}
        )

    receipt = NodeRedActuatorDriver(
        "http://127.0.0.1:1880/internal/freeze-protect/actuator",
        "hub-token",
        urlopen=urlopen,
    ).command(ActuatorCommand.DRAIN)

    assert receipt.command is ActuatorCommand.DRAIN
    assert requests[0].get_header("X-hub-token") == "hub-token"  # type: ignore[attr-defined]


def test_node_red_turns_transport_errors_into_adapter_errors() -> None:
    driver = NodeRedActuatorDriver(
        "http://127.0.0.1:1880/internal/freeze-protect/actuator",
        "hub-token",
        urlopen=lambda _request, _timeout: (_ for _ in ()).throw(URLError("offline")),
    )

    with pytest.raises(AdapterError, match="Node-RED"):
        driver.command(ActuatorCommand.DRAIN)
