from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from freeze_protect.api.app import create_app

ADMIN = {"X-Admin-Token": "admin-token"}
DISPLAY = {"X-Display-Token": "display-token"}


class FailingTemperatureSource:
    def read(self) -> object:
        raise OSError("DS18B20 settings read failed")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        database_path=tmp_path / "freeze-protect.db",
        admin_token="admin-token",
        display_token="display-token",
        development_mode=True,
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


def test_status_and_settings_are_administrator_only(client: TestClient) -> None:
    assert client.get("/api/v1/status").status_code == 401
    assert client.get("/api/v1/status", headers=ADMIN).json()["state"] == "FROST_PROTECTION"
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
