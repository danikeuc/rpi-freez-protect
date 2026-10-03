"""HTTP/service/SQLite/production driver/daemon traces, with no network or GPIO.

Only provider scheduling, Node-RED HTTP envelope and hardware registers are
substituted. The production driver constructs/validates every wire receipt.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Self
from urllib.error import URLError
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_paired_gpio_daemon import FakeRegisters, load_daemon
from test_weather_api import Worker

from freeze_protect.adapters.node_red import NodeRedActuatorDriver
from freeze_protect.api.app import create_app
from freeze_protect.application.weather_worker import WeatherResult
from freeze_protect.domain.models import ActuatorCommand, ControlMode

DISPLAY = {"X-Display-Token": "synthetic-display"}
WEATHER = {"X-Weather-Settings-Token": "synthetic-weather"}


class Response:
    def __init__(self, status, payload):
        self.status = status
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self):
        return self.payload


class Rig:
    def __init__(self, tmp_path, monkeypatch):
        self.elapsed = 100.0
        self.daemon = load_daemon()
        self.registers = FakeRegisters(self.daemon)
        self.levels = []
        write = self.registers.write32

        def traced_write(offset, mask):
            write(offset, mask)
            self.levels.append(self.registers.level & self.daemon.PAIR_MASK)

        self.registers.write32 = traced_write
        self.lease = self.daemon.SupplyLease(
            self.daemon.PairedGpio(self.registers), clock=lambda: self.elapsed
        )
        self.requests = []
        self.failure = None

        def transport(request, timeout):
            assert (
                request.full_url
                == "http://127.0.0.1:1880/internal/freeze-protect/actuator"
            )
            assert request.method == "POST" and timeout == 3.0
            assert request.get_header("X-hub-token") == "synthetic-hub"
            body = json.loads(request.data)
            assert set(body) <= {
                "command",
                "request_id",
                "protocol_version",
                "supply_action",
            }
            assert body["protocol_version"] == 2
            self.requests.append(body)
            result = self.daemon.execute_request(
                {**body, "deadline_unix_ms": self.elapsed * 1000 + 1500},
                self.lease,
                clock=lambda: self.elapsed * 1000,
            )
            if not result["ok"]:
                return Response(503, result)
            # These two fields belong to the substituted Node-RED envelope.
            result.update(
                request_id=body["request_id"], flow_revision="fixture-paired-v4"
            )
            if body.get("supply_action") == "begin" and self.failure == "lost_begin":
                raise URLError("synthetic lost receipt after daemon acceptance")
            if body.get("supply_action") == "begin" and self.failure == "wrong_action":
                result["supply_action"] = "renew"
            return Response(200, result)

        driver = NodeRedActuatorDriver(
            "http://127.0.0.1:1880/internal/freeze-protect/actuator",
            "synthetic-hub",
            urlopen=transport,
        )
        monkeypatch.setattr(
            "freeze_protect.api.app.SimulatedActuatorDriver", lambda: driver
        )
        monkeypatch.setattr("freeze_protect.api.app.WeatherWorker", Worker)
        self.app = create_app(
            tmp_path / "cross-layer.db",
            "synthetic-admin",
            "synthetic-display",
            True,
            weather_settings_token="synthetic-weather",
            control_mode=ControlMode.WEATHER_ASSISTED,
            run_background=False,
            clock=lambda: (
                datetime(2026, 10, 3, 10, tzinfo=UTC)
                + timedelta(seconds=self.elapsed - 100)
            ),
            monotonic_clock=lambda: self.elapsed,
        )
        assert self.app.state.relay_driver is driver
        self.client = TestClient(self.app)

    @property
    def store(self):
        return self.app.state.weather_store

    def status(self):
        response = self.client.get("/api/v1/display/status", headers=DISPLAY)
        assert response.status_code == 200
        return response.json()

    def payload(self, duration=None):
        status = self.status()
        result = {
            "request_id": str(uuid4()),
            "expected_control_revision": status["control_revision"],
            "action_nonce": status["action_nonce"],
        }
        if duration is not None:
            result["duration_seconds"] = duration
        return result

    def action(self, name, payload):
        return self.client.post(
            f"/api/v1/display/actions/{name}", headers=DISPLAY, json=payload
        )

    def enable(self):
        response = self.client.put(
            "/api/v1/display/weather-settings",
            headers=WEATHER,
            json={
                "expected_revision": self.store.load().settings.revision,
                "enabled": True,
                "latitude": 46.5,
                "longitude": 15.5,
                "timezone": "Europe/Ljubljana",
            },
        )
        assert response.status_code == 200

    def warm(self):
        self.app.state.weather_worker.warm()
        self.app.state.control_service.run_cycle()

    def pair_trace(self):
        assert self.levels
        assert set(self.levels) <= {0, self.daemon.PAIR_MASK}
        assert all(mask == self.daemon.PAIR_MASK for _, mask in self.registers.writes)
        status = self.status()
        expected = 0 if status["command"] == "SUPPLY" else self.daemon.PAIR_MASK
        assert self.registers.level & self.daemon.PAIR_MASK == expected

    def begins(self):
        return sum(body.get("supply_action") == "begin" for body in self.requests)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    rig = Rig(tmp_path, monkeypatch)
    with rig.client:
        yield rig
    assert rig.registers.level & rig.daemon.PAIR_MASK == rig.daemon.PAIR_MASK
    assert set(rig.levels) <= {0, rig.daemon.PAIR_MASK}


def test_auto_loss_stop_replay_and_deliberate_start_cross_all_layers(rig):
    rig.enable()
    rig.warm()
    assert rig.status()["operation"] == "AUTO_SUPPLY"
    assert rig.status()["remaining_seconds"] == 0
    assert rig.store.load().active_marker == "auto"
    stale_start = rig.payload(180)
    stop = rig.payload()
    stopped = rig.action("stop", stop)
    assert stopped.status_code == 200
    revision = stopped.json()["control_revision"]
    assert rig.store.load().user_off and rig.store.load().active_marker is None
    before = len(rig.requests)
    replay = rig.action("stop", stop)
    assert replay.status_code == 200 and replay.json()["control_revision"] == revision
    assert len(rig.requests) == before
    assert rig.action("start", stale_start).status_code == 409
    rig.app.state.control_service.run_cycle()
    assert rig.status()["operation"] == "USER_OFF" and rig.begins() == 1
    assert rig.action("start", rig.payload(180)).status_code == 200
    assert rig.status()["operation"] == "AUTO_SUPPLY" and rig.begins() == 2
    # Refresh latest attempt failure invalidates the still-young warm observation.
    for _ in range(30):
        rig.elapsed += 30
        rig.app.state.control_service.run_cycle()
    worker = rig.app.state.weather_worker
    worker.result = WeatherResult(
        worker.requests[-1], None, "synthetic unavailable", rig.elapsed
    )
    rig.app.state.control_service.run_cycle()
    assert rig.status()["operation"] == "MANUAL_IDLE"
    assert rig.status()["command"] == "DRAIN"
    assert not rig.status()["weather"]["eligible"]
    assert rig.store.load().active_marker is None
    before = len(rig.requests)
    rig.status()
    assert len(rig.requests) == before  # GET is not an actuator command.
    rig.pair_trace()


def test_manual_deadline_duplicates_and_old_client_compatibility(rig):
    request = rig.payload(60)
    accepted = rig.action("start", request)
    assert accepted.status_code == 200
    result_revision = accepted.json()["control_revision"]
    assert rig.status()["operation"] == "MANUAL_ACTIVE"
    assert rig.store.load().active_marker == "manual"
    rig.elapsed += 30
    before = len(rig.requests)
    replay = rig.action("start", request)
    assert (
        replay.status_code == 200
        and replay.json()["control_revision"] == result_revision
    )
    assert replay.json()["status"]["remaining_seconds"] == 30
    assert len(rig.requests) == before and rig.begins() == 1
    rig.enable()
    rig.warm()
    assert (
        rig.status()["remaining_seconds"] == 30
    )  # settings/forecast do not extend manual.
    rig.elapsed += 30
    status = rig.status()
    assert status["operation"] == "MANUAL_IDLE" and status["remaining_seconds"] == 0
    assert rig.store.load().active_marker is None and rig.begins() == 1
    # Compatibility fields remain meaningful for old clients during AUTO.
    rig.app.state.control_service.run_cycle()
    status = rig.status()
    assert status["operation"] == "AUTO_SUPPLY"
    assert status["command"] == "SUPPLY" and status["remaining_seconds"] == 0
    assert {
        "mode",
        "state",
        "command",
        "reason",
        "pipe_temperature_c",
        "sensor_health",
    } <= status.keys()
    before = len(rig.requests)
    legacy = rig.client.post(
        "/api/v1/display/actions/timed-shower",
        headers=DISPLAY,
        json={"duration_seconds": 60},
    )
    assert legacy.status_code == 200
    assert [body["command"] for body in rig.requests[before:]][:2] == [
        "DRAIN",
        "SUPPLY",
    ]
    assert rig.status()["operation"] == "MANUAL_ACTIVE"
    assert (
        rig.client.post("/api/v1/display/actions/drain", headers=DISPLAY).status_code
        == 200
    )
    assert rig.store.load().user_off
    assert (
        rig.client.post(
            "/api/v1/display/actions/timed-shower",
            headers=DISPLAY,
            json={"duration_seconds": 60},
        ).status_code
        == 409
    )
    rig.pair_trace()


@pytest.mark.parametrize("failure", ["expired_renew", "lost_begin", "wrong_action"])
def test_real_driver_fault_or_lease_refusal_never_replays_begin(rig, failure):
    rig.failure = failure
    rig.enable()
    rig.warm()
    if failure == "expired_renew":
        assert rig.status()["operation"] == "AUTO_SUPPLY"
        rig.elapsed += 60
        assert rig.lease.enforce()
        rig.app.state.control_service.run_cycle()
        assert [
            body.get("supply_action")
            for body in rig.requests
            if body["command"] == "SUPPLY"
        ] == ["begin", "renew"]
    assert rig.status()["operation"] == "FAULT"
    assert rig.store.load().fault_inhibited
    assert rig.begins() == 1
    for _ in range(3):
        rig.app.state.control_service.run_cycle()
    assert rig.begins() == 1
    assert rig.status()["command"] == ActuatorCommand.DRAIN.value
    rig.pair_trace()
