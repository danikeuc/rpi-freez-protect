# M1A Hub and relay integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the safe Pi-side controller that keeps both valves paired, persists and validates seven-day Open-Meteo forecasts, exposes a constrained display API, and drives Node-RED only through an authenticated loopback bridge.

**Architecture:** Replace M0's `OPEN`/`CLOSE_OR_PROTECT` simulation policy with a pure M1 policy that produces only paired `SUPPLY` or paired `DRAIN`. A synchronous application service coordinates local sources, the SQLite cache, and an idempotent Node-RED HTTP driver; FastAPI exposes typed administrator and display endpoints while a lifecycle-owned loop refreshes weather hourly and evaluates safety every 30 seconds.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite standard library, `urllib.request`, pytest, Ruff, mypy, Node-RED with `node-red-node-pi-gpio`.

**Spec:** `docs/superpowers/specs/2026-09-11-m1-weather-display-design.md`

## Global Constraints

- `DRAIN` means GPIO 26 and GPIO 20 high/released; `SUPPLY` means both low/energized. GPIO 21 is never used.
- A command must target the two valves as one paired actuator; no API or Node-RED route may target either valve separately.
- Missing, stale, invalid, or uncommissioned DS18B20 input must keep the installation in `FROST_PROTECTION` with `DRAIN`; forecast alone never enables `SUPPLY`.
- Automatic `NORMAL` requires a commissioned healthy sensor above 7 °C and exactly seven date-aligned minima all strictly above 5 °C.
- Display-initiated `TIMED_SHOWER` is server-timed: 10 minutes by default and never longer than 30 minutes; expiry, a drain action, process startup, relay failure, and configuration failure request `DRAIN`.
- The Pi Hub binds to `127.0.0.1`; the Node-RED bridge binds to `127.0.0.1`, authenticates `X-Hub-Token`, and accepts only `SUPPLY` or `DRAIN`.
- Tokens, Wi-Fi credentials, and the final Hub URL are supplied by environment/provisioning and never committed or returned by an API.

---

## File structure

```text
src/freeze_protect/domain/models.py          # M1 state, paired command, settings, readings, forecast, decision
src/freeze_protect/domain/policy.py          # pure automatic M1 eligibility function
src/freeze_protect/application/ports.py      # source, actuator, cache and audit protocols
src/freeze_protect/application/service.py    # startup drain, cycle, timed shower and status coordinator
src/freeze_protect/adapters/weather.py       # strict Open-Meteo HTTP parser
src/freeze_protect/adapters/ds18b20.py       # Linux 1-Wire reader
src/freeze_protect/adapters/node_red.py      # authenticated paired actuator HTTP client
src/freeze_protect/adapters/simulation.py    # deterministic tests only
src/freeze_protect/persistence/sqlite.py     # settings migration, forecast cache and audit persistence
src/freeze_protect/api/auth.py                # constant-time admin and display guards
src/freeze_protect/api/app.py                 # composition, typed APIs and lifespan loop
src/freeze_protect/main.py                    # environment-to-adapter composition and loopback Uvicorn entrypoint
deployment/node-red/freeze-protect-paired-relay.json # importable, loopback-only bridge flow
deployment/systemd/freeze-protect.service     # production service unit template
deployment/freeze-protect.env.example         # non-secret environment-variable template
tests/unit/test_m1_policy.py                  # pure state safety tests
tests/unit/test_weather.py                    # malformed/fresh/stale weather parser tests
tests/unit/test_ds18b20.py                    # 1-Wire parsing tests
tests/unit/test_node_red.py                   # outbound bridge receipt/timeout tests
tests/unit/test_m1_service.py                 # timer, restart and paired-command tests
tests/integration/test_m1_api.py              # auth, display and persisted-cache API tests
tests/integration/test_node_red_flow.py       # exported flow contract test
```

### Task 1: Replace M0 domain language with the M1 safety model

**Files:**
- Modify: `src/freeze_protect/domain/models.py`, `src/freeze_protect/domain/policy.py`
- Create: `tests/unit/test_m1_policy.py`
- Remove: `tests/unit/test_models.py`, `tests/unit/test_policy.py`

