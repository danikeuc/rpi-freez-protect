from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from freeze_protect.adapters.max31865 import Max31865TemperatureSource
from freeze_protect.adapters.simulation import SimulatedTemperatureSource
from freeze_protect.api.app import create_app
from freeze_protect.application.temperature_telemetry import TemperatureTelemetrySampler
from freeze_protect.domain.models import (
    ActuatorCommand,
    ControlMode,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)
from freeze_protect.persistence.sqlite import SQLiteSettingsStore

ADMIN = {"X-Admin-Token": "admin-token"}
DISPLAY = {"X-Display-Token": "display-token"}


class FailingTemperatureSource:
    def read(self) -> object:
        raise OSError("temperature source read failed")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        database_path=tmp_path / "freeze-protect.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.MANUAL_TIMED,
        clock=lambda: datetime(2026, 9, 11, 12, tzinfo=UTC),
        run_background=False,
    )
    with TestClient(app) as test_client:
        yield test_client


def test_display_token_can_start_and_stop_only_a_server_timed_shower(
    client: TestClient,
) -> None:
    started = client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY)
    status = client.get("/api/v1/display/status", headers=DISPLAY)
    stopped = client.post("/api/v1/display/actions/drain", headers=DISPLAY)

    assert started.status_code == 200
    assert status.json()["state"] == "TIMED_SHOWER"
    assert status.json()["action"] == "CLOSE_NOW"
    assert status.json()["command"] == "SUPPLY"
    assert 0 < status.json()["remaining_seconds"] <= 600
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "MANUAL_DRAIN"


def test_default_api_mode_refuses_supply_and_reports_safe_drain(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / "safe.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        run_background=False,
    )
    relay = app.state.relay_driver

    with TestClient(app) as client:
        status = client.get("/api/v1/display/status", headers=DISPLAY)
        attempted = client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY)
        assert status.json()["mode"] == "safe_drain"
        assert status.json()["timed_shower_duration_supported"] is False
        assert status.json()["state"] == "SAFE_DRAIN"
        assert status.json()["command"] == "DRAIN"
        assert status.json()["remaining_seconds"] == 0
        assert status.json()["action_enabled"] is False
        assert attempted.status_code == 409

    assert all(command.value == "DRAIN" for command in relay.commands)


def test_manual_status_starts_idle_with_no_remaining_time(client: TestClient) -> None:
    payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert payload["mode"] == "manual_timed"
    assert payload["command"] == "DRAIN"
    assert payload["remaining_seconds"] == 0
    assert payload["action_enabled"] is True
    assert payload["timed_shower_duration_supported"] is True


@pytest.mark.parametrize("seconds", range(60, 601, 60))
def test_manual_duration_accepts_whole_minutes_api(
    client: TestClient, seconds: int
) -> None:
    response = client.post(
        "/api/v1/display/actions/timed-shower",
        headers=DISPLAY,
        json={"duration_seconds": seconds},
    )
    payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert response.status_code == 200
    assert payload["timed_shower_deadline"] == (
        datetime(2026, 9, 11, 12, tzinfo=UTC) + timedelta(seconds=seconds)
    ).isoformat()


@pytest.mark.parametrize("body", [
    b'{"duration_seconds":true}',
    b'{"duration_seconds":60.0}',
    b'{"duration_seconds":"60"}',
    b'{"duration_seconds":null}',
    b'{}',
    b'{"duration_seconds":60,"extra":1}',
    b'{"duration_seconds":60,"duration_seconds":120}',
    b'{"duration_seconds":0}',
    b'{"duration_seconds":59}',
    b'{"duration_seconds":61}',
    b'{"duration_seconds":601}',
    b'{"duration_seconds":NaN}',
    b'{"duration_seconds":Infinity}',
    b'{"duration_seconds":-Infinity}',
    b'{"duration_seconds":60}' + b' ' * 256,
    b'[60]',
])
def test_duration_body_rejects_invalid_without_actuation(
    client: TestClient, body: bytes
) -> None:
    relay = client.app.state.relay_driver
    before = len(relay.commands)

    response = client.post(
        "/api/v1/display/actions/timed-shower", headers=DISPLAY,
        content=body,
    )

    assert response.status_code == 400
    assert len(relay.commands) == before


