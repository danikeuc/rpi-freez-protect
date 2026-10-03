"""Exact HTTP contracts; real app/SQLite with fake transport and paired driver."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from freeze_protect.api.app import create_app
from freeze_protect.application.weather_worker import WeatherResult
from freeze_protect.domain.models import ActuatorCommand, ControlMode
from freeze_protect.domain.weather import WeatherWindow

DISPLAY = {"X-Display-Token": "display"}
WEATHER = {"X-Weather-Settings-Token": "weather"}
ADMIN = {"X-Admin-Token": "admin"}
SETTINGS = {
    "revision": 0,
    "enabled": False,
    "latitude": None,
    "longitude": None,
    "timezone": "Europe/Ljubljana",
}


class Worker:
    def __init__(self, fetch, wake, monotonic_clock):
        self.requests = []
        self.result = None
        self.stopped = False
        self.clock = monotonic_clock

    def submit(self, request):
        self.requests.append(request)
        return True

    def poll(self):
        result, self.result = self.result, None
        return result

    def cancel(self):
        self.result = None

    def stop(self):
        self.stopped = True

    def warm(self):
        request = self.requests[-1]
        today = request.requested_at.astimezone(
            ZoneInfo(request.settings.timezone)
        ).date()
        self.result = WeatherResult(
            request,
            WeatherWindow(
                tuple(today + timedelta(days=i) for i in range(5)),
                (5.0,) * 5,
                request.requested_at,
                46.5,
                15.5,
                request.settings.timezone,
                request.settings.revision,
                request.generation,
            ),
            None,
            self.clock(),
        )


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr("freeze_protect.api.app.WeatherWorker", Worker)
    elapsed = [100.0]
    application = create_app(
        tmp_path / "api.db",
        "admin",
        "display",
        True,
        weather_settings_token="weather",
        control_mode=ControlMode.WEATHER_ASSISTED,
        run_background=False,
        clock=lambda: (
            datetime(2026, 10, 3, 10, tzinfo=UTC) + timedelta(seconds=elapsed[0] - 100)
        ),
        monotonic_clock=lambda: elapsed[0],
    )
    application.state.test_elapsed = elapsed
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def action(client, duration=180):
    status = client.get("/api/v1/display/status", headers=DISPLAY).json()
    payload = {
        "request_id": str(uuid4()),
        "expected_control_revision": status["control_revision"],
        "action_nonce": status["action_nonce"],
    }
    if duration is not None:
        payload["duration_seconds"] = duration
    return payload


def test_settings_exact_schema_and_distinct_scoped_credentials(client):
    assert (
        client.get("/api/v1/display/weather-settings", headers=WEATHER).json()
        == SETTINGS
    )
    update = {
        "expected_revision": 0,
        "enabled": True,
        "latitude": 46.5,
        "longitude": 15.5,
        "timezone": "Europe/Ljubljana",
    }
    for headers in ({}, DISPLAY, ADMIN, {"X-Weather-Settings-Token": "display"}):
        assert (
            client.put(
                "/api/v1/display/weather-settings", headers=headers, json=update
            ).status_code
            == 401
        )
    response = client.put(
        "/api/v1/display/weather-settings", headers=WEATHER, json=update
    )
    assert response.status_code == 200
    assert response.json() == {
        "revision": 1,
        **{k: v for k, v in update.items() if k != "expected_revision"},
    }
    assert (
        client.put(
            "/api/v1/display/weather-settings", headers=WEATHER, json=update
        ).status_code
        == 409
    )
    assert client.get("/api/v1/settings", headers=WEATHER).status_code == 401
    assert (
        client.post(
            "/api/v1/commands/clear-fault",
            headers={**WEATHER, "X-Confirm-Command": "CLEAR_FAULT"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/display/actions/start", headers=WEATHER, json=action(client)
        ).status_code
        == 401
    )


def test_status_exact_additions_and_manual_start_stop_contract(client):
    status = client.get("/api/v1/display/status", headers=DISPLAY).json()
    assert status["weather_assistance_version"] == 1
    assert status["operation"] == "MANUAL_IDLE"
    assert status["mode"] == "weather_assisted"
    assert status["state"] == "MANUAL_DRAIN"
    assert status["weather"] == {
        "enabled": False,
        "available": False,
        "eligible": False,
        "reason": "disabled",
        "dates": [],
        "minima_c": [],
        "last_successful_check": None,
    }
    assert isinstance(status["action_nonce"], str)
    request = action(client)
    started = client.post(
        "/api/v1/display/actions/start", headers=DISPLAY, json=request
    )
    assert started.status_code == 200
    body = started.json()
    assert set(body) == {"request_id", "accepted", "control_revision", "status"}
    assert body["request_id"] == request["request_id"] and body["accepted"] is True
    assert body["status"]["operation"] == "MANUAL_ACTIVE"
    assert body["status"]["remaining_seconds"] == 180
    assert body["control_revision"] == body["status"]["control_revision"]
    stopped = client.post(
        "/api/v1/display/actions/stop", headers=DISPLAY, json=action(client, None)
    )
    assert stopped.status_code == 200
    assert stopped.json()["status"]["operation"] == "USER_OFF"
    assert stopped.json()["status"]["command"] == "DRAIN"
    assert (
        client.post(
            "/api/v1/display/actions/timed-shower",
            headers=DISPLAY,
            json={"duration_seconds": 180},
        ).status_code
        == 409
    )
    assert (
        client.post("/api/v1/display/actions/drain", headers=DISPLAY).status_code == 200
    )


def test_warm_equality_at_five_is_auto_without_a_countdown(client):
    saved = client.put(
        "/api/v1/display/weather-settings",
        headers=WEATHER,
        json={
            "expected_revision": 0,
            "enabled": True,
            "latitude": 46.5,
            "longitude": 15.5,
            "timezone": "Europe/Ljubljana",
        },
    )
    assert saved.status_code == 200
    client.app.state.weather_worker.warm()
    client.app.state.control_service.run_cycle()
    status = client.get("/api/v1/display/status", headers=DISPLAY).json()
    assert status["operation"] == "AUTO_SUPPLY"
    assert status["state"] == "AUTO_SUPPLY"
    assert status["command"] == "SUPPLY"
    assert status["remaining_seconds"] == 0
    assert status["weather"]["eligible"] is True
    assert status["weather"]["minima_c"] == [5.0] * 5
    assert len(status["weather"]["dates"]) == 5
    before = list(client.app.state.relay_driver.commands)
    client.get("/api/v1/display/status", headers=DISPLAY)
    assert client.app.state.relay_driver.commands == before


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"[]",
        b'{"request_id":"not-uuid","expected_control_revision":1,"action_nonce":"x","duration_seconds":60}',
        b'{"request_id":"00000000-0000-0000-0000-000000000000","expected_control_revision":true,"action_nonce":"x","duration_seconds":60}',
        b'{"request_id":"00000000-0000-0000-0000-000000000000","expected_control_revision":1,"action_nonce":"x","duration_seconds":true}',
    ],
)
def test_invalid_action_json_never_actuates(client, body):
    before = list(client.app.state.relay_driver.commands)
    response = client.post(
        "/api/v1/display/actions/start", headers=DISPLAY, content=body
    )
    assert response.status_code == 422
    assert client.app.state.relay_driver.commands == before


@pytest.mark.parametrize(
    "change",
    [
        {"duration_seconds": True},
        {"duration_seconds": 60.0},
        {"duration_seconds": "60"},
        {"duration_seconds": 59},
        {"duration_seconds": 61},
        {"duration_seconds": 601},
        {"extra": 1},
        {"expected_control_revision": -1},
        {"expected_control_revision": 9007199254740992},
    ],
)
def test_action_fields_are_strict(client, change):
    request = {**action(client), **change}
    assert (
        client.post(
            "/api/v1/display/actions/start", headers=DISPLAY, json=request
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "body",
    [
        b'{"expected_revision":0,"enabled":true,"latitude":NaN,"longitude":15,"timezone":"Europe/Ljubljana"}',
        b'{"expected_revision":0,"enabled":true,"latitude":Infinity,"longitude":15,"timezone":"Europe/Ljubljana"}',
        b'{"expected_revision":0,"enabled":true,"latitude":46,"longitude":15,"timezone":"Europe/Ljubljana","enabled":false}',
    ],
)
def test_settings_reject_nonfinite_and_duplicate_fields(client, body):
    assert (
        client.put(
            "/api/v1/display/weather-settings", headers=WEATHER, content=body
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_revision", True),
        ("enabled", 1),
        ("latitude", True),
        ("timezone", "Unknown/Bad"),
        ("latitude", 91),
        ("longitude", None),
        ("extra", 1),
    ],
)
def test_settings_domain_and_strict_input_validation(client, field, value):
    request = {
        "expected_revision": 0,
        "enabled": True,
        "latitude": 46.5,
        "longitude": 15.5,
        "timezone": "Europe/Ljubljana",
        field: value,
    }
    assert (
        client.put(
            "/api/v1/display/weather-settings", headers=WEATHER, json=request
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "route,headers",
    [
        ("/api/v1/display/actions/start", DISPLAY),
        ("/api/v1/display/actions/stop", DISPLAY),
        ("/api/v1/display/weather-settings", WEATHER),
    ],
)
def test_body_limit_is_413(client, route, headers):
    assert (
        client.request(
            "PUT" if route.endswith("weather-settings") else "POST",
            route,
            headers=headers,
            content=b" " * 4097,
        ).status_code
        == 413
    )


def test_missing_start_duration_and_stop_extra_duration_are_invalid(client):
    assert (
        client.post(
            "/api/v1/display/actions/start", headers=DISPLAY, json=action(client, None)
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/display/actions/stop", headers=DISPLAY, json=action(client)
        ).status_code
        == 422
    )


def test_replay_keeps_recorded_revision_and_current_user_off_without_io(client):
    request = action(client)
    accepted = client.post(
        "/api/v1/display/actions/start", headers=DISPLAY, json=request
    ).json()
    client.post(
        "/api/v1/display/actions/stop", headers=DISPLAY, json=action(client, None)
    )
    before = list(client.app.state.relay_driver.commands)
    replay = client.post("/api/v1/display/actions/start", headers=DISPLAY, json=request)
    assert replay.status_code == 200
    assert replay.json()["control_revision"] == accepted["control_revision"]
    assert replay.json()["status"]["operation"] == "USER_OFF"
    assert client.app.state.relay_driver.commands == before


def test_corrupt_weather_identity_still_constructs_startup_drain_and_fault(app):
    database = app.state.weather_store._database_path
    database.with_name(database.name + ".weather-identity").write_text("corrupt")
    damaged = create_app(
        database,
        "admin",
        "display",
        True,
        weather_settings_token="weather",
        control_mode=ControlMode.WEATHER_ASSISTED,
        run_background=False,
    )
    with TestClient(damaged) as client:
        status = client.get("/api/v1/display/status", headers=DISPLAY)
        assert status.status_code == 200
        assert status.json()["operation"] == "FAULT"
        assert status.json()["action_nonce"] is None
        assert status.json()["control_revision"] is None
        assert damaged.state.relay_driver.commands and all(
            c is ActuatorCommand.DRAIN for c in damaged.state.relay_driver.commands
        )
        assert (
            client.get("/api/v1/display/weather-settings", headers=WEATHER).status_code
            == 503
        )
        assert (
            client.post("/api/v1/display/actions/drain", headers=DISPLAY).status_code
            == 409
        )
    assert (
        database.with_name(database.name + ".weather-identity").read_text() == "corrupt"
    )


def test_worker_is_lifespan_owned_and_shutdown_drains_without_user_off(app):
    with TestClient(app):
        worker = app.state.weather_worker
        assert worker.stopped is False
    assert worker.stopped is True
    assert app.state.weather_store.load().user_off is False


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/display/weather-settings", "POST"),
        ("/api/v1/display/actions/start", "GET"),
        ("/api/v1/display/actions/stop", "PUT"),
    ],
)
def test_new_routes_reject_wrong_http_methods(client, path, method):
    assert client.request(method, path, headers=DISPLAY).status_code == 405


def test_new_routes_do_not_expose_a_general_admin_or_forecast_write(client):
    assert (
        client.put(
            "/api/v1/display/weather-settings/extra", headers=WEATHER, json={}
        ).status_code
        == 404
    )
    assert (
        client.put(
            "/api/v1/display/weather-settings",
            headers=WEATHER,
            json={
                "expected_revision": 0,
                "enabled": True,
                "latitude": 46.5,
                "longitude": 15.5,
                "timezone": "Europe/Ljubljana",
                "dates": ["2026-10-03"] * 6,
            },
        ).status_code
        == 422
    )


def test_nonascii_bad_weather_credential_is_401_without_server_exception(client):
    assert (
        client.get(
            "/api/v1/display/weather-settings",
            headers=[(b"X-Weather-Settings-Token", b"\xff")],
        ).status_code
        == 401
    )


def test_weather_credential_value_is_rejected_under_other_auth_headers(client):
    assert (
        client.get("/api/v1/settings", headers={"X-Admin-Token": "weather"}).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/display/status", headers={"X-Display-Token": "weather"}
        ).status_code
        == 401
    )


def test_reused_display_or_admin_token_cannot_become_weather_credential(tmp_path):
    for token in ("display", "admin"):
        app = create_app(
            tmp_path / (token + ".db"),
            "admin",
            "display",
            True,
            weather_settings_token=token,
            run_background=False,
        )
        with TestClient(app) as client:
            assert (
                client.get(
                    "/api/v1/display/weather-settings",
                    headers={"X-Weather-Settings-Token": token},
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/v1/display/actions/drain", headers=DISPLAY
                ).status_code
                == 200
            )
