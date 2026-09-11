# RPi Freeze Protect M0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable, fully simulated and safety-first freeze-protection control service that is ready for Raspberry Pi hardware adapters but cannot drive GPIO yet.

**Architecture:** A pure Python domain policy evaluates timestamped sensor and forecast data into a logical state and relay command. Application services invoke adapter interfaces and persist an append-only audit trail. FastAPI exposes the local status, configuration, manual-command and development-simulation endpoints; GPIO, weather and ESP32 implementations stay outside M0.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Uvicorn, SQLite from the standard library, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-11-freeze-protect-design.md`

## Global Constraints

- The Pi is the sole control hub; an ESP32 is only a future I/O peripheral.
- Python domain and application code must not import FastAPI, GPIO, MQTT or SQLite.
- M0 contains simulated adapters only: it must not include `gpiozero`, `RPi.GPIO`, relay wiring or production actuator control.
- Missing, stale or invalid sensor data, configuration validation failures and driver errors must result in an explicit fault/audit event, never a silent fallback.
- `OPEN` and `CLOSE_OR_PROTECT` are logical, mutually exclusive commands. Relay channel/polarity/pulse configuration is deferred to M1.
- A valid forecast is required for automatic release/open; default policy requires each of the next seven daily minima to exceed +5 °C.
- Runtime configuration values are validated and versioned. Do not hard-code commissioning thresholds or physical timings in control logic.
- Bind the web service to loopback by default. Administrative settings, simulation input and manual commands require a non-empty `FREEZE_PROTECT_ADMIN_TOKEN` and a matching confirmation header where stated.
- Every automated decision, manual command, fault and configuration change is written to the append-only audit store.
- Work test-first. Each completed task must pass its focused test command and be committed separately.

---

## File structure

```text
pyproject.toml                              # package, dependencies, test/lint/type-check configuration
README.md                                   # M0 local run, test and safety instructions
src/freeze_protect/__init__.py              # package version
src/freeze_protect/domain/models.py         # immutable values, enums and validated safety settings
src/freeze_protect/domain/policy.py         # pure state/command decision function
src/freeze_protect/application/ports.py     # protocols shared by application and adapters
src/freeze_protect/application/service.py   # control cycle and manual-command orchestration
src/freeze_protect/adapters/simulation.py   # deterministic in-memory sensor, forecast and relay adapters
src/freeze_protect/persistence/sqlite.py    # SQLite settings and append-only audit repositories
src/freeze_protect/api/auth.py              # constant-time local administrator guard
src/freeze_protect/api/app.py               # FastAPI factory, routes and dependency composition
src/freeze_protect/main.py                  # Uvicorn entry point
tests/unit/test_models.py                   # settings and value-object boundaries
tests/unit/test_policy.py                   # exhaustive policy transitions
tests/unit/test_service.py                  # command deduplication and auditing behaviour
tests/integration/test_sqlite.py            # persistence/restart behaviour
tests/integration/test_api.py               # authenticated API and simulator contract
```

## Task 1: Bootstrap a reproducible Python project

**Files:**
- Create: `pyproject.toml`
- Create: `src/freeze_protect/__init__.py`
- Create: `tests/unit/test_smoke.py`
- Create: `README.md`

**Interfaces:**
- Produces: installable package `freeze_protect` and the `pytest`, `ruff`, and `mypy` commands used by all later tasks.

- [ ] **Step 1: Write the failing package smoke test**

```python
from freeze_protect import __version__


def test_package_exposes_a_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run the test to verify the package is absent**

Run: `python -m pytest tests/unit/test_smoke.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'freeze_protect'`.

- [ ] **Step 3: Add minimal package and tool configuration**

Create `pyproject.toml` with a setuptools `src` layout, `requires-python = ">=3.12"`, runtime dependencies `fastapi>=0.115,<1`, `uvicorn[standard]>=0.30,<1`, and `pydantic>=2.9,<3`; add dev dependencies `pytest>=8.3,<9`, `httpx>=0.27,<1`, `ruff>=0.6,<1`, `mypy>=1.11,<2`, and `build>=1.2,<2`. Configure pytest with `testpaths = ["tests"]`, Ruff for target `py312`, and mypy with `strict = true`.

Create `src/freeze_protect/__init__.py`:

```python
__version__ = "0.1.0"
```

Create a short `README.md` stating that M0 is simulation-only and must not be wired to a relay.

- [ ] **Step 4: Install and verify the bootstrap**

Run: `python -m pip install -e '.[dev]' && python -m pytest tests/unit/test_smoke.py -v && python -m ruff check . && python -m mypy src`