def test_short_duration_expires_with_disconnected_client(client: TestClient) -> None:
    service = client.app.state.control_service
    ticks = [100.0]
    service._monotonic_clock = lambda: ticks[0]
    relay = client.app.state.relay_driver
    response = client.post(
        "/api/v1/display/actions/timed-shower",
        headers=DISPLAY,
        json={"duration_seconds": 60},
    )
    assert response.status_code == 200

    ticks[0] = 160.0
    decision = service.run_cycle()

    assert decision.reason == "timed_shower_expired"
    assert [command.value for command in relay.commands] == ["DRAIN", "SUPPLY", "DRAIN"]


def test_explicit_duration_rejected_during_active_automatic_shower_api(
    tmp_path: Path,
) -> None:
    app = create_app(
        database_path=tmp_path / "automatic.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.AUTOMATIC,
        clock=lambda: datetime(2026, 9, 11, 12, tzinfo=UTC),
        run_background=False,
    )
    relay = app.state.relay_driver
    with TestClient(app) as automatic_client:
        started = automatic_client.post(
            "/api/v1/display/actions/timed-shower", headers=DISPLAY
        )
        assert started.status_code == 200
        original_deadline = app.state.control_service.status().timed_shower_deadline
        before = list(relay.commands)

        rejected = automatic_client.post(
            "/api/v1/display/actions/timed-shower",
            headers=DISPLAY,
            json={"duration_seconds": 60},
        )

        assert rejected.status_code == 409
        assert rejected.json()["detail"] == "manual_duration_requires_manual_mode"
        assert app.state.control_service.status().timed_shower_deadline == original_deadline
        assert relay.commands == before
        assert automatic_client.get("/api/v1/display/status", headers=DISPLAY).json()[
            "command"
        ] == "SUPPLY"


def test_duplicate_start_does_not_extend_display_countdown(client: TestClient) -> None:
    service = client.app.state.control_service
    ticks = [100.0]
    service._monotonic_clock = lambda: ticks[0]

    first = client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY)
    ticks[0] = 101.25
    second = client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY)
    payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert first.status_code == 200
    assert second.status_code == 200
    assert payload["command"] == "SUPPLY"
    assert payload["remaining_seconds"] == 599


def test_display_status_drains_at_exact_expiry(client: TestClient) -> None:
    service = client.app.state.control_service
    ticks = [100.0]
    service._monotonic_clock = lambda: ticks[0]
    relay = client.app.state.relay_driver
    assert client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY).status_code == 200

    ticks[0] = 700.0
    payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert payload["state"] == "MANUAL_DRAIN"
    assert payload["command"] == "DRAIN"
    assert payload["remaining_seconds"] == 0
    assert relay.commands[-1].value == "DRAIN"


@pytest.mark.parametrize("route,method", [
    ("/api/v1/display/status", "get"),
    ("/api/v1/display/actions/timed-shower", "post"),
    ("/api/v1/display/actions/drain", "post"),
])
@pytest.mark.parametrize("headers", [{}, ADMIN, {"X-Display-Token": "wrong-token"}])
def test_all_display_routes_reject_invalid_tokens(
    client: TestClient, route: str, method: str, headers: dict[str, str]
) -> None:
    relay = client.app.state.relay_driver
    before = list(relay.commands)
    response = getattr(client, method)(route, headers=headers)

    assert response.status_code == 401
    assert relay.commands == before


@pytest.mark.parametrize("route", [
    "/api/v1/display/actions/timed-shower",
    "/api/v1/display/actions/drain",
])
def test_display_actions_reject_request_body_without_actuation(
    client: TestClient, route: str
) -> None:
    relay = client.app.state.relay_driver
    before = list(relay.commands)

    response = client.post(route, headers=DISPLAY, json={"duration_s": 30})

    assert response.status_code == 400
    assert relay.commands == before


