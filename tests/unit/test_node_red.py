from __future__ import annotations

import json
from typing import Self
from urllib.error import URLError

import pytest

from freeze_protect.adapters.node_red import NodeRedActuatorDriver
from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import ActuatorCommand, SupplyAction


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = json.dumps(payload).encode()
        self.status = status

    def __enter__(self) -> Self:
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
            {
                "command": "SUPPLY",
                "request_id": "r-1",
                "gpio": {"26": 0, "20": 1},
                "flow_revision": "m1",
                "protocol_version": 2,
                "supply_action": "begin",
            }
        ),
    )

    with pytest.raises(AdapterError, match="receipt"):
        driver.command(ActuatorCommand.SUPPLY, supply_action=SupplyAction.BEGIN)


def test_node_red_sends_authenticated_post_and_parses_receipt() -> None:
    requests: list[object] = []

    def urlopen(request: object, _timeout: float) -> FakeResponse:
        requests.append(request)
        body = json.loads(request.data.decode())  # type: ignore[attr-defined]
        return FakeResponse(
            {
                "command": body["command"],
                "request_id": body["request_id"],
                "gpio": {"26": 1, "20": 1},
                "flow_revision": "m1",
                "protocol_version": 2,
            }
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


def test_node_red_rejects_old_drain_receipt_before_supply() -> None:
    driver = NodeRedActuatorDriver(
        "http://127.0.0.1:1880/internal/freeze-protect/actuator",
        "hub-token",
        urlopen=lambda _request, _timeout: FakeResponse(
            {
                "command": "DRAIN",
                "request_id": "old",
                "gpio": {"26": 1, "20": 1},
                "flow_revision": "old",
            }
        ),
    )
    with pytest.raises(AdapterError):
        driver.command(ActuatorCommand.DRAIN)


def test_node_red_supply_requires_explicit_action_and_matching_receipt() -> None:
    requests: list[dict[str, object]] = []

    def urlopen(request: object, _timeout: float) -> FakeResponse:
        body = json.loads(request.data.decode())  # type: ignore[attr-defined]
        requests.append(body)
        return FakeResponse(
            {
                "command": "SUPPLY",
                "request_id": body["request_id"],
                "gpio": {"26": 0, "20": 0},
                "flow_revision": "v2",
                "protocol_version": 2,
                "supply_action": "renew",
            }
        )

    driver = NodeRedActuatorDriver(
        "http://127.0.0.1:1880/internal/freeze-protect/actuator",
        "hub-token",
        urlopen=urlopen,
    )
    with pytest.raises(AdapterError):
        driver.command(ActuatorCommand.SUPPLY)
    with pytest.raises(AdapterError):
        driver.command(ActuatorCommand.SUPPLY, supply_action=SupplyAction.BEGIN)
    assert requests == [
        {
            "command": "SUPPLY",
            "request_id": requests[0]["request_id"],
            "protocol_version": 2,
            "supply_action": "begin",
        }
    ]


@pytest.mark.parametrize(
    "error,code",
    [
        ("bridge is not ready in verified DRAIN", "bridge_not_ready"),
        ("SUPPLY request expired", "request_expired"),
        ("SUPPLY lease state rejects action", "lease_rejected"),
        ("paired GPIO executor stderr", "executor_stderr"),
        ("paired GPIO executor failed", "executor_failed"),
        ("paired GPIO readback not confirmed", "readback_unconfirmed"),
        ("private-token-must-not-leak", "unclassified"),
    ],
)
def test_http_503_retains_only_allowlisted_cause(error, code, caplog):
    import io
    from urllib.error import HTTPError

    calls = []
    response = HTTPError(
        "http://127.0.0.1/private",
        503,
        "private-reason",
        {},
        io.BytesIO(json.dumps({"error": error}).encode()),
    )

    def fail(request, timeout):
        calls.append(request)
        raise response

    driver = NodeRedActuatorDriver(
        "http://127.0.0.1:1880/internal/freeze-protect/actuator",
        "private-hub-token",
        urlopen=fail,
    )
    with pytest.raises(AdapterError) as caught:
        driver.command(ActuatorCommand.DRAIN)
    assert "http_status=503" in str(caught.value)
    assert "bridge_reason=" + code in str(caught.value)
    assert len(calls) == 1
    assert "private" not in str(caught.value) + caplog.text
    assert response.closed


@pytest.mark.parametrize("body", [b"not-json", b"[]", b'{"error":42}', b"x" * 5000])
def test_http_failure_diagnostic_handles_invalid_or_oversized_body(body):
    import io
    from urllib.error import HTTPError

    response = HTTPError("http://127.0.0.1/", 503, "unavailable", {}, io.BytesIO(body))

    def fail(request, timeout):
        raise response

    driver = NodeRedActuatorDriver(
        "http://127.0.0.1:1880/internal/freeze-protect/actuator",
        "hub-token",
        urlopen=fail,
    )
    with pytest.raises(AdapterError, match="bridge_reason=unclassified"):
        driver.command(ActuatorCommand.DRAIN)
    assert response.closed
