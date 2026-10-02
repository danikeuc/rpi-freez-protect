# Weather-Assisted Shower Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Offer continuous shower supply for a qualifying five-day forecast and preserve deliberately started 1–10 minute showers otherwise.

**Architecture:** The Pi owns weather, persistent inhibition, deadlines and actuator decisions. A bounded background weather worker cannot block the controller or protocol-2 renewal. The Dial adds authenticated weather settings and an AUTO presentation using additive capability-gated APIs.

**Tech Stack:** Python >=3.12, FastAPI/Pydantic, SQLite, urllib, existing Node-RED/protocol-2 GPIO daemon; C/LVGL with ESP-IDF 5.5.5 on the Waveshare ESP32-S3.

**Spec:** [Approved weather design](../specs/2026-10-02-weather-assisted-shower-design.md).

**Status:** Written for owner review on 2026-10-03; no implementation or tests claimed. Execution method and this plan require confirmation. Read the spec as well as this plan.

## Global Constraints

- Today plus four local dates; five finite Celsius minima **>=5.0 C**, including equality. Default timezone `Europe/Ljubljana`.
- Refresh every **900 monotonic seconds**; accepted fetch deadline **5 seconds**; snapshot maximum age **1,200 monotonic seconds**; control processing bound **30 seconds**. Failure of the latest fetch invalidates warm cache.
- New opt-in `weather_assisted` mode AND saved enabled preference required. Fresh installation is disabled. Preserve `safe_drain`, `manual_timed` and legacy seven-day `automatic` behavior.
- Existing accepted manual interval is **60–600 seconds**, whole minutes; duplicate commands, forecast changes and admin changes never extend it.
- PT100 remains informational. Both outputs are one group: high/high DRAIN, low/low SUPPLY; mixed pairs prohibited.
- Existing **60-second daemon lease**, BEGIN/RENEW distinction and single GPIO writer remain. Failed/ambiguous receipt means DRAIN/FAULT; never substitute BEGIN for failed RENEW.
- A user STOP persists until a fresh deliberate START; weather recovery cannot clear a fault or inhibition.
- Pi owns weather persistence; Dial owns PIN, duration and rotation. Weather credentials are distinct from display and general-admin tokens.
- Preserve published v1.0.0/v1.1.0 artifacts. No BLE work, physical actuation, deployment, firmware upload, merge or release in implementation tasks.

## Review Focus

- An old-location result arriving after a settings update must never authorize AUTO: W2/W3 generation tests.
- A hung DNS/socket worker must not block timer expiry, lease renewal or shutdown: W2/W3 stalled-worker tests.
- A database write failing during active supply must not reopen after restart: W1/W3 durable recovery tests, conservative marker rule below.
- A stale START after a later STOP or reboot must not clear inhibition: W4 revision/nonce and replay tests.
- A midnight/DST/date reversal and an old client receiving AUTO must not create false freshness/countdown: W1/W5 boundary tests.

## Baselines, file ownership and execution order

Pi baseline `87b12236af955ec068ddd673b7b702ebc09fe846`, design branch currently contains documentation only. Dial release baseline `9bd5fc062d91f9ca7b3c6bd4c54dc60481129007`; inspected local head `b5c364d48b0310c4a804a22e8ae47bea3f7cd97d` predates its merge. Verify trees and clean state before using either. Reuse suitable attached worktrees; use managed worktree creation if isolation is needed. Never reset the user's old/dirty checkout.

W1 -> W2 -> W3 -> W4 -> W5 -> W6. The playlist plan can progress independently until its Dial changes touch `admin_server_dial.c`, `admin_page_dial.h`, the CMake source list or gesture code. Integrate those shared files serially. W1–W4 produce a testable Pi backend with weather disabled; W5 adds its usable admin and display.

No live provider, SSH or hardware access is needed for unit/integration tests. Use existing commissioning docs only for later, separately authorized deployment.

## Contracts to implement

### Weather model and durable recovery

Keep the existing seven-element `ForecastSnapshot` intact. Introduce frozen `WeatherSettings(enabled: bool, latitude: float | None, longitude: float | None, timezone: str, revision: int)` and `WeatherWindow(dates: tuple[date, ...], minima_c: tuple[float, ...], fetched_at: datetime, requested_latitude: float, requested_longitude: float, timezone: str, settings_revision: int, generation: int)` in `domain/weather.py`. Exactly five dates/values; bools and nonfinite numbers invalid.