def test_unrelated_request_completes_while_supply_bridge_is_blocked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    relay = client.app.state.relay_driver
    original_command = relay.command
    entered = Event()
    release = Event()

    def blocking_command(command: ActuatorCommand, *, supply_action=None) -> object:
        if command is ActuatorCommand.SUPPLY:
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("test did not release the simulated bridge")
        return original_command(command, supply_action=supply_action)

    monkeypatch.setattr(relay, "command", blocking_command)
    with ThreadPoolExecutor(max_workers=2) as requests:
        action = requests.submit(
            client.post, "/api/v1/display/actions/timed-shower", headers=DISPLAY
        )
        assert entered.wait(timeout=2)
        unrelated = requests.submit(client.get, "/api/v1/settings", headers=ADMIN)
        try:
            response = unrelated.result(timeout=1)
        finally:
            release.set()
        assert response.status_code == 200
        assert action.result(timeout=2).status_code == 200


def test_manual_start_conflicts_when_configured_max_is_under_ten_minutes(
    client: TestClient,
) -> None:
    settings = client.get("/api/v1/settings", headers=ADMIN).json()
    settings["settings_version"] += 1
    settings["timed_shower_max_s"] = 599
    settings["timed_shower_default_s"] = 599
    assert client.put("/api/v1/settings", headers=ADMIN, json=settings).status_code == 200
    relay = client.app.state.relay_driver
    before = list(relay.commands)

    response = client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY)

    assert response.status_code == 409
    assert relay.commands == before
    assert client.get("/api/v1/display/status", headers=DISPLAY).json()["command"] == "DRAIN"


def test_start_at_expired_boundary_conflicts_without_new_supply(
    client: TestClient,
) -> None:
    service = client.app.state.control_service
    ticks = [100.0]
    service._monotonic_clock = lambda: ticks[0]
    relay = client.app.state.relay_driver
    assert client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY).status_code == 200

    ticks[0] = 700.0
    response = client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY)

    assert response.status_code == 409
    assert [command.value for command in relay.commands] == ["DRAIN", "SUPPLY", "DRAIN"]


def test_display_status_has_no_admin_or_secret_values(client: TestClient) -> None:
    payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert "last_reading" not in payload
    assert "sensor_diagnostics" not in payload
    assert "bridge_flow_revision" not in payload
    assert "observed_at" not in str(payload)
    assert "source_id" not in str(payload)
    assert "/dev/spidev" not in str(payload)
    assert "fault_register" not in str(payload)
    assert "fault_names" not in str(payload)
    assert "admin-token" not in str(payload)
    assert "display-token" not in str(payload)


def test_timed_shower_request_wakes_the_control_loop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    def record_wake(loop: object) -> None:
        calls.append(loop)

    monkeypatch.setattr("freeze_protect.api.app.PeriodicControlLoop.wake", record_wake)
    response = client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY)

    assert response.status_code == 200
    assert len(calls) == 1


def test_hub_shutdown_reasserts_drain_after_an_active_timed_shower(
    tmp_path: Path,
) -> None:
    app = create_app(
        database_path=tmp_path / "freeze-protect.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.MANUAL_TIMED,
        clock=lambda: datetime(2026, 9, 11, 12, tzinfo=UTC),
        run_background=False,
    )
    relay = app.state.relay_driver

    with TestClient(app) as client:
        response = client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY)
        assert response.status_code == 200

    assert [command.value for command in relay.commands] == [
        "DRAIN",
        "SUPPLY",
        "DRAIN",
    ]


def test_display_status_rejects_missing_admin_or_wrong_token_without_actuation(
    client: TestClient,
) -> None:
    relay = client.app.state.relay_driver
    before = list(relay.commands)

    assert client.get("/api/v1/display/status").status_code == 401
    assert client.get("/api/v1/display/status", headers=ADMIN).status_code == 401
    assert client.get(
        "/api/v1/display/status", headers={"X-Display-Token": "arbitrary-wrong-token"}
    ).status_code == 401
    assert relay.commands == before
    assert client.get("/api/v1/display/status", headers=DISPLAY).status_code == 200


