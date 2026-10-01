# Raspberry Pi PT100 Display Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add display-only PT100/MAX31865 telemetry to the authenticated display status endpoint in every control mode without giving telemetry any authority over relays or the ten-minute shower timer.

**Architecture:** A new thread-safe `TemperatureTelemetrySampler` owns the temperature source only in `manual_timed` and `safe_drain`. Automatic mode retains the existing `ControlService.last_reading` path, so only one component can access SPI in a running process. The display serializer applies a fixed 15-second freshness rule and emits only `pipe_temperature_c` and `sensor_health`.

**Tech Stack:** Python 3.12, FastAPI, frozen domain dataclasses, `threading`, pytest, Ruff, strict mypy.

**Spec:** [`docs/superpowers/specs/2026-10-01-waveshare-pt100-telemetry-design.md`](../specs/2026-10-01-waveshare-pt100-telemetry-design.md)

## Global Constraints

- Keep `ControlService` as the sole actuator authority. The sampler must not receive an `ActuatorDriver`, call `start_timed_shower()`, call `drain()`, or mutate a control deadline.
- Start the sampler only for `ControlMode.MANUAL_TIMED` and `ControlMode.SAFE_DRAIN`. Automatic mode must continue to use only `ControlService._read_temperature()` and `ControlStatus.last_reading`.
- Keep the five-second sampling interval and the display-only 15-second stale threshold as code constants. A reading whose age is 15.0 seconds or greater is unavailable and serialized as `STALE`.
- Every read attempt replaces the previous snapshot. An error must remove any earlier numeric value immediately.
- Preserve all display authentication, Nginx route allowlisting, paired GPIO behavior, active-low levels, ten-minute timing, and action response shapes.
- Do not expose observation timestamps, SPI device names, MAX31865 fault registers, source identifiers, tokens, or administrator diagnostics through the display endpoint.
- Repository tests are source evidence only. They do not prove deployed SPI, GPIO, relay, valve, or plumbing behavior.

## Review Focus

- Verify there is never more than one owner of `TemperatureSource.read()` in any operating mode.
- Verify the exact freshness boundary: 14.999 seconds remains fresh; 15.0 seconds is `STALE` with a null value.
- Verify expected and unexpected source failures both replace an earlier healthy value and the loop continues.
- Verify temperature changes cannot alter `mode`, `state`, `command`, `remaining_seconds`, `action`, `action_enabled`, or the actuator command history.
- Verify the display payload contains exactly the two approved sensor fields and no diagnostics or credentials.

---

### Task 1: Add the non-automatic telemetry sampler

**Files:**

- Create: `src/freeze_protect/application/temperature_telemetry.py`
- Create: `tests/unit/test_temperature_telemetry.py`

**Interfaces:**

```python
DISPLAY_TEMPERATURE_SAMPLE_INTERVAL_S = 5.0
DISPLAY_TEMPERATURE_STALE_AFTER_S = 15.0

class TemperatureTelemetrySampler:
    def __init__(
        self,
        source: TemperatureSource,
        *,
        clock: Callable[[], datetime],
        sample_interval_s: float = DISPLAY_TEMPERATURE_SAMPLE_INTERVAL_S,
        stale_after_s: float = DISPLAY_TEMPERATURE_STALE_AFTER_S,
    ) -> None: ...

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def sample_once(self) -> TemperatureReading: ...
    def snapshot(self) -> TemperatureReading: ...
```

`snapshot()` returns `TemperatureReading(None, observed_at, SensorHealth.STALE)` when a healthy cached reading has reached the 15-second display threshold. Before the first sample, it returns an unavailable `STALE` reading timestamped with the construction clock. Non-healthy source results retain their health enum but always expose `value_c=None`.