`WeatherObservation(window: WeatherWindow | None, received_mono: float, latest_attempt_ok: bool, reason: str)` is process-local and cannot be restored as eligible from disk. `WeatherEligibility(eligible: bool, reason: str)` is the pure validator output. A wall-clock vs monotonic discrepancy exceeding 30 seconds invalidates the time basis until a new successful fetch; local date changes independently invalidate missing current-day coverage.

`WeatherControlRecord(settings: WeatherSettings, user_off: bool, fault_inhibited: bool, active_marker: str | None, control_revision: int)` is a singleton SQLite record. Marker values are `manual`/`auto`/null. Persist the marker before BEGIN, and clear only after confirmed DRAIN plus successful durable writes. Atomic compare-and-swap checks and increments `control_revision`; settings edits additionally increment `settings.revision` in the same transaction. Polling/status reads and ordinary lease renewals do not increment either revision. Store creation is distinguishable from an unexpectedly missing/corrupt established record; the latter faults closed.

**Conservative planning refinement for approval:** an uncleared `auto` marker after unclean shutdown also inhibits reopening until deliberate START, just like an interrupted manual interval. This closes the case where a fault cannot be written to a failed disk. A clean shutdown clears the marker after confirmed DRAIN, allowing a later fresh forecast to restore AUTO. Do not silently implement automatic resumption after an unclean exit instead. This strengthens the approved spec's interrupted-manual recovery rule and is part of this plan review.

### New Pi and Dial API surface

All new JSON inputs reject unknown/duplicate fields, bool-as-int, NaN/Infinity and oversized bodies (4 KiB). No raw provider body or secrets in errors. Credentials use existing constant-time guard conventions.

| Method/path | Credential | Contract |
| --- | --- | --- |
| GET `/api/v1/display/weather-settings` | restricted weather credential | `{revision,enabled,latitude,longitude,timezone}`; no secrets |
| PUT same | restricted weather credential | `{expected_revision,enabled,latitude,longitude,timezone}`; CAS; returned saved object |
| POST `/api/v1/display/actions/start` | display | `{request_id,expected_control_revision,action_nonce,duration_seconds}`; AUTO if eligible, otherwise bounded manual |
| POST `/api/v1/display/actions/stop` | display | `{request_id,expected_control_revision,action_nonce}`; durable USER_OFF + DRAIN |
| GET existing `/api/v1/display/status` | display | additive `weather_assistance_version:1`, `operation`, `control_revision`, `action_nonce`, `weather` |
| GET/PUT `/admin/api/weather` on Dial | PIN session; CSRF for PUT | proxy exact settings schema; no browser credential access |

`operation` is MANUAL_IDLE/MANUAL_ACTIVE/AUTO_SUPPLY/USER_OFF/FAULT. `weather` contains `{enabled,available,eligible,reason,dates,minima_c,last_successful_check}`. `remaining_seconds` stays 0 for AUTO; `command` and temperature fields retain meaning. The additive nonce is a random process-local, single-use authorization freshness value valid for **10 seconds**, bound to a control revision; at most 64 outstanding nonces, removing expired entries before capacity checks. Full capacity rejects new issuance rather than evicting an in-flight accepted action. A pending/rejected issuance never disables legacy DRAIN. Do not expose the nonce in access logs.

Successful new action responses have `{request_id,accepted:true,control_revision,status}`, where `control_revision` is the recorded result revision and `status` is the current display status. Matching replays retain that recorded revision and refresh only `status`; rejected actions use the documented HTTP errors. Use UUID request IDs. Persist body hashes and acceptance/result metadata before any BEGIN for at most the latest 128 new-action requests; a reused ID with different body returns 409. A matching replay returns its recorded outcome plus fresh status and never performs I/O again. A stale revision/nonce returns 409 without START. Startup durably advances the control revision and invalidates old nonces. No automatic action retry following HTTP timeout. New STOP conflicts can always be followed by the existing unconditional DRAIN path as a new deliberate operator stop.

Keep legacy `/actions/timed-shower` explicitly bounded and `/actions/drain` available. In weather mode an old timed-shower action cannot clear an existing USER_OFF/fault inhibition; return 409 requiring the fresh new START. A legacy DRAIN always inhibits weather. If an old bounded action arrives during AUTO, confirm DRAIN before a new bounded BEGIN; a duplicate active manual action keeps the old deadline. Internal fallback/shutdown drains do not create user inhibition.

Errors: 401 bad/missing credential, 409 revision/replay/not-ready conflict, 413 body too large, 422 invalid input, 503 unavailable storage/controller. Persistence failures also request DRAIN and latch fault. GET is not a command to enable AUTO.

## Task W1: Five-day rules and durable weather state