def test_display_status_preserves_legacy_valve_fields_with_unavailable_sensor(
    client: TestClient,
) -> None:
    payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert payload == {
        "mode": "manual_timed",
        "command": "DRAIN",
        "remaining_seconds": 0,
        "state": "MANUAL_DRAIN",
        "reason": "manual_idle",
        "forecast": {"available": False, "fresh": False, "dates": [], "minima_c": []},
        "timed_shower_deadline": None,
        "timed_shower_duration_supported": True,
        "action": "TIMED_SHOWER",
        "action_enabled": True,
        "pipe_temperature_c": None,
        "sensor_health": "STALE",
    }


@pytest.mark.parametrize("mode", [ControlMode.MANUAL_TIMED, ControlMode.SAFE_DRAIN])
@pytest.mark.parametrize(
    ("health", "expected_value"),
    [
        (SensorHealth.HEALTHY, 6.4),
        (SensorHealth.STALE, None),
        (SensorHealth.INVALID, None),
        (SensorHealth.CALIBRATION_REQUIRED, None),
    ],
)
def test_nonautomatic_display_uses_sampler_health_snapshot(
    tmp_path: Path, mode: ControlMode, health: SensorHealth, expected_value: float | None
) -> None:
    observed_at = datetime(2026, 9, 11, 12, tzinfo=UTC)
    app = create_app(
        database_path=tmp_path / f"{mode.value}-{health.value}.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=mode,
        clock=lambda: observed_at,
        run_background=False,
    )
    with TestClient(app) as client:
        source = app.state.temperature_source
        source.set(TemperatureReading(6.4, observed_at, health))
        sampler = app.state.temperature_telemetry_sampler
        assert sampler is not None
        sampler.sample_once()
        payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert payload["pipe_temperature_c"] == expected_value
    assert payload["sensor_health"] == health.value


def test_manual_display_discards_previous_value_after_source_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = client.app.state.temperature_source
    sampler = client.app.state.temperature_telemetry_sampler
    assert sampler is not None
    source.set(
        TemperatureReading(
            6.4, datetime(2026, 9, 11, 12, tzinfo=UTC), SensorHealth.HEALTHY
        )
    )
    sampler.sample_once()
    assert client.get("/api/v1/display/status", headers=DISPLAY).json()[
        "pipe_temperature_c"
    ] == 6.4

    def fail_read() -> TemperatureReading:
        raise OSError("sensor unavailable")

    monkeypatch.setattr(source, "read", fail_read)
    sampler.sample_once()
    payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert payload["pipe_temperature_c"] is None
    assert payload["sensor_health"] == "STALE"


@pytest.mark.parametrize(
    ("age_seconds", "expected_value", "expected_health"),
    [
        (14.999, 6.4, "HEALTHY"),
        (15.0, None, "STALE"),
        (-0.001, None, "STALE"),
    ],
)
def test_automatic_display_uses_injected_clock_for_freshness(
    tmp_path: Path,
    age_seconds: float,
    expected_value: float | None,
    expected_health: str,
) -> None:
    observed_at = datetime(2026, 9, 11, 12, tzinfo=UTC)
    current_time = [observed_at]
    app = create_app(
        database_path=tmp_path / "automatic-freshness.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.AUTOMATIC,
        clock=lambda: current_time[0],
        run_background=False,
    )
    with TestClient(app) as client:
        assert app.state.temperature_telemetry_sampler is None
        app.state.temperature_source.set(
            TemperatureReading(6.4, observed_at, SensorHealth.HEALTHY)
        )
        app.state.control_service.run_cycle()
        current_time[0] = observed_at + timedelta(seconds=age_seconds)
        payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert payload["pipe_temperature_c"] == expected_value
    assert payload["sensor_health"] == expected_health


