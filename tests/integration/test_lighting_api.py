from conftest import Clock, Output
from fastapi.testclient import TestClient

from freeze_protect.lighting.api import create_app

DISPLAY = "d" * 32
SETTINGS = "s" * 32
CAMERA = "c" * 32


def bearer(token):
    return {"Authorization": "Bearer " + token}


def test_roles_strict_dtos_and_unconfigured_refusal(tmp_path):
    clock, output = Clock(), Output()
    app = create_app(
        tmp_path / "api.db",
        DISPLAY,
        SETTINGS,
        CAMERA,
        output,
        {"camera-1"},
        clock,
        provision_new_database=True,
    )
    with TestClient(app) as client:
        prefix = "/api/v1/lights"
        assert client.get(prefix + "/status").status_code == 401
        assert client.get(prefix + "/status", headers=bearer(CAMERA)).status_code == 403
        s = client.get(prefix + "/status", headers=bearer(DISPLAY)).json()
        assert s["capability"] == "independent_light_v1" and s["health"] == "OK"
        body = {
            "request_id": "action",
            "expected_revision": s["revision"],
            "action": "timed_on",
        }
        assert (
            client.post(
                prefix + "/actions", json=body, headers=bearer(CAMERA)
            ).status_code
            == 403
        )
        assert (
            client.post(
                prefix + "/actions",
                json={**body, "expected_revision": True},
                headers=bearer(DISPLAY),
            ).status_code
            == 422
        )
        assert (
            client.post(
                prefix + "/actions", json={**body, "pin": 26}, headers=bearer(DISPLAY)
            ).status_code
            == 422
        )
        on = client.post(prefix + "/actions", json=body, headers=bearer(DISPLAY))
        assert on.status_code == 200 and on.json()["gpio_on"] is True
        assert (
            client.post(prefix + "/actions", json=body, headers=bearer(DISPLAY)).json()
            == on.json()
        )
        assert (
            client.put(
                prefix + "/settings", json={}, headers=bearer(DISPLAY)
            ).status_code
            == 403
        )
        assert (
            client.get(
                prefix + "/history?limit=101", headers=bearer(SETTINGS)
            ).status_code
            == 422
        )
        assert (
            client.post(
                prefix + "/actions", content=b"x" * 4097, headers=bearer(DISPLAY)
            ).status_code
            == 413
        )
    app = create_app(
        tmp_path / "disabled.db",
        DISPLAY,
        DISPLAY,
        CAMERA,
        output,
        {"camera-1"},
        clock,
        provision_new_database=True,
    )
    with TestClient(app) as client:
        s = client.get(prefix + "/status", headers=bearer(DISPLAY)).json()
        assert s["health"] == "UNAVAILABLE"
        body["expected_revision"] = s["revision"]
        assert (
            client.post(
                prefix + "/actions", json=body, headers=bearer(DISPLAY)
            ).status_code
            == 503
        )


def test_lifespan_worker_expires_without_any_http_mutation(tmp_path):
    import time

    clock = Clock()
    output = Output()
    app = create_app(
        tmp_path / "worker.db",
        DISPLAY,
        SETTINGS,
        CAMERA,
        output,
        {"camera-1"},
        clock,
        provision_new_database=True,
    )
    with TestClient(app) as client:
        s = client.get("/api/v1/lights/status", headers=bearer(DISPLAY)).json()
        client.post(
            "/api/v1/lights/actions",
            headers=bearer(DISPLAY),
            json={
                "request_id": "hold",
                "expected_revision": s["revision"],
                "action": "timed_on",
            },
        )
        clock.advance(301)
        for _ in range(100):
            if not output.on:
                break
            time.sleep(0.01)
        assert not output.on


def test_camera_role_timestamp_replay_and_settings_contract(tmp_path):
    clock, output = Clock(), Output()
    app = create_app(
        tmp_path / "camera.db",
        DISPLAY,
        SETTINGS,
        CAMERA,
        output,
        {"camera-1"},
        clock,
        provision_new_database=True,
    )
    with TestClient(app) as client:
        prefix = "/api/v1/lights"
        clock.advance(0.01)
        payload = {
            "event_id": "evt",
            "source_id": "camera-1",
            "occurred_at": clock.stamp(),
        }
        assert (
            client.post(
                prefix + "/events/unifi", headers=bearer(DISPLAY), json=payload
            ).status_code
            == 403
        )
        result = client.post(
            prefix + "/events/unifi", headers=bearer(CAMERA), json=payload
        )
        assert result.json()["accepted"] is True
        assert (
            client.post(
                prefix + "/events/unifi", headers=bearer(CAMERA), json=payload
            ).json()["duplicate"]
            is True
        )
        for value in [True, "nan", "2026-10-13T01:00:00", "2026-10-13T01:00:00+01:00"]:
            invalid = {**payload, "event_id": "bad", "occurred_at": value}
            assert (
                client.post(
                    prefix + "/events/unifi", headers=bearer(CAMERA), json=invalid
                ).status_code
                == 422
            )
        settings = client.get(prefix + "/settings", headers=bearer(SETTINGS)).json()
        body = {
            "request_id": "save",
            "expected_revision": settings["revision"],
            "hold_seconds": 60,
            "manual_seconds": 120,
        }
        assert (
            client.put(
                prefix + "/settings", headers=bearer(SETTINGS), json=body
            ).status_code
            == 200
        )
        assert (
            client.put(
                prefix + "/settings", headers=bearer(SETTINGS), json=body
            ).json()["revision"]
            == 1
        )
        assert client.get(prefix + "/history", headers=bearer(SETTINGS)).json()["items"]
        assert (
            client.get(prefix + "/status", headers=bearer(SETTINGS)).status_code == 200
        )
        for seconds in [True, 61, 0, 7260, "60"]:
            invalid = {**body, "request_id": "invalid", "hold_seconds": seconds}
            assert (
                client.put(
                    prefix + "/settings", headers=bearer(SETTINGS), json=invalid
                ).status_code
                == 422
            )