**Files:** create `src/freeze_protect/domain/weather.py`, `persistence/weather.py`; modify `domain/models.py` for `ControlMode.WEATHER_ASSISTED` and AUTO controller state; create `tests/unit/test_weather_policy.py`, `tests/integration/test_weather_store.py`.

**Interfaces:** `evaluate_weather(settings: WeatherSettings, observation: WeatherObservation | None, now: datetime, now_mono: float) -> WeatherEligibility`; `SQLiteWeatherStore(database_path: Path).load() -> WeatherControlRecord`; `.compare_and_swap(expected_control_revision: int, record: WeatherControlRecord) -> WeatherControlRecord`. Define `WeatherRevisionConflict` and `WeatherStateError` in the new persistence module. Settings revision advances only on settings edits; control revision advances on control/recovery transitions.

- [ ] Write `test_threshold_inclusive`: five minima all 5.0/5.1 -> eligible; any 4.9 -> false. Assert 4/6 dates, nonconsecutive/duplicate/missing-today dates, bool/null/nonfinite values, wrong timezone, disabled preference and failed-latest-attempt cannot qualify. Assert freshness expires at `age >= 1200`, and clock reversal/DST/local midnight require new coverage.
- [ ] Write store tests: new database disabled; migrate an existing v1.1.0 database without changing old settings/cache/events; missing established record/corrupt JSON faults; stale CAS fails; marker and inhibition survive reload; injected write failure preserves the last complete record. Test auto/manual active markers after unclean exit.
- [ ] Run `python -m pytest -q tests/unit/test_weather_policy.py tests/integration/test_weather_store.py`; confirm failure is the absent behavior, not a fixture/import-environment problem.
- [ ] Implement the exact interfaces and additive `weather_control` singleton plus version marker, using SQLite transactions, strict decoding and the existing database path. Keep old seven-day decoding unchanged. Rerun the focused suite and `python -m ruff check .` to PASS.
- [ ] Commit the listed source/tests with `feat(weather): add five-day rules and durable inhibition`.

## Task W2: Bounded weather fetch outside control execution

**Files:** modify `adapters/weather.py`; create `application/weather_worker.py`; create `tests/unit/test_weather_window.py`, `tests/unit/test_weather_worker.py`.

**Interfaces:** `OpenMeteoForecastClient.fetch_window(settings: WeatherSettings, now: datetime, generation: int) -> WeatherWindow`; immutable `WeatherRequest(settings, requested_at, generation)` and `WeatherResult(request, window: WeatherWindow | None, error: str | None)` in worker module; `WeatherWorker(fetch, wake, monotonic_clock).submit(request: WeatherRequest) -> bool`, `.poll() -> WeatherResult | None`, `.stop(timeout_s: float = 1.0) -> None`.

- [ ] Write adapter tests asserting HTTPS, `forecast_days=5`, `temperature_unit=celsius`, requested timezone and `daily=temperature_2m_min`; reject redirects, >65,536 bytes, missing/wrong units/timezone, malformed numeric data and invalid returned coordinates. A valid grid coordinate differing by >0.01 degrees must be accepted while requested provenance remains unchanged. Old `fetch()` seven-day fixtures must still pass.
- [ ] Write worker tests with injected clocks/blocking transport: one outstanding request maximum, no replacement-thread growth after a hang, result at/after five seconds rejected, late old-generation reply cannot restore eligibility, cancellation and shutdown join <=1 second. Return state is immutable and callback only wakes control.
- [ ] Run `python -m pytest -q tests/unit/test_weather_window.py tests/unit/test_weather_worker.py tests/unit/test_weather.py`; observe new assertions FAIL before implementation.
- [ ] Implement bounded response reading with verified HTTPS/no redirects and a single daemon worker. Use monotonic deadline checks around result handoff; socket timeout alone is not a total DNS/read deadline. Discard stale work and never block control waiting for the worker. Rerun to PASS.
- [ ] Commit `feat(weather): isolate bounded forecast requests from control`.

## Task W3: Integrate policy, manual timing and lease ownership

**Files:** modify `application/service.py`, `application/ports.py`; create `application/weather_control.py` for weather coordination; create `tests/unit/test_weather_service.py`, `tests/integration/test_weather_lease.py`; extend `tests/unit/test_periodic_loop.py`.

**Interfaces:** `WeatherCoordinator(store: SQLiteWeatherStore, worker: WeatherWorker, clock, monotonic_clock)` owns current observation/generation and exposes `.tick() -> WeatherEligibility`, `.update_settings(expected_revision: int, settings: WeatherSettings) -> WeatherSettings`, `.invalidate(reason: str) -> None`. `ControlService` gains optional coordinator/store dependencies, `start_weather_shower(duration_seconds: int) -> Decision`, `stop_weather_shower() -> Decision`; only ControlService emits actuator intents under its existing lock. Use the W1 durable record and W2 request/result types; no duplicate state machine in the Dial.