@pytest.mark.parametrize(
    "health",
    [SensorHealth.STALE, SensorHealth.INVALID, SensorHealth.CALIBRATION_REQUIRED],
)
def test_automatic_display_hides_unhealthy_numeric_reading(
    tmp_path: Path, health: SensorHealth
) -> None:
    observed_at = datetime(2026, 9, 11, 12, tzinfo=UTC)
    app = create_app(
        database_path=tmp_path / f"automatic-{health.value}.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.AUTOMATIC,
        clock=lambda: observed_at,
        run_background=False,
    )
    with TestClient(app) as client:
        app.state.temperature_source.set(TemperatureReading(6.4, observed_at, health))
        app.state.control_service.run_cycle()
        payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert payload["pipe_temperature_c"] is None
    assert payload["sensor_health"] == health.value


def test_uncommissioned_healthy_temperature_is_visible_to_display(
    tmp_path: Path,
) -> None:
    app = create_app(
        database_path=tmp_path / "automatic.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.AUTOMATIC,
        clock=lambda: datetime(2026, 9, 11, 12, tzinfo=UTC),
        run_background=False,
    )
    with TestClient(app) as client:
        _assert_uncommissioned_temperature_visibility(client)


def _assert_uncommissioned_temperature_visibility(client: TestClient) -> None:
    service = client.app.state.control_service
    service._temperature_source = SimulatedTemperatureSource(
        TemperatureReading(
            8.4, datetime(2026, 9, 11, 12, tzinfo=UTC), SensorHealth.HEALTHY
        )
    )

    decision = service.run_cycle()
    admin_status = client.get("/api/v1/status", headers=ADMIN).json()
    display_status = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert decision.reason == "sensor_pending"
    assert admin_status["state"] == "FROST_PROTECTION"
    assert admin_status["last_reading"]["value_c"] == 8.4
    assert admin_status["last_reading"]["health"] == "HEALTHY"
    assert display_status["pipe_temperature_c"] == 8.4
    assert display_status["sensor_health"] == "HEALTHY"


def test_status_and_settings_are_administrator_only(client: TestClient) -> None:
    assert client.get("/api/v1/status").status_code == 401
    assert client.get("/api/v1/status", headers=ADMIN).json()["state"] == "MANUAL_DRAIN"
    settings = client.get("/api/v1/settings", headers=ADMIN)

    assert settings.status_code == 200
    assert settings.json()["sensor_commissioned"] is False
    assert "display_token" not in settings.json()


def test_settings_persistence_failure_latches_fault_and_returns_service_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = client.get("/api/v1/settings", headers=ADMIN).json()
    settings["settings_version"] = 2

    def fail_save(_self: object, _settings: object) -> object:
        raise OSError("disk is read-only")

    monkeypatch.setattr(
        "freeze_protect.api.app.SQLiteSettingsStore.save",
        fail_save,
    )
    response = client.put("/api/v1/settings", headers=ADMIN, json=settings)

    assert response.status_code == 503
    assert client.app.state.control_service.status().state.value == "FAULT"


def test_settings_update_fails_closed_when_sensor_configuration_read_fails(
    tmp_path: Path,
) -> None:
    app = create_app(
        database_path=tmp_path / "freeze-protect.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.AUTOMATIC,
        clock=lambda: datetime(2026, 9, 11, 12, tzinfo=UTC),
        run_background=False,
    )
    with TestClient(app) as client:
        app.state.control_service._temperature_source = FailingTemperatureSource()
        settings = client.get("/api/v1/settings", headers=ADMIN).json()
        settings["settings_version"] = 2
        response = client.put("/api/v1/settings", headers=ADMIN, json=settings)

    assert response.status_code == 503
    assert app.state.control_service.status().state.value == "FAULT"


def test_production_mode_does_not_expose_simulation_route(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / "production.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=False,
        node_red_url="http://127.0.0.1:1880/internal/freeze-protect/actuator",
        node_red_token="node-red-token",
        run_background=False,
    )

    with TestClient(app) as client:
        assert (
            client.post("/api/v1/simulation/temperature", headers=ADMIN).status_code
            == 404
        )