**Interfaces:**
- Produces: `ControllerState {STARTING, FROST_PROTECTION, NORMAL, TIMED_SHOWER, FAULT}`, `ActuatorCommand {DRAIN, SUPPLY}`, `SafetySettings`, `ForecastSnapshot(dates: tuple[date, ...], daily_minima_c: tuple[float, ...], source_generated_at: datetime | None, fetched_at: datetime, latitude: float, longitude: float)`, `TemperatureReading`, `Decision`, and `ActuatorReceipt(command: ActuatorCommand, request_id: str, gpio_26: int, gpio_20: int)`.
- Produces: `evaluate_automatic(reading: TemperatureReading, forecast: ForecastSnapshot | None, settings: SafetySettings, now: datetime) -> Decision`.

- [ ] **Step 1: Write failing tests for the invariant and exact forecast rule**

```python
def test_uncommissioned_sensor_is_always_frost_protection() -> None:
    decision = evaluate_automatic(pending_reading(), eligible_forecast(), SETTINGS, NOW)
    assert (decision.state, decision.command, decision.reason) == (
        ControllerState.FROST_PROTECTION, ActuatorCommand.DRAIN, "sensor_pending"
    )

def test_equal_forecast_threshold_is_not_normal() -> None:
    decision = evaluate_automatic(healthy_reading(8.0), forecast((5.1,) * 6 + (5.0,)), SETTINGS, NOW)
    assert decision.command is ActuatorCommand.DRAIN
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/unit/test_m1_policy.py -q`

Expected: FAIL because `ActuatorCommand` and `evaluate_automatic` do not exist.

- [ ] **Step 3: Implement focused immutable domain types and policy**

```python
class ActuatorCommand(str, Enum):
    DRAIN = "DRAIN"
    SUPPLY = "SUPPLY"

def evaluate_automatic(reading, forecast, settings, now) -> Decision:
    if not settings.sensor_commissioned:
        return Decision(ControllerState.FROST_PROTECTION, ActuatorCommand.DRAIN, "sensor_pending")
    if reading.health is not SensorHealth.HEALTHY or reading.value_c is None:
        return Decision(ControllerState.FROST_PROTECTION, ActuatorCommand.DRAIN, "sensor_unhealthy")
    if reading.value_c <= settings.protection_threshold_c:
        return Decision(ControllerState.FROST_PROTECTION, ActuatorCommand.DRAIN, "pipe_below_protection_threshold")
    if forecast is None or not forecast.is_eligible(settings, now):
        return Decision(ControllerState.FROST_PROTECTION, ActuatorCommand.DRAIN, "forecast_not_eligible")
    return Decision(ControllerState.NORMAL, ActuatorCommand.SUPPLY, "automatic_normal")
```

Set the persisted defaults to protection 5.0 °C, release 7.0 °C, forecast threshold 5.0 °C, seven days, sensor stale 120 seconds, forecast stale 21600 seconds, default shower 600 seconds, maximum shower 1800 seconds, `sensor_commissioned=False`, and optional `sensor_device_id`. Validate finite coordinates when supplied, a valid IANA zone, `0 < default <= maximum <= 1800`, and `release_threshold_c > protection_threshold_c`.

- [ ] **Step 4: Run focused and full Python tests**

Run: `python -m pytest -q`

Expected: M1 domain tests pass; no test asserts an old M0 command name.

- [ ] **Step 5: Commit the policy migration**

```bash
git add src/freeze_protect/domain tests/unit/test_m1_policy.py tests/unit/test_models.py tests/unit/test_policy.py
git commit -m "feat: add M1 paired actuator safety policy"
```

### Task 2: Persist configuration and a finite forecast cache

**Files:**
- Modify: `src/freeze_protect/persistence/sqlite.py`, `src/freeze_protect/application/ports.py`
- Create: `tests/integration/test_m1_sqlite.py`
- Remove: `tests/integration/test_sqlite.py`

**Interfaces:**
- Produces: `ForecastStore.load() -> ForecastSnapshot | None`, `ForecastStore.save(snapshot: ForecastSnapshot) -> None`.
- Produces: `SQLiteSettingsStore`, `SQLiteForecastStore`, `SQLiteEventStore` compatible with M1 dataclasses.

- [ ] **Step 1: Write persistence tests**