- [ ] Write trace tests: startup DRAIN -> warm BEGIN -> valid RENEWs; warm-cache refresh failure -> DRAIN; cold -> manual idle; manual 180-second timer remains 180 through cold/warm/disable/location changes; expiry confirms DRAIN before any later AUTO. No BEGIN on failed RENEW or ambiguous receipt. Sensor FAULT must not veto eligible weather in this mode.
- [ ] Write fault/recovery tests: STOP persists before acknowledgement, later weather success remains off; START persistence failure emits no SUPPLY; marker remains on failed fault write; reboot marker inhibits; clean shutdown permits new-fetch eligibility; fault clear drains and leaves USER_OFF; database corruption faults. GPIO traces contain only whole paired commands.
- [ ] Write scheduling tests with a stalled weather worker: renewal and manual expiry still run, refresh cadence is 900 seconds, startup/enable/location/midnight trigger immediate refresh, results wake loop within its 30-second processing bound; fallback without location still allows a deliberate bounded shower. Run `python -m pytest -q tests/unit/test_weather_service.py tests/unit/test_periodic_loop.py tests/integration/test_weather_lease.py` and observe expected failures.
- [ ] Implement coordination and runtime branches; retain old mode behavior. Worker lifecycle belongs to application lifespan. `PeriodicControlLoop` must not invoke blocking fetch in weather mode; preserve separate temperature telemetry. Run focused tests and existing service/daemon lease suites to PASS.
- [ ] Commit `feat(control): integrate weather-assisted shower policy`.

## Task W4: Authenticated API, freshness and gateway allowlist

**Files:** create `api/weather.py`, `application/weather_actions.py`; modify `api/app.py`, `api/auth.py`, `main.py`, `deployment/nginx/freeze-protect-display.conf`; create `tests/integration/test_weather_api.py`, `tests/unit/test_weather_actions.py`; extend `tests/integration/test_workstation_commissioning_assets.py`.

**Interfaces:** `WeatherActionInput(request_id: str, expected_control_revision: int, action_nonce: str, duration_seconds: int | None)` strict DTO; `WeatherActionGate.execute(action: str, request: WeatherActionInput) -> WeatherActionResult` serializes CAS/dedup/freshness and calls W3 exactly once. `WeatherActionResult` has `request_id: str`, `accepted: bool`, `control_revision: int` and `status` using the existing display-status serialization extended with W4 fields. Its JSON is the action-response contract above. Persist request receipts in additive `weather_action_receipts` table using the W1 database. `build_weather_guard(token: str | None)`; optional `weather_settings_token` keyword in `create_app`, sourced from `FREEZE_PROTECT_WEATHER_SETTINGS_TOKEN`.

- [ ] Write full request/response assertions for the contract table, including old-client routes, bool durations, missing/extra/duplicate fields, six-day data rejection, 401 for display token on settings write and weather token on general admin routes, and 405/404 gateway constraints.
- [ ] Write replay/race tests: stale START after STOP/reboot rejected; same-ID retry never extends/reopens; same ID/different body conflicts; accepted receipt followed by crash does not replay BEGIN; full nonce pool and expired nonce cannot block DRAIN; expired HTTP responses never imply success. Run `python -m pytest -q tests/integration/test_weather_api.py tests/unit/test_weather_actions.py` and observe FAIL.
- [ ] Implement exact routes/status additions/auth and body limits. Serialize gate work with ControlService; persist intent before I/O and report unknown effect as FAULT. Legacy timed action stays bounded. Add only exact Nginx locations/methods; no general-admin exposure and no commissioning allowlist changes.
- [ ] Run focused tests plus `python -m pytest -q tests/integration/test_m1_api.py tests/integration/test_workstation_commissioning_assets.py`; verify PASS and `git diff --check`.
- [ ] Commit `feat(api): expose scoped weather settings and explicit actions`.

## Task W5: Dial weather admin and AUTO state

**Files in Dial:** create `idf_app/main/weather_admin_dial.[ch]`; modify `admin_server_dial.c`, `admin_page_dial.h`, `valve_config_dial.[ch]`, `valve_client_dial.c`, `valve_logic.[ch]`, `valve_ui_dial.c`, `idf_app/main/CMakeLists.txt`; create `tests/admin_dial/test_weather_admin.c`; extend existing admin browser/HTTP and valve fixtures plus their runners.