def test_production_app_selects_max31865_without_accessing_spi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_spidev_is_imported(_name: str) -> object:
        raise AssertionError("SPI must remain lazy during app construction")

    monkeypatch.setattr(
        "freeze_protect.adapters.max31865.import_module",
        fail_if_spidev_is_imported,
    )

    app = create_app(
        database_path=tmp_path / "production.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=False,
        node_red_url="http://127.0.0.1:1880/internal/freeze-protect/actuator",
        node_red_token="node-red-token",
        run_background=False,
    )

    assert isinstance(app.state.temperature_source, Max31865TemperatureSource)
    assert app.state.temperature_source.diagnostics()["device"] == "/dev/spidev0.0"


def test_production_upgrade_invalidates_legacy_sensor_commissioning_once(
    tmp_path: Path,
) -> None:
    database = tmp_path / "production.db"
    SQLiteSettingsStore(database).save(
        SafetySettings(
            sensor_device_id="28-00000legacy",
            sensor_commissioned=True,
            settings_version=1,
        )
    )

    first = create_app(
        database_path=database,
        admin_token="admin-token",
        display_token="display-token",
        development_mode=False,
        run_background=False,
    )
    second = create_app(
        database_path=database,
        admin_token="admin-token",
        display_token="display-token",
        development_mode=False,
        run_background=False,
    )

    assert first.state.control_service.settings.sensor_commissioned is False
    assert first.state.control_service.settings.settings_version == 2
    assert second.state.control_service.settings == first.state.control_service.settings


