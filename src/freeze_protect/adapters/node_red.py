from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol, Self, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request
from urllib.request import urlopen as stdlib_urlopen
from uuid import uuid4

from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import ActuatorCommand, ActuatorReceipt, SupplyAction

PROTOCOL_VERSION = 2


class _Response(Protocol):
    status: int

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...

    def read(self) -> bytes: ...


UrlOpen = Callable[[Request, float], _Response]


def _urlopen(request: Request, timeout: float) -> _Response:
    return cast(_Response, stdlib_urlopen(request, timeout=timeout))


class NodeRedActuatorDriver:
    def __init__(
        self,
        endpoint: str,
        hub_token: str,
        *,
        urlopen: UrlOpen = _urlopen,
        timeout_s: float = 3.0,
    ) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise ValueError("Node-RED endpoint must use http://127.0.0.1")
        if not hub_token:
            raise ValueError("Node-RED hub token must not be empty")
        self._endpoint = endpoint
        self._hub_token = hub_token
        self._urlopen = urlopen
        self._timeout_s = timeout_s

    def command(
        self, command: ActuatorCommand, *, supply_action: SupplyAction | None = None
    ) -> ActuatorReceipt:
        if (command is ActuatorCommand.SUPPLY) != (supply_action is not None):
            raise AdapterError("SUPPLY requires an action and DRAIN forbids one")
        request_id = str(uuid4())
        body: dict[str, object] = {
            "command": command.value,
            "request_id": request_id,
            "protocol_version": PROTOCOL_VERSION,
        }
        if supply_action is not None:
            body["supply_action"] = supply_action.value
        request = Request(
            self._endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Hub-Token": self._hub_token,
            },
            method="POST",
        )
        try:
            with self._urlopen(request, self._timeout_s) as response:
                if response.status != 200:
                    raise AdapterError("Node-RED returned a non-success status")
                payload = json.loads(response.read().decode("utf-8"))
        except AdapterError:
            raise
        except (HTTPError, URLError, OSError) as error:
            raise AdapterError(f"Node-RED request failed: {error}") from error
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as error:
            raise AdapterError(f"Node-RED response is invalid: {error}") from error
        return _receipt(payload, command, request_id, supply_action)


def _receipt(
    payload: object,
    command: ActuatorCommand,
    request_id: str,
    supply_action: SupplyAction | None,
) -> ActuatorReceipt:
    if not isinstance(payload, dict):
        raise AdapterError("Node-RED receipt must be an object")
    if (
        payload.get("command") != command.value
        or payload.get("request_id") != request_id
    ):
        raise AdapterError("Node-RED receipt does not match the request")
    if (
        type(payload.get("protocol_version")) is not int
        or payload["protocol_version"] != PROTOCOL_VERSION
    ):
        raise AdapterError("Node-RED receipt protocol version mismatch")
    if payload.get("supply_action") != (
        supply_action.value if supply_action is not None else None
    ):
        raise AdapterError("Node-RED receipt supply action mismatch")
    gpio = payload.get("gpio")
    if not isinstance(gpio, dict):
        raise AdapterError("Node-RED receipt has no GPIO map")
    try:
        return ActuatorReceipt(
            command=command,
            request_id=request_id,
            gpio_26=_gpio_level(gpio, "26"),
            gpio_20=_gpio_level(gpio, "20"),
            flow_revision=_string(payload, "flow_revision"),
            protocol_version=PROTOCOL_VERSION,
            supply_action=supply_action,
        )
    except (TypeError, ValueError) as error:
        raise AdapterError(f"Node-RED receipt is invalid: {error}") from error


def _gpio_level(payload: dict[object, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or value not in {0, 1}:
        raise ValueError(f"GPIO {key} must be 0 or 1")
    return int(value)


def _string(payload: dict[object, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value