**Interfaces:** `bool weather_admin_get(weather_settings_view_t *out)`, `bool weather_admin_update(const weather_settings_write_t *request, weather_settings_view_t *out)` use the exact W4 DTOs and a separate privately provisioned NVS weather token. `valve_status_t` gains capability version, operation, control revision and nonce. `valve_request_t` distinguishes legacy timed, weather start, weather stop and DRAIN. No network/NVS calls in LVGL callbacks; immutable mailbox completion with config/session generation checks.

- [ ] Write host tests: fresh capability selects new START route, stale/missing capability never sends it; a fresh status/nonce is fetched after a deliberate START when the cached nonce has expired, within the existing 10-second unsent gesture lifetime; no action is retried after uncertain dispatch; existing timed routes retain old firmware/Pi fallback; AUTO with `remaining_seconds=0` still renders supply/AUTO; unknown capability/state is unknown, never guessed as expired.
- [ ] Write admin/browser tests: toggle/coordinates/timezone save/read-back, CAS conflicts, timeout reconciliation without automatic enabling retry, zero missing token exposure, PIN/CSRF/Origin checks, independent duration/rotation retention and unknown offline status. Test all four rotations and cancellation of a held touch during settings updates.
- [ ] Run `sh scripts/test_admin_dial.sh` and `sh scripts/test_valve_dial.sh` under ESP-IDF 5.5.5; observe new cases FAIL. If toolchain absent, provision it in the execution stage and report the missing prerequisite rather than skipping crypto validation.
- [ ] Implement above interfaces, exact `/admin/api/weather` proxy and narrow credential provisioning. Keep PT100 one decimal, existing shower icon/dots and relay indicator. Display AUTO instead of countdown and explain USER_OFF in admin. Rerun both runners to PASS.
- [ ] Commit Dial changes with `feat(dial): add weather settings and automatic shower display`.

## Task W6: Integration evidence and review handoff

**Files:** create `docs/operations/weather-assisted-shower.md`, `docs/evidence/2026-10-03-weather-plan-validation.md` (record actual execution date when used); update `README.md`, `docs/PROJECT_STATE.md` and relevant deployment guides. No private coordinates/tokens/backups in Git.

**Interfaces:** consumes the exact W1–W5 commit IDs, test outputs and artifact manifest; produces a truthful repository-only implementation record and later deployment procedure.

- [ ] Add executable cross-layer fixtures using the real service/driver paths for AUTO loss, STOP/START revisions, manual expiry and lease refusal; do not substitute a toy policy. Assert old/new client compatibility and clear readback vs physical-evidence boundaries.
- [ ] Run Pi `python -m pytest -q`, `python -m ruff check .`, `python -m mypy src`, `python -m build`; commissioning suite and `sh -n` for any changed shell scripts. Expected PASS; record actual counts/versions, do not reuse historic numbers.
- [ ] Run Dial shared checks from `.github/workflows/docker.yml` job `test-shared`, both admin/valve runners, and `idf.py -C idf_app build` in the recorded ESP-IDF 5.5.5 environment. Do not invoke a combined build-and-flash script. Hash firmware artifacts without claiming them flashed.
- [ ] Document staged operator deployment: backup/verify database and configs, retain manual_timed and weather disabled, deploy compatible Pi/Dial, provision restricted token privately, read back settings, then separately review continuous-duty hardware and fault gaps before enabling weather. Rollback disables weather, confirms DRAIN, stops new stack and restores the protected pre-migration snapshot plus exact v1.1.0 artifacts. No automated restore command against a running database.
- [ ] Run Python Engineering Guardrails preflight and emit READY_FOR_INDEPENDENT_REVIEW or NOT_READY with exact evidence. Independently review pinned revisions according to the selected execution method; fix material findings and rerun affected gates. Commit `docs: document weather operation and verification boundaries`. Do not merge/release/deploy without the appropriate later authorization.

## Physical fault record carried into deployment

| Fault | Required behavior / surviving mechanism | Unresolved hardware evidence |
| --- | --- | --- |
| Provider or Dial communication loss | local weather/manual policy and expiry; no replay | New-mode timing needs runtime observation |
| Hub crash/hang | daemon lease requests DRAIN within 60 s while daemon runs | Daemon crash/hang needs independent enforcement proof |
| Pi reboot | startup DRAIN, durable inhibition/recovery checks | Pre-application GPIO and valve timing |
| Pi, relay supply or valve 24 V power loss/restoration | required DRAIN per each power domain | Passive hydraulic return, response time and restoration behavior |

Legal outputs remain high/high or low/low. Tests of Python or GPIO do not prove valve position. Continuous-duty suitability and the unresolved physical boundaries prevent automatic live enablement, not repository implementation.