```python
def test_cached_forecast_survives_a_store_reopen(tmp_path: Path) -> None:
    store = SQLiteForecastStore(tmp_path / "state.db")
    store.save(ForecastSnapshot(DATES, (6.0,) * 7, NOW))
    assert SQLiteForecastStore(tmp_path / "state.db").load() == ForecastSnapshot(DATES, (6.0,) * 7, NOW)

def test_old_m0_settings_row_loads_with_safe_m1_defaults(tmp_path: Path) -> None:
    insert_m0_settings_json(tmp_path / "state.db")
    assert SQLiteSettingsStore(tmp_path / "state.db").load().sensor_commissioned is False
```

- [ ] **Step 2: Run the persistence test to verify it fails**

Run: `python -m pytest tests/integration/test_m1_sqlite.py -q`

Expected: FAIL because `SQLiteForecastStore` is undefined.

- [ ] **Step 3: Add additive SQLite schema and backwards-safe settings decoding**

Create a singleton `forecast_cache` table with `payload_json` and `updated_at`; retain existing audit events and settings. Decode a stored M0 settings object by overlaying it on the M1 default dictionary, set `sensor_commissioned=False`, and assign the safe M1 threshold defaults rather than inferring commissioning. Store all seven ISO dates, minima, source generation time when supplied, retrieval time, and response coordinates as JSON; reject a cache row that cannot instantiate `ForecastSnapshot`.

- [ ] **Step 4: Run persistence and full tests**

Run: `python -m pytest tests/integration/test_m1_sqlite.py -q && python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit the persistence work**

```bash
git add src/freeze_protect/persistence src/freeze_protect/application/ports.py tests/integration/test_m1_sqlite.py tests/integration/test_sqlite.py
git commit -m "feat: persist M1 settings and forecast cache"
```

### Task 3: Implement deterministic adapters for weather, DS18B20 and Node-RED

**Files:**
- Create: `src/freeze_protect/adapters/weather.py`, `src/freeze_protect/adapters/ds18b20.py`, `src/freeze_protect/adapters/node_red.py`
- Modify: `src/freeze_protect/adapters/simulation.py`, `src/freeze_protect/application/ports.py`
- Create: `tests/unit/test_weather.py`, `tests/unit/test_ds18b20.py`, `tests/unit/test_node_red.py`

**Interfaces:**
- Produces: `OpenMeteoForecastClient.fetch(settings: SafetySettings, now: datetime) -> ForecastSnapshot`.
- Produces: `Ds18b20TemperatureSource.read() -> TemperatureReading` and `NodeRedActuatorDriver.command(command: ActuatorCommand) -> ActuatorReceipt`.
- Consumes: an injected `urlopen(request, timeout)` callable and a configurable `Path` so unit tests make no network or `/sys` calls.

- [ ] **Step 1: Write failing adapter tests**

```python
def test_open_meteo_rejects_a_six_day_or_non_finite_payload() -> None:
    with pytest.raises(AdapterError, match="exactly seven"):
        client_with_json({"daily": {"time": ["2026-09-11"] * 6, "temperature_2m_min": [6.0] * 6}}).fetch(SETTINGS, NOW)

def test_node_red_requires_matching_paired_receipt() -> None:
    with pytest.raises(AdapterError, match="receipt"):
        driver_with_json({"command": "SUPPLY", "gpio": {"26": 0, "20": 1}}).command(ActuatorCommand.SUPPLY)