Expected: all commands PASS.

- [ ] **Step 5: Commit the bootstrap**

```bash
git add pyproject.toml README.md src/freeze_protect/__init__.py tests/unit/test_smoke.py
git commit -m "chore: bootstrap freeze protect service"
```

## Task 2: Define validated domain values and settings

**Files:**
- Create: `src/freeze_protect/domain/models.py`
- Create: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `ControllerState`, `RelayCommand`, `SensorHealth`, `TemperatureReading`, `ForecastSnapshot`, `SafetySettings`, `Decision`, and `AuditEvent`.
- Consumed by: `domain.policy.evaluate`, application ports, persistence and API schemas.

- [ ] **Step 1: Write failing value-object tests**

```python
from datetime import UTC, datetime

import pytest

from freeze_protect.domain.models import ForecastSnapshot, SafetySettings


def test_release_requires_exactly_configured_forecast_days() -> None:
    snapshot = ForecastSnapshot(
        daily_minima_c=(5.1,) * 7,
        fetched_at=datetime.now(UTC),
    )
    assert snapshot.has_minima_above(5.0, days=7) is True


def test_settings_reject_non_positive_release_days() -> None:
    with pytest.raises(ValueError, match="release_days"):
        SafetySettings(release_days=0)
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python -m pytest tests/unit/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'freeze_protect.domain.models'`.

- [ ] **Step 3: Implement immutable domain types**

Use `@dataclass(frozen=True, slots=True)` and `Enum` for the domain types. Define `Decision(state: ControllerState, command: RelayCommand, reason: str)`. Define `AuditEvent(id: str, occurred_at: datetime, event_type: str, payload: Mapping[str, object])`; callers generate UUID4 strings and UTC timestamps. Implement `SafetySettings` with these constructor fields and defaults for simulator use only:

```python
protection_threshold_c: float = 1.0
release_threshold_c: float = 5.0
release_days: int = 7
sensor_stale_after_s: int = 900
minimum_protection_dwell_s: int = 300
settings_version: int = 1
```

Validate that `release_days`, stale timeout and dwell are positive; `release_threshold_c > protection_threshold_c`; and version is positive. `ForecastSnapshot.has_minima_above(threshold_c: float, days: int) -> bool` must return `False` if fewer than `days` values are available, and otherwise use strict `>` for every selected minimum. `TemperatureReading` must represent health separately from its optional numeric value, so stale/invalid readings need not invent a temperature.

- [ ] **Step 4: Verify domain validation and static types**

Run: `python -m pytest tests/unit/test_models.py -v && python -m mypy src/freeze_protect/domain`

Expected: PASS.

- [ ] **Step 5: Commit the domain model**

```bash
git add src/freeze_protect/domain/models.py tests/unit/test_models.py
git commit -m "feat: define validated control domain models"
```

## Task 3: Implement the pure safety policy

**Files:**
- Create: `src/freeze_protect/domain/policy.py`
- Create: `tests/unit/test_policy.py`

**Interfaces:**
- Consumes: `TemperatureReading`, `ForecastSnapshot | None`, `SafetySettings`, and prior `ControllerState`.
- Produces: `evaluate(previous_state, reading, forecast, settings) -> Decision`.

- [ ] **Step 1: Write failing transition tests**

```python
def test_low_healthy_temperature_enters_protecting() -> None:
    decision = evaluate(
        previous_state=ControllerState.MONITORING,
        reading=healthy_reading(0.5),
        forecast=None,
        settings=SETTINGS,
    )
    assert decision.state is ControllerState.PROTECTING
    assert decision.command is RelayCommand.CLOSE_OR_PROTECT


def test_release_is_blocked_when_forecast_has_a_day_at_threshold() -> None:
    decision = evaluate(
        previous_state=ControllerState.PROTECTING,
        reading=healthy_reading(6.0),
        forecast=forecast((5.1,) * 6 + (5.0,)),
        settings=SETTINGS,
    )
    assert decision.state is ControllerState.RELEASE_PENDING
    assert decision.command is RelayCommand.STOP
```

Add tests proving that unhealthy/stale/invalid input returns `FAULT` + `STOP`; `STARTING` and `MANUAL_LOCK` return `FAULT`/`STOP` and `MANUAL_LOCK`/`STOP` respectively; `FAULT` remains faulted until a later manual-clear use case; and a healthy protected system returns `MONITORING` + `OPEN` only when all seven forecast minima strictly exceed the configured threshold.

- [ ] **Step 2: Run the policy suite to verify failure**

Run: `python -m pytest tests/unit/test_policy.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'freeze_protect.domain.policy'`.