- [ ] **Step 1: Write failing snapshot tests.** Cover the initial unavailable snapshot, a healthy sample, `INVALID`, `STALE`, and `CALIBRATION_REQUIRED` samples, replacement of a prior numeric value, and the 14.999/15.0-second boundary. Use an aware mutable wall clock and a deterministic fake `TemperatureSource`.
- [ ] **Step 2: Write failing lifecycle tests.** Prove `start()` samples immediately, samples repeatedly at a short injected interval, never overlaps reads, survives an `AdapterError` and an unexpected exception, and `stop()` joins cleanly. Repeated `start()` before `stop()` and repeated `stop()` calls are harmless; restarting the same sampler after `stop()` is intentionally unsupported and must not create a new thread.
- [ ] **Step 3: Run the focused tests and capture the expected failure.** Run `python -m pytest -q tests/unit/test_temperature_telemetry.py`. The test module should fail because the sampler does not exist.
- [ ] **Step 4: Implement the minimum sampler.** Use one lock to serialize reads and protect the immutable snapshot, one daemon thread, and one stop event. Measure the wait from each sample start so slow reads do not add unbounded cadence drift. `sample_once()` catches expected and unexpected source exceptions, stores a fixed unavailable `STALE` snapshot, and logs only a fixed sensor failure classification without credentials or adapter diagnostic payloads. Treat a future-dated observation as unavailable `STALE`.
- [ ] **Step 5: Run focused verification.** Run `python -m pytest -q tests/unit/test_temperature_telemetry.py`, `python -m ruff check src/freeze_protect/application/temperature_telemetry.py tests/unit/test_temperature_telemetry.py`, and `python -m mypy src/freeze_protect/application/temperature_telemetry.py`. All must pass.
- [ ] **Step 6: Commit the sampler slice.** Commit with `git add src/freeze_protect/application/temperature_telemetry.py tests/unit/test_temperature_telemetry.py && git commit -m "feat(telemetry): sample PT100 for display"`.

### Task 2: Compose one sensor owner per mode

**Files:**

- Modify: `src/freeze_protect/api/app.py`
- Modify: `tests/integration/test_m1_api.py`

**Composition contract:**

- `create_app()` constructs `TemperatureTelemetrySampler` only when `control_mode is not ControlMode.AUTOMATIC`.
- Expose the optional sampler as `app.state.temperature_telemetry_sampler` for deterministic tests and diagnostics of ownership, using `None` in automatic mode.
- Lifespan order for non-automatic mode is `service.startup()` (which reasserts `DRAIN`), sampler `start()`, request serving, sampler `stop()`, control-loop `stop()`, final `service.drain("shutdown_drain")`.
- Respect `run_background=False`: construct the sampler but do not start its thread. Tests may call `sample_once()` explicitly.
- Automatic mode starts no sampler and serializes `service.status().last_reading`.

- [ ] **Step 1: Write failing ownership and lifecycle integration tests.** In `manual_timed` and `safe_drain`, assert the sampler exists and automatic control cycles do not read the source. In `automatic`, assert the sampler is `None`, a control cycle is the only source read, and display status uses `last_reading`. Patch `TemperatureTelemetrySampler.start`/`stop` to record lifespan order without touching SPI.
- [ ] **Step 2: Write failing isolation tests.** Starting from an unchanged manual valve status and actuator command list, call `sample_once()` with healthy and failing sources. Assert all valve fields and actuator commands remain identical.
- [ ] **Step 3: Run the focused tests and capture the expected failures.** Run `python -m pytest -q tests/integration/test_m1_api.py -k 'telemetry or temperature or automatic'`.
- [ ] **Step 4: Wire the sampler in `create_app()`.** Keep the same `TemperatureSource` instance but pass it to exactly one runtime reader based on `ControlMode`. Do not change `ControlService` mode logic or `PeriodicControlLoop` behavior.
- [ ] **Step 5: Run the focused API and loop tests.** Run `python -m pytest -q tests/unit/test_temperature_telemetry.py tests/unit/test_periodic_loop.py tests/integration/test_m1_api.py`. All must pass.
- [ ] **Step 6: Commit the composition slice.** Commit with `git add src/freeze_protect/api/app.py tests/integration/test_m1_api.py && git commit -m "feat(api): compose PT100 display telemetry"`.

### Task 3: Extend the authenticated display status contract

**Files:**

- Modify: `src/freeze_protect/api/app.py`
- Modify: `tests/integration/test_m1_api.py`

**Serialization contract:**

```python
def _display_status_payload(
    control: ControlStatus,
    settings: SafetySettings,
    temperature: TemperatureReading | None,
) -> dict[str, object]: ...
```

Every successful display response adds:

```json
{"pipe_temperature_c": 6.4, "sensor_health": "HEALTHY"}
```