```

- [ ] **Step 2: Run focused adapter tests to verify they fail**

Run: `python -m pytest tests/unit/test_weather.py tests/unit/test_ds18b20.py tests/unit/test_node_red.py -q`

Expected: FAIL because production adapters are absent.

- [ ] **Step 3: Implement strict adapter boundaries**

Use this exact Open-Meteo query construction:

```python
query = urlencode({
    "latitude": settings.latitude,
    "longitude": settings.longitude,
    "daily": "temperature_2m_min",
    "forecast_days": 7,
    "timezone": settings.timezone,
})
request = Request(f"https://api.open-meteo.com/v1/forecast?{query}", headers={"Accept": "application/json"})
```

Require exactly seven ISO dates and seven finite numeric minima, dates increasing by one day, and a response latitude/longitude within `0.01` of configured coordinates. Parse `/sys/bus/w1/devices/<28-id>/w1_slave`, require first line ending `YES`, parse `t=<millidegrees>`, and mark values stale when `now - mtime > sensor_stale_after_s`. Send Node-RED a JSON POST with a UUID request ID and `X-Hub-Token`; accept only an HTTP 200 JSON receipt containing the requested command and GPIO map `{26: expected, 20: expected}`.

- [ ] **Step 4: Run adapter tests and static checks**

Run: `python -m pytest tests/unit/test_weather.py tests/unit/test_ds18b20.py tests/unit/test_node_red.py -q && python -m ruff check src tests && python -m mypy src`

Expected: PASS.

- [ ] **Step 5: Commit adapters**

```bash
git add src/freeze_protect/adapters src/freeze_protect/application/ports.py tests/unit/test_weather.py tests/unit/test_ds18b20.py tests/unit/test_node_red.py
git commit -m "feat: add weather sensor and node-red adapters"
```

### Task 4: Coordinate startup drain, safe timer and periodic safety cycles

**Files:**
- Modify: `src/freeze_protect/application/service.py`, `src/freeze_protect/adapters/simulation.py`
- Create: `tests/unit/test_m1_service.py`
- Remove: `tests/unit/test_service.py`

**Interfaces:**
- Produces: `ControlService.startup() -> Decision`, `run_cycle() -> Decision`, `start_timed_shower() -> Decision`, `drain(reason: str) -> Decision`, and `status() -> ControlStatus`, where `ControlStatus` contains `state`, `reason`, `last_reading`, `forecast`, `timed_shower_deadline`, and `last_receipt`.
- Produces: `ControlLoop.start()` and `ControlLoop.stop()`; the loop invokes weather refresh every 3600 seconds and `run_cycle()` every 30 seconds.

- [ ] **Step 1: Write failing service tests**

```python
def test_startup_always_issues_drain_before_status_becomes_available() -> None:
    service.startup()
    assert relay.commands == [ActuatorCommand.DRAIN]
    assert service.status().state is ControllerState.FROST_PROTECTION

def test_timed_shower_expires_to_drain_and_never_exceeds_maximum() -> None:
    service.start_timed_shower()
    clock.advance(601)
    assert service.run_cycle().command is ActuatorCommand.DRAIN
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.SUPPLY, ActuatorCommand.DRAIN]
```

- [ ] **Step 2: Run focused service tests to verify they fail**

Run: `python -m pytest tests/unit/test_m1_service.py -q`

Expected: FAIL because the M0 service has no `startup` or timed-shower interfaces.

- [ ] **Step 3: Implement synchronous, lock-protected coordination**

At `startup`, always dispatch `DRAIN`, reset any persisted/active timer, append `startup_drain`, then evaluate to `FROST_PROTECTION` without a sensor. A bridge failure transitions to `FAULT` and records `relay_driver_error`; on a failed `SUPPLY`, immediately make one best-effort `DRAIN` request and do not retry `SUPPLY`. `start_timed_shower` rejects `FAULT`, records a deadline of `now + timed_shower_default_s`, sends one `SUPPLY`, and writes an audit event. `run_cycle` checks timer expiry first, then evaluates automatic conditions. Never let an endpoint supply a duration.

- [ ] **Step 4: Run service and full tests**

Run: `python -m pytest tests/unit/test_m1_service.py -q && python -m pytest -q`

Expected: PASS, including restart and immediate-drain scenarios.

- [ ] **Step 5: Commit service changes**

```bash
git add src/freeze_protect/application/service.py src/freeze_protect/adapters/simulation.py tests/unit/test_m1_service.py tests/unit/test_service.py
git commit -m "feat: add safe timed shower control service"
```

### Task 5: Publish authenticated administrator and display APIs

**Files:**
- Modify: `src/freeze_protect/api/auth.py`, `src/freeze_protect/api/app.py`, `src/freeze_protect/main.py`
- Create: `tests/integration/test_m1_api.py`
- Remove: `tests/integration/test_api.py`, `tests/integration/test_m0_acceptance.py`

**Interfaces:**
- Produces: `GET/PUT /api/v1/settings`, `GET /api/v1/status`, `GET /api/v1/display/status`, `POST /api/v1/display/actions/timed-shower`, and `POST /api/v1/display/actions/drain`.
- Consumes: `X-Admin-Token` for administrator endpoints and `X-Display-Token` for display endpoints, compared with `secrets.compare_digest`.

- [ ] **Step 1: Write API contract tests**

```python
def test_display_token_can_start_and_stop_only_a_server_timed_shower(client: TestClient) -> None:
    assert client.post("/api/v1/display/actions/timed-shower", headers=DISPLAY).status_code == 200
    assert client.get("/api/v1/display/status", headers=DISPLAY).json()["action"] == "CLOSE_NOW"
    assert client.post("/api/v1/display/actions/drain", headers=DISPLAY).status_code == 200

