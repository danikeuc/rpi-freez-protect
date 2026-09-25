from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from freeze_protect.adapters.max31865 import Max31865TemperatureSource
from freeze_protect.adapters.simulation import SimulatedTemperatureSource
from freeze_protect.api.app import create_app
from freeze_protect.domain.models import (
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)
from freeze_protect.persistence.sqlite import SQLiteSettingsStore

ADMIN = {"X-Admin-Token": "admin-token"}
DISPLAY = {"X-Display-Token": "display-token"}
INTEGRATION = {"X-Integration-Token": "integration-token"}


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
        clock=lambda: datetime(2026, 9, 11, 12, tzinfo=UTC),
        run_background=False,
        integration_token="integration-token",
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
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "FROST_PROTECTION"


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


def test_hub_shutdown_reasserts_drain_after_an_active_timed_shower(tmp_path: Path) -> None:
    app = create_app(
        database_path=tmp_path / "freeze-protect.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
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


def test_missing_or_admin_token_on_display_endpoint_is_rejected(
    client: TestClient,
) -> None:
    assert client.get("/api/v1/display/status").status_code == 401
    assert client.get("/api/v1/display/status", headers=ADMIN).status_code == 401
    assert client.get("/api/v1/display/status", headers=DISPLAY).status_code == 200


def test_display_status_does_not_expose_sensor_diagnostics(client: TestClient) -> None:
    payload = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert "pipe_temperature_c" not in payload
    assert "sensor_health" not in payload


def test_uncommissioned_healthy_temperature_is_visible_only_to_administrator(
    client: TestClient,
) -> None:
    service = client.app.state.control_service
    service._temperature_source = SimulatedTemperatureSource(
        TemperatureReading(8.4, datetime(2026, 9, 11, 12, tzinfo=UTC), SensorHealth.HEALTHY)
    )

    decision = service.run_cycle()
    admin_status = client.get("/api/v1/status", headers=ADMIN).json()
    display_status = client.get("/api/v1/display/status", headers=DISPLAY).json()

    assert decision.reason == "sensor_pending"
    assert admin_status["state"] == "FROST_PROTECTION"
    assert admin_status["last_reading"]["value_c"] == 8.4
    assert admin_status["last_reading"]["health"] == "HEALTHY"
    assert "pipe_temperature_c" not in display_status


def test_status_and_settings_are_administrator_only(client: TestClient) -> None:
    assert client.get("/api/v1/status").status_code == 401
    assert client.get("/api/v1/status", headers=ADMIN).json()["state"] == "FROST_PROTECTION"
    settings = client.get("/api/v1/settings", headers=ADMIN)

    assert settings.status_code == 200
    assert settings.json()["sensor_commissioned"] is False
    assert "display_token" not in settings.json()


def test_uhc_integration_token_reads_only_status_and_settings(
    client: TestClient,
) -> None:
    relay = client.app.state.relay_driver
    commands_before = list(relay.commands)

    status = client.get("/api/v1/integrations/uhc/status", headers=INTEGRATION)
    settings = client.get("/api/v1/integrations/uhc/settings", headers=INTEGRATION)

    assert status.status_code == 200
    assert status.json()["state"] == "FROST_PROTECTION"
    assert settings.status_code == 200
    assert settings.json()["timed_shower_default_s"] == 600
    assert relay.commands == commands_before


def test_uhc_integration_token_is_distinct_from_admin_and_display_tokens(
    client: TestClient,
) -> None:
    for headers in ({}, ADMIN, DISPLAY):
        assert (
            client.get("/api/v1/integrations/uhc/status", headers=headers).status_code
            == 401
        )

    assert (
        client.get("/api/v1/status", headers=INTEGRATION).status_code == 401
    )
    assert (
        client.get("/api/v1/display/status", headers=INTEGRATION).status_code == 401
    )


def test_uhc_integration_token_updates_validated_settings_without_supply(
    client: TestClient,
) -> None:
    relay = client.app.state.relay_driver
    commands_before = list(relay.commands)
    settings = client.get("/api/v1/settings", headers=ADMIN).json()
    settings["timed_shower_default_s"] = 900
    settings["settings_version"] += 1

    response = client.put(
        "/api/v1/integrations/uhc/settings",
        headers=INTEGRATION,
        json=settings,
    )

    assert response.status_code == 200
    assert response.json()["timed_shower_default_s"] == 900
    assert "SUPPLY" not in [command.value for command in relay.commands[ len(commands_before) :]]


def test_uhc_integration_settings_reject_invalid_policy(
    client: TestClient,
) -> None:
    settings = client.get("/api/v1/settings", headers=ADMIN).json()
    settings["timed_shower_default_s"] = 1_900
    settings["settings_version"] += 1

    response = client.put(
        "/api/v1/integrations/uhc/settings",
        headers=INTEGRATION,
        json=settings,
    )

    assert response.status_code == 422


def test_uhc_integration_cannot_commission_or_replace_the_sensor(client: TestClient) -> None:
    settings = client.get(
        "/api/v1/integrations/uhc/settings", headers=INTEGRATION
    ).json()
    settings["sensor_commissioned"] = True
    settings["sensor_device_id"] = "28-000000000000"
    settings["settings_version"] += 1

    response = client.put(
        "/api/v1/integrations/uhc/settings", headers=INTEGRATION, json=settings
    )
    persisted = client.get(
        "/api/v1/integrations/uhc/settings", headers=INTEGRATION
    ).json()

    assert response.status_code == 403
    assert persisted["sensor_commissioned"] is False
    assert persisted["sensor_device_id"] is None


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
        assert client.post("/api/v1/simulation/temperature", headers=ADMIN).status_code == 404


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
