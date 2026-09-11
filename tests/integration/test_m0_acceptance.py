from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from freeze_protect.api.app import create_app
from freeze_protect.domain.models import ControllerState, RelayCommand

ADMIN = {"X-Admin-Token": "test-token"}


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def clear_startup_fault(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/simulation/temperature",
            headers=ADMIN,
            json={"value_c": 6.0, "health": "HEALTHY"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/commands/clear-fault",
            headers={**ADMIN, "X-Confirm-Command": "CLEAR_FAULT"},
        ).status_code
        == 200
    )


def test_restart_never_reissues_an_interrupted_protection_command(
    tmp_path: Path,
) -> None:
    clock = FakeClock(datetime(2026, 9, 11, tzinfo=UTC))
    database = tmp_path / "state.db"
    first_app = create_app(database, "test-token", True, clock=clock)
    first_client = TestClient(first_app)
    clear_startup_fault(first_client)
    first_client.post(
        "/api/v1/simulation/temperature",
        headers=ADMIN,
        json={"value_c": 0.5, "health": "HEALTHY"},
    )

    assert first_app.state.relay_driver.commands == [RelayCommand.CLOSE_OR_PROTECT]

    restarted_app = create_app(database, "test-token", True, clock=clock)
    restarted = TestClient(restarted_app)
    assert restarted.get("/api/v1/status").json()["state"] == "STARTING"
    restarted_app.state.control_service.run_cycle()

    assert restarted.get("/api/v1/status").json()["state"] == "FAULT"
    assert restarted_app.state.relay_driver.commands == []


def test_sensor_fault_is_visible_and_audited(tmp_path: Path) -> None:
    app = create_app(tmp_path / "state.db", "test-token", True)
    client = TestClient(app)
    clear_startup_fault(client)

    decision = client.post(
        "/api/v1/simulation/temperature",
        headers=ADMIN,
        json={"health": "STALE"},
    )
    events = client.get("/api/v1/events", headers=ADMIN)

    assert decision.json()["state"] == "FAULT"
    assert client.get("/api/v1/status").json()["state"] == "FAULT"
    assert events.json()["items"][0]["payload"]["reason"] == "sensor_unhealthy"


def test_release_requires_eligible_forecast_and_never_conflicts_relays(
    tmp_path: Path,
) -> None:
    clock = FakeClock(datetime(2026, 9, 11, tzinfo=UTC))
    app = create_app(tmp_path / "state.db", "test-token", True, clock=clock)
    client = TestClient(app)
    clear_startup_fault(client)
    client.post(
        "/api/v1/simulation/temperature",
        headers=ADMIN,
        json={"value_c": 0.5, "health": "HEALTHY"},
    )
    client.post(
        "/api/v1/simulation/temperature",
        headers=ADMIN,
        json={"value_c": 0.5, "health": "HEALTHY"},
    )
    clock.advance(300)

    blocked = client.post(
        "/api/v1/simulation/temperature",
        headers=ADMIN,
        json={"value_c": 6.0, "health": "HEALTHY"},
    )
    released = client.post(
        "/api/v1/simulation/temperature",
        headers=ADMIN,
        json={
            "value_c": 6.0,
            "health": "HEALTHY",
            "daily_minima_c": [5.1] * 7,
        },
    )

    assert blocked.json()["state"] == "RELEASE_PENDING"
    assert released.json()["state"] == "MONITORING"
    assert app.state.relay_driver.commands == [
        RelayCommand.CLOSE_OR_PROTECT,
        RelayCommand.OPEN,
    ]
    assert len(set(app.state.relay_driver.commands)) == 2


def test_production_mode_does_not_expose_simulation_route(tmp_path: Path) -> None:
    app = create_app(tmp_path / "state.db", "test-token", False)

    assert TestClient(app).post("/api/v1/simulation/temperature", headers=ADMIN).status_code == 404


def test_logical_states_remain_explicit_in_the_api(tmp_path: Path) -> None:
    app = create_app(tmp_path / "state.db", "test-token", True)

    assert app.state.control_service.state is ControllerState.STARTING