- [ ] **Step 3: Implement one pure decision function**

Implement only `evaluate(...)`. It must not read a clock, mutate state, touch an adapter, or persist data. Return `Decision` values with concise machine-readable reasons: `sensor_unhealthy`, `below_protection_threshold`, `forecast_not_eligible`, `release_eligible`, `manual_lock`, or `fault_latched`.

The evaluation order is mandatory:

```text
manual lock -> MANUAL_LOCK / STOP
starting or latched fault -> FAULT / STOP
unhealthy reading -> FAULT / STOP
temperature <= protection threshold -> PROTECTING / CLOSE_OR_PROTECT
previous protecting/release pending + non-eligible forecast -> RELEASE_PENDING / STOP
previous protecting/release pending + eligible forecast -> MONITORING / OPEN
otherwise -> MONITORING / STOP
```

- [ ] **Step 4: Verify every transition**

Run: `python -m pytest tests/unit/test_policy.py -v && python -m ruff check src/freeze_protect/domain tests/unit/test_policy.py`

Expected: PASS.

- [ ] **Step 5: Commit the policy**

```bash
git add src/freeze_protect/domain/policy.py tests/unit/test_policy.py
git commit -m "feat: add pure freeze protection policy"
```

## Task 4: Orchestrate simulated control cycles and audit events

**Files:**
- Create: `src/freeze_protect/application/ports.py`
- Create: `src/freeze_protect/application/service.py`
- Create: `src/freeze_protect/adapters/simulation.py`
- Create: `tests/unit/test_service.py`

**Interfaces:**
- Consumes: `evaluate(...)` from Task 3.
- Produces: `ControlService.run_cycle() -> Decision`, `ControlService.manual_command(command: RelayCommand) -> Decision`, `ControlService.clear_fault() -> Decision`, and protocols `TemperatureSource`, `ForecastSource`, `RelayDriver`, `EventStore`.

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_relay_receives_protection_once_when_state_changes() -> None:
    relays = SimulatedRelayDriver()
    service = build_service(reading_c=0.5, relay_driver=relays)

    service.run_cycle()
    service.run_cycle()

    assert relays.commands == [RelayCommand.CLOSE_OR_PROTECT]


def test_each_decision_is_appended_to_audit_log() -> None:
    events = InMemoryEventStore()
    service = build_service(reading_c=0.5, event_store=events)

    service.run_cycle()

    assert [event.event_type for event in events.events] == ["automatic_decision"]
```

Also test that a manual `STOP` enters `MANUAL_LOCK` and appends `manual_command`; a healthy, unlocked manual command appends `manual_command`; and relay-driver exceptions create a `FAULT` decision and a `relay_driver_error` event, without retrying or emitting the opposite command.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/unit/test_service.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'freeze_protect.application'`.

- [ ] **Step 3: Implement ports, in-memory adapters and service**

Define protocols with these exact members:

```python
class TemperatureSource(Protocol):
    def read(self) -> TemperatureReading: ...

class ForecastSource(Protocol):
    def read(self) -> ForecastSnapshot | None: ...

class RelayDriver(Protocol):
    def command(self, command: RelayCommand) -> None: ...

class EventStore(Protocol):
    def append(self, event: AuditEvent) -> None: ...
```

`ControlService` starts in `STARTING`, which the policy converts to latched `FAULT` without a relay command on its first cycle. `clear_fault()` requires a healthy current sensor reading and moves to `MONITORING` with `STOP`; it appends a `fault_cleared` event. A manual `STOP` moves to `MANUAL_LOCK`; a manual `OPEN` or `CLOSE_OR_PROTECT` is refused while faulted, locked or sensor-unhealthy, otherwise it is emitted once and recorded as `manual_command`. The service keeps only logical state and the last emitted non-`STOP` command. It calls `RelayDriver.command` only when a new non-stop command represents a state transition. It appends an `automatic_decision` event for every cycle and a `relay_driver_error` event if the driver raises. `SimulatedTemperatureSource`, `SimulatedForecastSource`, `SimulatedRelayDriver` and `InMemoryEventStore` must be deterministic, have no FastAPI dependency, and expose simple test inspection fields.

- [ ] **Step 4: Run focused service tests**

Run: `python -m pytest tests/unit/test_service.py -v && python -m mypy src/freeze_protect/application src/freeze_protect/adapters`

Expected: PASS.

- [ ] **Step 5: Commit the simulation service**

```bash
git add src/freeze_protect/application src/freeze_protect/adapters tests/unit/test_service.py
git commit -m "feat: add simulated control service and audit events"
```