def test_missing_or_admin_token_on_display_endpoint_is_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/display/status").status_code == 401
    assert client.get("/api/v1/display/status", headers=ADMIN).status_code == 401
```

- [ ] **Step 2: Run focused API tests to verify they fail**

Run: `python -m pytest tests/integration/test_m1_api.py -q`

Expected: FAIL because the display token guard and endpoints do not exist.

- [ ] **Step 3: Compose production and development dependencies safely**

Use FastAPI lifespan to call `service.startup()`, start the periodic loop, stop it on shutdown, and never bind a public listener. `GET /api/v1/status` and settings require admin authentication. The display status contains only `state`, `reason`, pipe temperature or `None`, sensor health, weather freshness/minima, active timer deadline, and action label; it excludes all tokens, Node-RED address, relay pins, and admin settings. Retain development simulation behind `FREEZE_PROTECT_DEVELOPMENT_MODE=true`, with no production route.

- [ ] **Step 4: Run API, full and build checks**

Run: `python -m pytest tests/integration/test_m1_api.py -q && python -m pytest -q && python -m ruff check . && python -m mypy src && python -m build`

Expected: PASS.

- [ ] **Step 5: Commit API composition**

```bash
git add src/freeze_protect/api src/freeze_protect/main.py tests/integration/test_m1_api.py tests/integration/test_api.py tests/integration/test_m0_acceptance.py
git commit -m "feat: expose authenticated M1 display API"
```

### Task 6: Ship an inspectable Node-RED flow and Pi deployment assets

**Files:**
- Create: `deployment/node-red/freeze-protect-paired-relay.json`, `deployment/systemd/freeze-protect.service`, `deployment/freeze-protect.env.example`, `deployment/COMMISSIONING.md`, `tests/integration/test_node_red_flow.py`
- Modify: `README.md`

**Interfaces:**
- Produces: one Node-RED `POST /internal/freeze-protect/actuator` flow that returns `{command, request_id, gpio:{"26":level,"20":level}, flow_revision}`.
- Consumes: `FREEZE_PROTECT_HUB_TOKEN`, the deployed Hub's `FREEZE_PROTECT_NODE_RED_URL`, and only 24 V valve contacts wired by the physical commissioning procedure.

- [ ] **Step 1: Write static flow-contract test**

```python
def test_flow_has_only_one_post_route_and_never_mentions_gpio21() -> None:
    flow = json.loads(FLOW_PATH.read_text())
    assert [(node["method"], node["url"]) for node in flow if node["type"] == "http in"] == [("post", "/internal/freeze-protect/actuator")]
    assert "GPIO21" not in FLOW_PATH.read_text()
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `python -m pytest tests/integration/test_node_red_flow.py -q`

Expected: FAIL because the safe exported flow is absent.

- [ ] **Step 3: Create the production flow and deployment instructions**

The flow must have an inject-once DRAIN branch wired to GPIO 26 and 20, a Function node that rejects a missing/mismatched `X-Hub-Token`, rejects values other than uppercase `SUPPLY`/`DRAIN`, writes both GPIO outputs before its HTTP receipt, and has no timer or GET route. The function maps `SUPPLY` to `0`/`0` and `DRAIN` to `1`/`1`. Document import into the existing active `node-red.service`, successful `curl` loopback health receipt, systemd environment files mode `0600`, electrical isolation, and the five physical checks from the spec.

- [ ] **Step 4: Run flow, full, static and package verification**

Run: `python -m pytest -q && python -m ruff check . && python -m mypy src && python -m build`

Expected: PASS.

- [ ] **Step 5: Commit deployable Hub assets**

```bash
git add README.md deployment tests/integration/test_node_red_flow.py
git commit -m "docs: add M1 Pi relay commissioning assets"
```