@pytest.mark.parametrize("mode", [ControlMode.MANUAL_TIMED, ControlMode.SAFE_DRAIN])
def test_temperature_telemetry_is_the_only_nonautomatic_sensor_reader(
    tmp_path: Path, mode: ControlMode, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(
        database_path=tmp_path / f"{mode.value}.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=mode,
        clock=lambda: datetime(2026, 9, 11, 12, tzinfo=UTC),
        run_background=False,
    )
    sampler = app.state.temperature_telemetry_sampler
    source = app.state.temperature_source
    reads: list[object] = []
    original_read = source.read

    def record_read() -> TemperatureReading:
        reads.append(source)
        return original_read()

    monkeypatch.setattr(source, "read", record_read)
    assert sampler is not None
    assert sampler._source is source
    monkeypatch.setattr(
        sampler,
        "start",
        lambda: pytest.fail("run_background=False must not start telemetry"),
    )

    with TestClient(app):
        app.state.control_service.run_cycle()
        assert reads == []
        sampler.sample_once()
        assert reads == [source]
        app.state.control_service.run_cycle()
        assert reads == [source]


def test_automatic_control_is_the_only_temperature_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_sampler_construction(_sampler: object, *_args: object, **_kwargs: object) -> None:
        pytest.fail("automatic mode must not construct a telemetry sampler")

    monkeypatch.setattr(TemperatureTelemetrySampler, "__init__", reject_sampler_construction)
    app = create_app(
        database_path=tmp_path / "automatic-ownership.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.AUTOMATIC,
        clock=lambda: datetime(2026, 9, 11, 12, tzinfo=UTC),
        run_background=False,
    )
    source = app.state.temperature_source
    source.set(
        TemperatureReading(
            8.4, datetime(2026, 9, 11, 12, tzinfo=UTC), SensorHealth.HEALTHY
        )
    )
    reads: list[object] = []
    original_read = source.read

    def record_read() -> TemperatureReading:
        reads.append(source)
        return original_read()

    monkeypatch.setattr(source, "read", record_read)
    assert app.state.temperature_telemetry_sampler is None

    with TestClient(app) as client:
        startup_reads = len(reads)
        assert startup_reads == 1
        app.state.control_service.run_cycle()
        assert len(reads) == startup_reads + 1
        assert app.state.control_service.status().last_reading == TemperatureReading(
            8.4, datetime(2026, 9, 11, 12, tzinfo=UTC), SensorHealth.HEALTHY
        )
        assert client.get("/api/v1/display/status", headers=DISPLAY).status_code == 200
        assert len(reads) == startup_reads + 1


@pytest.mark.parametrize("mode", [ControlMode.MANUAL_TIMED, ControlMode.SAFE_DRAIN])
def test_temperature_telemetry_lifespan_order(
    tmp_path: Path, mode: ControlMode, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(
        database_path=tmp_path / f"{mode.value}-lifespan.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=mode,
        run_background=True,
    )
    service = app.state.control_service
    calls: list[str] = []
    original_startup = service.startup
    original_drain = service.drain

    def record_startup() -> object:
        calls.append("service.startup")
        return original_startup()

    def record_drain(reason: str) -> object:
        calls.append(f"service.drain:{reason}")
        return original_drain(reason)

    monkeypatch.setattr(service, "startup", record_startup)
    monkeypatch.setattr(service, "drain", record_drain)
    monkeypatch.setattr(
        "freeze_protect.api.app.TemperatureTelemetrySampler.start",
        lambda _sampler: calls.append("sampler.start"),
    )
    monkeypatch.setattr(
        "freeze_protect.api.app.TemperatureTelemetrySampler.stop",
        lambda _sampler: calls.append("sampler.stop"),
    )
    monkeypatch.setattr(
        "freeze_protect.api.app.PeriodicControlLoop.start",
        lambda _loop: calls.append("loop.start"),
    )
    monkeypatch.setattr(
        "freeze_protect.api.app.PeriodicControlLoop.stop",
        lambda _loop: calls.append("loop.stop"),
    )

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        calls.append("request.served")

    assert calls == [
        "service.startup",
        "sampler.start",
        "loop.start",
        "request.served",
        "sampler.stop",
        "loop.stop",
        "service.drain:shutdown_drain",
    ]


@pytest.mark.parametrize("failing_start", ["sampler", "loop"])
def test_temperature_telemetry_start_failure_still_drains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_start: str
) -> None:
    app = create_app(
        database_path=tmp_path / f"{failing_start}-startup.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.MANUAL_TIMED,
        run_background=True,
    )
    service = app.state.control_service
    relay = app.state.relay_driver
    calls: list[str] = []
    original_startup = service.startup
    original_drain = service.drain

    def record_startup() -> object:
        calls.append("service.startup")
        return original_startup()

    def record_drain(reason: str) -> object:
        calls.append(f"service.drain:{reason}")
        return original_drain(reason)

    def start_sampler(_sampler: object) -> None:
        calls.append("sampler.start")
        if failing_start == "sampler":
            raise RuntimeError("sampler startup failed")

    def start_loop(_loop: object) -> None:
        calls.append("loop.start")
        if failing_start == "loop":
            raise RuntimeError("loop startup failed")

    monkeypatch.setattr(service, "startup", record_startup)
    monkeypatch.setattr(service, "drain", record_drain)
    monkeypatch.setattr(TemperatureTelemetrySampler, "start", start_sampler)
    monkeypatch.setattr(
        TemperatureTelemetrySampler,
        "stop",
        lambda _sampler: calls.append("sampler.stop"),
    )
    monkeypatch.setattr("freeze_protect.api.app.PeriodicControlLoop.start", start_loop)
    monkeypatch.setattr(
        "freeze_protect.api.app.PeriodicControlLoop.stop",
        lambda _loop: calls.append("loop.stop"),
    )

    with pytest.raises(RuntimeError, match=f"{failing_start} startup failed"), TestClient(app):
        pytest.fail("request serving must not begin after startup failure")

    expected_start = ["sampler.start"]
    if failing_start == "loop":
        expected_start.append("loop.start")
    assert calls == [
        "service.startup",
        *expected_start,
        "sampler.stop",
        "loop.stop",
        "service.drain:shutdown_drain",
    ]
    assert [command.value for command in relay.commands] == ["DRAIN", "DRAIN"]


def test_temperature_telemetry_stop_failure_still_stops_loop_and_drains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(
        database_path=tmp_path / "stop-failure.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=ControlMode.MANUAL_TIMED,
        run_background=True,
    )
    service = app.state.control_service
    relay = app.state.relay_driver
    calls: list[str] = []
    original_drain = service.drain

    def record_drain(reason: str) -> object:
        calls.append(f"service.drain:{reason}")
        return original_drain(reason)

    def fail_sampler_stop(_sampler: object) -> None:
        calls.append("sampler.stop")
        raise RuntimeError("sampler stop failed")

    monkeypatch.setattr(service, "drain", record_drain)
    monkeypatch.setattr(
        TemperatureTelemetrySampler,
        "start",
        lambda _sampler: calls.append("sampler.start"),
    )
    monkeypatch.setattr(TemperatureTelemetrySampler, "stop", fail_sampler_stop)
    monkeypatch.setattr(
        "freeze_protect.api.app.PeriodicControlLoop.start",
        lambda _loop: calls.append("loop.start"),
    )
    monkeypatch.setattr(
        "freeze_protect.api.app.PeriodicControlLoop.stop",
        lambda _loop: calls.append("loop.stop"),
    )

    with pytest.raises(RuntimeError, match="sampler stop failed"), TestClient(app):
        calls.append("request.served")

    assert calls == [
        "sampler.start",
        "loop.start",
        "request.served",
        "sampler.stop",
        "loop.stop",
        "service.drain:shutdown_drain",
    ]
    assert [command.value for command in relay.commands] == ["DRAIN", "DRAIN"]


@pytest.mark.parametrize("failing", [False, True])
def test_temperature_telemetry_sample_cannot_change_manual_valve_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, failing: bool
) -> None:
    sampler = client.app.state.temperature_telemetry_sampler
    source = client.app.state.temperature_source
    service = client.app.state.control_service
    relay = client.app.state.relay_driver
    assert sampler is not None
    if failing:
        def fail_read() -> TemperatureReading:
            raise OSError("sensor unavailable")

        monkeypatch.setattr(source, "read", fail_read)
    else:
        source.set(
            TemperatureReading(
                8.4, datetime(2026, 9, 11, 12, tzinfo=UTC), SensorHealth.HEALTHY
            )
        )
    before_status = service.status()
    before_commands = list(relay.commands)

    sampler.sample_once()

    assert service.status() == before_status
    assert relay.commands == before_commands
    assert sampler.snapshot().health is (
        SensorHealth.STALE if failing else SensorHealth.HEALTHY
    )


