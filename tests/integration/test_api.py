from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from freeze_protect.api.app import create_app

ADMIN = {"X-Admin-Token": "test-token"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        database_path=tmp_path / "freeze-protect.db",
        admin_token="test-token",
        development_mode=True,
    )
    with TestClient(app) as test_client:
        yield test_client


def clear_startup_fault(client: TestClient) -> None:
    simulation = client.post(
        "/api/v1/simulation/temperature",
        headers=ADMIN,
        json={"value_c": 6.0, "health": "HEALTHY"},
    )
    assert simulation.status_code == 200
    clear = client.post(
        "/api/v1/commands/clear-fault",
        headers={**ADMIN, "X-Confirm-Command": "CLEAR_FAULT"},
    )
    assert clear.status_code == 200


def test_health_and_status_are_available_without_an_admin_token(
    client: TestClient,
) -> None:
    health = client.get("/health")
    status = client.get("/api/v1/status")

    assert health.status_code == 200
    assert health.json()["service"] == "ok"
    assert status.status_code == 200
    assert status.json()["state"] == "STARTING"


def test_manual_open_requires_token_and_exact_confirmation(client: TestClient) -> None:
    assert client.post("/api/v1/commands/open").status_code == 401
    assert (
        client.post(
            "/api/v1/commands/open",
            headers={**ADMIN, "X-Confirm-Command": "PROTECT"},
        ).status_code
        == 400
    )

    response = client.post(
        "/api/v1/commands/open",
        headers={**ADMIN, "X-Confirm-Command": "OPEN"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "fault_latched"


def test_simulation_requires_admin_and_is_disabled_in_production(tmp_path: Path) -> None:
    development_client = TestClient(
        create_app(tmp_path / "development.db", "test-token", True)
    )
    production_client = TestClient(
        create_app(tmp_path / "production.db", "test-token", False)
    )

    assert development_client.post("/api/v1/simulation/temperature").status_code == 401
    assert production_client.post("/api/v1/simulation/temperature", headers=ADMIN).status_code == 404


def test_simulation_drives_a_protection_decision_after_fault_clear(
    client: TestClient,
) -> None:
    clear_startup_fault(client)

    response = client.post(
        "/api/v1/simulation/temperature",
        headers=ADMIN,
        json={"value_c": 0.5, "health": "HEALTHY"},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "PROTECTING"
    assert client.get("/api/v1/status").json()["state"] == "PROTECTING"


def test_settings_require_admin_and_write_a_versioned_audit_event(
    client: TestClient,
) -> None:
    assert client.get("/api/v1/settings").status_code == 401
    assert client.get("/api/v1/settings", headers=ADMIN).json()["settings_version"] == 1

    update = client.put(
        "/api/v1/settings",
        headers=ADMIN,
        json={
            "protection_threshold_c": 1.5,
            "release_threshold_c": 5.0,
            "release_days": 7,
            "sensor_stale_after_s": 900,
            "minimum_protection_dwell_s": 300,
            "settings_version": 2,
        },
    )

    assert update.status_code == 200
    assert update.json()["settings_version"] == 2
    conflict = client.put(
        "/api/v1/settings",
        headers=ADMIN,
        json=update.json(),
    )
    assert conflict.status_code == 409
    events = client.get("/api/v1/events", headers=ADMIN)
    assert events.status_code == 200
    assert events.json()["items"][0]["event_type"] == "settings_changed"

def test_clear_fault_requires_exact_confirmation(client: TestClient) -> None:
    assert client.post("/api/v1/commands/clear-fault", headers=ADMIN).status_code == 400
    clear_startup_fault(client)
    assert client.get("/api/v1/status").json()["state"] == "MONITORING"