def test_uncertain_action_retry_preserves_http_503(tmp_path, monkeypatch):
    import sqlite3

    clock, output = Clock(), Output()
    app = create_app(
        tmp_path / "uncertain-action.db",
        DISPLAY,
        SETTINGS,
        CAMERA,
        output,
        {"camera-1"},
        clock,
        provision_new_database=True,
    )
    with TestClient(app) as client:
        controller = app.state.light_controller
        real_save = controller.store.save
        writes = 0

        def final_commit_fails(*args, **kwargs):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise sqlite3.OperationalError("post-receipt disk failure")
            return real_save(*args, **kwargs)

        monkeypatch.setattr(controller.store, "save", final_commit_fails)
        body = {
            "request_id": "lost-action",
            "expected_revision": controller.status().revision,
            "action": "manual_on",
        }
        original = client.post(
            "/api/v1/lights/actions", headers=bearer(DISPLAY), json=body
        )
        assert original.status_code == 503 and not output.on
        begins = output.calls.count("begin")
        retry = client.post(
            "/api/v1/lights/actions", headers=bearer(DISPLAY), json=body
        )
        assert retry.status_code == 503
        assert retry.json() == original.json()
        assert output.calls.count("begin") == begins and not output.on


def test_uncertain_event_retry_preserves_http_503(tmp_path, monkeypatch):
    import sqlite3

    clock, output = Clock(), Output()
    app = create_app(
        tmp_path / "uncertain-event.db",
        DISPLAY,
        SETTINGS,
        CAMERA,
        output,
        {"camera-1"},
        clock,
        provision_new_database=True,
    )
    with TestClient(app) as client:
        controller = app.state.light_controller
        real_save = controller.store.save
        writes = 0

        def final_commit_fails(*args, **kwargs):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise sqlite3.OperationalError("post-receipt disk failure")
            return real_save(*args, **kwargs)

        monkeypatch.setattr(controller.store, "save", final_commit_fails)
        clock.advance(0.01)
        body = {
            "event_id": "lost-event",
            "source_id": "camera-1",
            "occurred_at": clock.stamp(),
        }
        original = client.post(
            "/api/v1/lights/events/unifi", headers=bearer(CAMERA), json=body
        )
        assert original.status_code == 503 and not output.on
        begins = output.calls.count("begin")
        retry = client.post(
            "/api/v1/lights/events/unifi", headers=bearer(CAMERA), json=body
        )
        assert retry.status_code == 503
        assert retry.json() == original.json()
        assert output.calls.count("begin") == begins and not output.on


def test_factory_default_does_not_recreate_lost_database(tmp_path):
    clock, output = Clock(), Output()
    path = tmp_path / "missing.db"
    app = create_app(path, DISPLAY, SETTINGS, CAMERA, output, {"camera-1"}, clock)
    with TestClient(app) as client:
        state = client.get("/api/v1/lights/status", headers=bearer(DISPLAY)).json()
        assert state["health"] == "UNAVAILABLE" and not path.exists()
        result = client.post(
            "/api/v1/lights/actions",
            headers=bearer(DISPLAY),
            json={
                "request_id": "missing-store",
                "expected_revision": state["revision"],
                "action": "manual_on",
            },
        )
        assert result.status_code == 503 and not output.on


def test_one_shot_provisioning_creates_database_without_starting_runtime(
    tmp_path, monkeypatch
):
    import pytest

    from freeze_protect.lighting.main import run
    from freeze_protect.lighting.store import LightStore

    path = tmp_path / "provisioned.db"
    monkeypatch.setenv("LIGHT_DB_PATH", str(path))
    monkeypatch.setenv("LIGHT_EXECUTOR_SOCKET", "/unused/socket")

    def forbidden(*args, **kwargs):
        raise AssertionError("provisioning must not start controller/executor/server")

    monkeypatch.setattr("freeze_protect.lighting.main.create_app", forbidden)
    monkeypatch.setattr("freeze_protect.lighting.main.ExecutorClient", forbidden)
    monkeypatch.setattr("freeze_protect.lighting.main.uvicorn.run", forbidden)
    run(["--provision-new-db"])
    store = LightStore(path)
    try:
        assert store.load_revision() == 0 and store.load().revision == 0
    finally:
        store.close()
    with pytest.raises(FileExistsError):
        run(["--provision-new-db"])