@pytest.mark.parametrize("mode", [ControlMode.MANUAL_TIMED, ControlMode.SAFE_DRAIN])
def test_lifespan_drains_while_temperature_source_read_remains_blocked(
    tmp_path: Path, mode: ControlMode, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(
        database_path=tmp_path / f"{mode.value}-blocked-telemetry.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
        control_mode=mode,
        run_background=True,
    )
    source = app.state.temperature_source
    sampler = app.state.temperature_telemetry_sampler
    service = app.state.control_service
    relay = app.state.relay_driver
    read_started = Event()
    read_release = Event()
    reads: list[object] = []
    original_read = source.read

    def blocked_read() -> TemperatureReading:
        reads.append(source)
        read_started.set()
        read_release.wait()
        return original_read()

    def run_lifespan() -> None:
        with TestClient(app):
            assert read_started.wait(timeout=0.5)

    monkeypatch.setattr(source, "read", blocked_read)
    with ThreadPoolExecutor(max_workers=1) as executor:
        lifespan = executor.submit(run_lifespan)
        try:
            assert read_started.wait(timeout=0.5)
            lifespan.result(timeout=2.0)

            assert not read_release.is_set()
            assert sampler._thread.is_alive()
            assert service.status().reason == "shutdown_drain"
            assert relay.commands[-1] is ActuatorCommand.DRAIN
            assert all(command is ActuatorCommand.DRAIN for command in relay.commands)
        finally:
            read_release.set()
            lifespan.result(timeout=2.0)
            sampler.stop()

    assert not sampler._thread.is_alive()
    assert reads == [source]