## Task 5: Persist settings and audit events in SQLite

**Files:**
- Create: `src/freeze_protect/persistence/sqlite.py`
- Create: `tests/integration/test_sqlite.py`
- Modify: `src/freeze_protect/application/ports.py`

**Interfaces:**
- Consumes: `SafetySettings` and `AuditEvent` from Task 2.
- Produces: `SQLiteSettingsStore.load() -> SafetySettings`, `SQLiteSettingsStore.save(settings: SafetySettings) -> SafetySettings`, `SQLiteEventStore.append(event: AuditEvent) -> None`, and `SQLiteEventStore.list(limit: int, offset: int) -> list[AuditEvent]`.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_settings_survive_a_new_store_instance(tmp_path: Path) -> None:
    database = tmp_path / "freeze-protect.db"
    first = SQLiteSettingsStore(database)
    saved = first.save(SafetySettings(protection_threshold_c=1.5, settings_version=2))

    second = SQLiteSettingsStore(database)

    assert second.load() == saved


def test_audit_events_are_append_only_in_time_order(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "freeze-protect.db")
    store.append(event("automatic_decision"))
    store.append(event("manual_command"))

    assert [item.event_type for item in store.list(limit=10, offset=0)] == ["manual_command", "automatic_decision"]
```

- [ ] **Step 2: Run integration tests to verify failure**

Run: `python -m pytest tests/integration/test_sqlite.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'freeze_protect.persistence'`.

- [ ] **Step 3: Implement schema initialization and repositories**

Use `sqlite3` with parameterized statements and initialize these tables transactionally:

```sql
CREATE TABLE IF NOT EXISTS settings (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  version INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_occurred_at
  ON audit_events (occurred_at DESC, id DESC);
```

`load` returns the simulator-default `SafetySettings()` when no settings row exists; it never writes that default merely by reading. `save` must reject any version not exactly one greater than the stored version, yielding a version-conflict error. Serialize only public dataclass fields to JSON. `list` must order by `occurred_at DESC, id DESC`, use bounded integer parameters, and never update/delete existing events.

- [ ] **Step 4: Verify restart persistence and full existing suite**

Run: `python -m pytest tests/integration/test_sqlite.py -v && python -m pytest -v`

Expected: PASS.

- [ ] **Step 5: Commit persistence**

```bash
git add src/freeze_protect/persistence src/freeze_protect/application/ports.py tests/integration/test_sqlite.py
git commit -m "feat: persist settings and audit events locally"
```

## Task 6: Expose a loopback-only, authenticated FastAPI service

**Files:**
- Create: `src/freeze_protect/api/auth.py`
- Create: `src/freeze_protect/api/app.py`
- Create: `src/freeze_protect/main.py`
- Create: `tests/integration/test_api.py`
- Modify: `src/freeze_protect/application/service.py`

**Interfaces:**
- Consumes: `ControlService`, SQLite stores and simulation adapters.
- Produces: `create_app(database_path: Path, admin_token: str | None, development_mode: bool) -> FastAPI` and an ASGI application named `app` in `main.py`.

- [ ] **Step 1: Write failing API contract tests**

```python
def test_status_is_available_without_admin_token(client: TestClient) -> None:
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert response.json()["state"] == "STARTING"


def test_manual_open_requires_token_and_exact_confirmation(client: TestClient) -> None:
    assert client.post("/api/v1/commands/open").status_code == 401
    response = client.post(
        "/api/v1/commands/open",
        headers={"X-Admin-Token": "test-token", "X-Confirm-Command": "OPEN"},
    )
    assert response.status_code in {200, 409}
```

Add tests for `/health`, settings validation/version conflicts, `/api/v1/events` pagination, `/api/v1/commands/clear-fault`, and `/api/v1/simulation/temperature`. The simulation route must return `404` when `development_mode=False` and require the admin token when enabled. A newly created app must report `STARTING` before its first control cycle and `FAULT` after that cycle unless an authenticated `clear-fault` operation succeeds.

- [ ] **Step 2: Run API tests to verify failure**

Run: `python -m pytest tests/integration/test_api.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'freeze_protect.api'`.

- [ ] **Step 3: Implement app factory and security guard**

`require_admin` must use `secrets.compare_digest`, return `401` if the configured token is empty/missing or the request token does not match, and never echo a supplied token. Register the exact endpoints from the specification plus `POST /api/v1/commands/clear-fault`. Parse manual relay commands into `RelayCommand`; require `X-Confirm-Command` to exactly equal the command's enum name, and require `X-Confirm-Command: CLEAR_FAULT` for the clear-fault route. Report a safety refusal as HTTP `409` with `{ "detail": decision.reason }`.

The development simulation route updates the simulated source and immediately invokes exactly one `ControlService.run_cycle()`; production mode has no code path to inject a reading. Store the composed `ControlService` in `app.state.control_service` solely for lifecycle/acceptance tests; routes use dependencies, not that test hook. `main.py` reads `FREEZE_PROTECT_DB_PATH` (default `./data/freeze-protect.db`), `FREEZE_PROTECT_ADMIN_TOKEN`, and `FREEZE_PROTECT_DEVELOPMENT_MODE` (`false` by default); pass `host="127.0.0.1"` to Uvicorn in the documented run command. Do not add CORS wildcards, anonymous write endpoints, or a network binding option in M0.

- [ ] **Step 4: Verify API and security contract**

Run: `python -m pytest tests/integration/test_api.py -v && python -m ruff check . && python -m mypy src`

Expected: PASS.

- [ ] **Step 5: Commit the API**

```bash
git add src/freeze_protect/api src/freeze_protect/main.py src/freeze_protect/application/service.py tests/integration/test_api.py
git commit -m "feat: expose secured local control API"
```

## Task 7: Demonstrate M0 acceptance and operator workflow

**Files:**
- Modify: `README.md`
- Create: `tests/integration/test_m0_acceptance.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: the fully composed application from Task 6.
- Produces: a documented safe local demonstration and a single acceptance test suite.

- [ ] **Step 1: Write failing acceptance scenarios**

```python
def test_restart_never_reissues_an_interrupted_protection_command(tmp_path: Path) -> None:
    app = create_app(tmp_path / "state.db", admin_token="test-token", development_mode=True)
    client = TestClient(app)
    client.post("/api/v1/simulation/temperature", headers=ADMIN, json={"value_c": 6.0})
    client.post("/api/v1/commands/clear-fault", headers={**ADMIN, "X-Confirm-Command": "CLEAR_FAULT"})
    client.post("/api/v1/simulation/temperature", headers=ADMIN, json={"value_c": 0.5})
    assert client.get("/api/v1/status").json()["state"] == "PROTECTING"

    restarted_app = create_app(tmp_path / "state.db", admin_token="test-token", development_mode=True)
    restarted = TestClient(restarted_app)
    assert restarted.get("/api/v1/status").json()["state"] == "STARTING"
    restarted_app.state.control_service.run_cycle()
    assert restarted.get("/api/v1/status").json()["state"] == "FAULT"
```

Add scenarios for stale/invalid inputs, forecast-gated release, no duplicate conflicting relay emission, a queryable event trail, and disabled simulator endpoint in non-development mode.

- [ ] **Step 2: Run acceptance tests to verify failure**

Run: `python -m pytest tests/integration/test_m0_acceptance.py -v`

Expected: FAIL until any missing lifecycle or safety behaviour is corrected.

- [ ] **Step 3: Make the smallest corrections required by the acceptance suite**

Keep changes within the existing boundaries. In `README.md`, document installation, the loopback command, the required token, simulated API example, test/lint/type-check commands, backup location, and a prominent warning: **do not connect M0 to physical relays or an actuator**.

- [ ] **Step 4: Run the complete verification set**

Run: `python -m pytest -v && python -m ruff check . && python -m mypy src && python -m build`

Expected: every command PASS and the built wheel contains the `freeze_protect` package.

- [ ] **Step 5: Commit the accepted M0 baseline**

```bash
git add README.md pyproject.toml tests/integration/test_m0_acceptance.py src tests
git commit -m "test: verify m0 safety acceptance scenarios"
```

## Plan self-review

| Spec requirement | Plan coverage |
| --- | --- |
| Local, deterministic Pi control authority | Tasks 2–4 |
| No physical actuation in M0 | Global constraints; Tasks 1, 4 and 7 |
| Sensor/forecast safety policy and +5 °C / seven-day default | Tasks 2–3 |
| Mutually exclusive logical relay commands and time-independent safety decisions | Tasks 3–4 and 7 |
| Versioned configuration and append-only audit evidence | Tasks 2 and 5 |
| Local API, status, settings, commands and development simulator | Task 6 |
| Authenticated admin writes and loopback binding | Global constraints; Task 6 |
| Restart behaviour, faults, observability and acceptance evidence | Tasks 4–7 |
| ESP32, GPIO, weather integration deferred | Global constraints and Task 7 README |

The plan contains no unspecified implementation steps: each task defines concrete file paths, interfaces, failing tests, verification commands and commit boundaries.