Unavailable startup, stale, invalid, and calibration-required responses use a null value and the corresponding uppercase health enum. A healthy reading at or beyond the display freshness threshold, or with a future observation timestamp, is normalized to null plus `STALE` before serialization. Use the injected `clock_fn`, rather than module-level `_now()`, for this decision so tests and production share one time source.

- [ ] **Step 1: Replace obsolete negative assertions with failing contract tests.** Update tests that currently assert the sensor fields are absent. Assert both fields are always present, administrator-only diagnostics remain absent, and legacy valve fields are byte-for-byte equivalent apart from the two additions.
- [ ] **Step 2: Add a health matrix.** Parameterize healthy, `STALE`, `INVALID`, `CALIBRATION_REQUIRED`, source failure after success, and freshness expiry. Assert no unavailable case retains a numeric value.
- [ ] **Step 3: Add mode and security coverage.** Prove automatic mode uses `ControlStatus.last_reading`; manual and safe modes use the sampler snapshot; missing/admin/wrong display tokens still return 401; and the serialized payload contains no token, source ID, device path, fault register, fault names, `last_reading`, or `sensor_diagnostics`.
- [ ] **Step 4: Run the focused API tests and capture the expected failures.** Run `python -m pytest -q tests/integration/test_m1_api.py`.
- [ ] **Step 5: Implement the serializer change.** Select the reading in the route from the active mode owner, normalize display freshness once, and merge only `pipe_temperature_c` and `sensor_health` into the existing dictionary. Do not change the Nginx configuration or add a route.
- [ ] **Step 6: Run focused verification.** Run `python -m pytest -q tests/unit/test_temperature_telemetry.py tests/integration/test_m1_api.py tests/integration/test_node_red_flow.py`, followed by `python -m ruff check src tests` and `python -m mypy src`. All must pass.
- [ ] **Step 7: Commit the API contract slice.** Commit with `git add src/freeze_protect/api/app.py tests/integration/test_m1_api.py && git commit -m "feat(display): expose safe PT100 telemetry"`.

### Task 4: Align operator documentation and evidence boundaries

**Files:**

- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/PROJECT_STATE.md`
- Modify: `docs/VERIFICATION.md`
- Modify: `deployment/COMMISSIONING.md`
- Modify: `deployment/DISPLAY_COMMISSIONING.md`

- [ ] **Step 1: Identify statements superseded by the feature.** Remove the claim that manual display status intentionally contains no sensor value. Preserve the statement that temperature has no control authority in `manual_timed` and that `sensor_commissioned` remains false.
- [ ] **Step 2: Document the two-reader exclusion.** Explain that non-automatic modes use the display sampler while automatic mode uses `ControlService.last_reading`, and that they never run together.
- [ ] **Step 3: Document the public display shape.** Add the two fields, uppercase health values, five-second cadence, 15-second display staleness, and exact unavailable behavior. State that diagnostics remain administrator-only.
- [ ] **Step 4: Reframe PT100 commissioning.** Split display-only sensor verification from future automatic-policy commissioning. Keep the 24 V valve supply disconnected, leave `FREEZE_PROTECT_CONTROL_MODE=manual_timed`, and do not set `sensor_commissioned=true` for this feature.
- [ ] **Step 5: Update the evidence ledger carefully.** Record implementation and local test evidence only after it exists. Keep installed Pi revision, physical sensor wiring, display appearance, relay contacts, valves, and water routing as `NOT_VERIFIED` until the later commissioning plan is executed.
- [ ] **Step 6: Run all repository gates.** Run `python -m pytest -q`, `python -m ruff check .`, `python -m mypy src`, `python -m build`, and `git diff --check`. Also run the deployment syntax commands from `.github/workflows/ci.yml`. All must pass before review.
- [ ] **Step 7: Perform a final authority review.** Inspect `git diff --stat` and `git diff`. Search with `rg -n "pipe_temperature_c|sensor_health|TemperatureTelemetrySampler|sensor_commissioned" src tests README.md docs deployment` and confirm every claim matches code and evidence.
- [ ] **Step 8: Commit documentation.** Commit with `git add README.md docs deployment && git commit -m "docs: describe PT100 display telemetry"`.
