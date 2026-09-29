# Manual Timed Pi Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Pi accept one authenticated ten-minute `SUPPLY` request and otherwise command the paired relays to `DRAIN` in the explicitly selected manual mode.

**Architecture:** Add an operating mode at process construction and guard every service path that could invoke automatic policy. Extend the existing display API with a small status contract for the dial. Leave the paired GPIO daemon and its 60-second lease in place.

**Tech Stack:** Python 3.12, FastAPI, pytest, Ruff, existing Node-RED and paired GPIO daemon.

**Spec:** `docs/superpowers/specs/2026-09-29-waveshare-roon-valve-control-design.md`

## Global Constraints

- `DRAIN = 0`: both relays released; BCM 26/20 high/high. `SUPPLY = 1`: both relays energized; BCM 26/20 low/low.
- Only a deliberate authenticated dial action may start `SUPPLY` in `manual_timed`; interval is exactly 600 monotonic seconds. Duplicate POSTs do not extend it.
- Absent or invalid operating mode is safe drain and refuses `SUPPLY`. No weather or sensor input may start `SUPPLY` in `manual_timed`.
- The Hub retains its loopback Node-RED boundary; Nginx exposes only the three existing display routes on the trusted LAN. Keep the daemon's 60-second `SUPPLY` lease.
- Keep 24 V disconnected. No live `SUPPLY`, GPIO, relay, Pi deployment, or physical-valve test during implementation without a separate bounded approval under `AGENTS.md`.

## Review Focus

1. A duplicate request just before the deadline must not extend it, and the first request at expiry must close the old interval; test the monotonic boundary in Task 2.
2. Updating settings during active manual `SUPPLY` must neither run automatic policy nor extend the deadline; test it in Task 2.
3. An invalid mode value must fail closed even if weather says supply; test it in Task 1.
4. A status request at expiry must not report active `SUPPLY` with zero remaining time; test it in Task 3.
5. A malformed or absent display token must never return status or actuate; test it in Task 3.

## File structure and contract

Pi repository paths below are relative to this repository. Add `ControlMode` to `domain/models.py` with `SAFE_DRAIN`, `MANUAL_TIMED`, and `AUTOMATIC`; add `MANUAL_DRAIN` and `SAFE_DRAIN` to `ControllerState`. A pure `parse_control_mode()` in that module parses `FREEZE_PROTECT_CONTROL_MODE` (`manual_timed` or `automatic`; anything else means safe drain); `main.py` passes it to the app. `ControlService` owns the mode, deadlines, transitions, and reported command. `api/app.py` maps the service to the existing display routes. Do not introduce a new relay route or a dial-supplied duration. Existing automatic tests must construct `AUTOMATIC` explicitly; the default is safe drain.

The display status JSON adds `mode` (`manual_timed`, `automatic`, `safe_drain`), `command` (`DRAIN` or `SUPPLY`), and `remaining_seconds` (integer 0..600 in manual mode; zero while idle). Keep current fields for the CrowPanel until its token is retired. `command` is the accepted software command/paired receipt, not physical valve position. The action POST response keeps `state`, `command`, and `reason`.

### Task 1: Mode selection and safe startup

**Files:** Modify `src/freeze_protect/domain/models.py`, `src/freeze_protect/main.py`, `src/freeze_protect/api/app.py`, `src/freeze_protect/application/service.py`, `deployment/freeze-protect.env.example`; test `tests/unit/test_m1_service.py`, `tests/integration/test_m1_api.py`.

**Interfaces:** `ControlMode(str, Enum)` values `SAFE_DRAIN="safe_drain"`, `MANUAL_TIMED="manual_timed"`, `AUTOMATIC="automatic"`; `parse_control_mode(value: str | None) -> ControlMode` in `domain/models.py`; `create_app(..., *, control_mode: ControlMode = ControlMode.SAFE_DRAIN, ...)`; `ControlService(..., mode: ControlMode = ControlMode.SAFE_DRAIN, ...)`; read-only `ControlService.mode: ControlMode`.

- [ ] **Step 1: Write failing tests.** In `test_m1_service.py`, assert default and invalid parsed mode yield `SAFE_DRAIN`; assert `startup()` sends only `DRAIN`, produces `SAFE_DRAIN` or `MANUAL_DRAIN`, and never calls a forecast or temperature port when constructed in those modes. Test an eligible warm forecast still cannot cause `SUPPLY` in manual mode. Update existing automatic-policy fixtures to pass `mode=ControlMode.AUTOMATIC` explicitly.
- [ ] **Step 2: Run the focused tests.** `python -m pytest -q tests/unit/test_m1_service.py tests/integration/test_m1_api.py`; expect the new cases to fail before implementation.
- [ ] **Step 3: Implement the interfaces.** Route startup, idle `run_cycle`, `drain`, `clear_fault`, `update_settings`, `refresh_forecast`, and `status` through explicit mode guards. In manual/safe modes, idle transitions command DRAIN and avoid sensor/forecast reads and fetches. Preserve existing automatic behavior only under `AUTOMATIC`. Expose `FREEZE_PROTECT_CONTROL_MODE=manual_timed` in the example, with an explicit warning that unset/invalid means safe drain.
- [ ] **Step 4: Verify.** Run the focused tests; expect pass. Run `python -m ruff check src/freeze_protect tests` and fix findings.
- [ ] **Step 5: Commit.** `git add src/freeze_protect/domain/models.py src/freeze_protect/main.py src/freeze_protect/api/app.py src/freeze_protect/application/service.py deployment/freeze-protect.env.example tests/unit/test_m1_service.py tests/integration/test_m1_api.py && git commit -m "feat: add fail closed manual control mode"`.

### Task 2: Fixed manual interval and failure transitions

**Files:** Modify `src/freeze_protect/application/service.py`; test `tests/unit/test_m1_service.py`, `tests/unit/test_periodic_loop.py`, `tests/integration/test_paired_gpio_daemon.py` as needed.

**Interfaces:** `ControlService.start_timed_shower() -> Decision`, `drain(reason: str = "drain_requested") -> Decision`, `seconds_until_timed_shower_expiry() -> float | None`. In `MANUAL_TIMED`, duration is a fixed 600 seconds, independent of admin default duration. If the configured maximum is below 600 seconds, refuse SUPPLY with `manual_duration_exceeds_settings_limit`; settings cannot lengthen the interval. In `SAFE_DRAIN`, start returns a DRAIN decision with reason `operating_mode_not_configured` (API maps it to 409). The existing `AUTOMATIC` path retains its current settings-based duration for compatibility.

- [ ] **Step 1: Write failing tests.** Cover manual start from `MANUAL_DRAIN`, changed admin default with maximum at least 600 still yielding 600 seconds, maximum below 600 refusing SUPPLY, duplicate requests at 500 seconds leaving 100 seconds, `run_cycle()` renewals only before expiry, expiry to `MANUAL_DRAIN`, manual `drain()` during active interval, restart clearing a previous interval, and failure cases (driver receipt error, event persistence error, safe mode). Add the Review Focus cases: settings update during an interval keeps the original deadline, and a POST at the exact expired boundary first closes the prior interval and returns DRAIN; a later deliberate press may start a new interval. Keep the existing daemon lease-expiry test and assert it still enforces 60 seconds.
- [ ] **Step 2: Run the focused tests.** `python -m pytest -q tests/unit/test_m1_service.py tests/unit/test_periodic_loop.py tests/integration/test_paired_gpio_daemon.py`; expect new tests to fail.
- [ ] **Step 3: Implement transitions.** Use the existing monotonic clock and forced paired writes. Check expiry before the duplicate branch, return the expired DRAIN decision for that request, and clear both deadlines on DRAIN, fault, and restart. Idle manual state stays `MANUAL_DRAIN`; never fall through to `_run_automatic()`. Retain one-shot `SUPPLY` writes and the current DRAIN retry behavior. The 30-second loop may renew only an active interval; its expiry wake remains exact.
- [ ] **Step 4: Verify.** Rerun the focused tests and Ruff; expect pass.
- [ ] **Step 5: Commit.** `git add src/freeze_protect/application/service.py tests/unit/test_m1_service.py tests/unit/test_periodic_loop.py tests/integration/test_paired_gpio_daemon.py && git commit -m "feat: enforce ten minute manual supply lease"`.

### Task 3: Dial-facing status and authorization

**Files:** Modify `src/freeze_protect/application/service.py`, `src/freeze_protect/api/app.py`, `tests/integration/test_m1_api.py`; add API contract example in `README.md`.

**Interfaces:** `ControlStatus` adds `mode: ControlMode`, `command: ActuatorCommand`, `remaining_seconds: int`. `ControlService.status() -> ControlStatus` computes remaining seconds from the monotonic deadline using ceiling, clamps to 0..600 in manual mode, and closes an expired interval before returning. `GET /api/v1/display/status` returns the three JSON fields defined above. `POST /api/v1/display/actions/timed-shower` returns HTTP 409 when no `SUPPLY` decision was accepted; no request body is accepted.

- [ ] **Step 1: Write failing API tests.** Assert idle/manual JSON is `mode=manual_timed`, `command=DRAIN`, `remaining_seconds=0`; after a start it is `SUPPLY` with at most 600 remaining; duplicate POST leaves deadline unchanged; status at expiry reports DRAIN; safe mode POST gives 409 and no SUPPLY; DRAIN POST gives DRAIN. Assert 401 for absent, admin, and malformed display tokens on all three display routes; unexpected POST JSON fields produce HTTP 400 and no actuation. Preserve minimal status: no admin token, sensor diagnostics, or secret values.
- [ ] **Step 2: Run focused API tests.** `python -m pytest -q tests/integration/test_m1_api.py`; expect new cases to fail.
- [ ] **Step 3: Implement status/API mapping.** Keep the three current Nginx paths and `X-Display-Token` guard. Reject nonempty action request bodies with HTTP 400 before calling the service. In safe drain, report `action_enabled=false`; in manual mode, allow `SUPPLY` only from idle with no fault. Update the response without exposing raw receipt or GPIO diagnostics. Add a short request/response example in `README.md` with placeholder tokens only.
- [ ] **Step 4: Verify.** Run focused API tests and Ruff; expect pass.
- [ ] **Step 5: Commit.** `git add src/freeze_protect/application/service.py src/freeze_protect/api/app.py tests/integration/test_m1_api.py README.md && git commit -m "feat: report manual valve status to dial"`.

### Task 4: Release gate and commissioning instructions

**Files:** Modify `deployment/freeze-protect.env.example`, `deployment/CROWPANEL_COMMISSIONING.md`, `docs/PROJECT_STATE.md`; test `tests/integration/test_node_red_flow.py` and existing Nginx allowlist tests.

**Interfaces:** No new runtime interface. Deployment procedure sets `FREEZE_PROTECT_CONTROL_MODE=manual_timed`, rotates `FREEZE_PROTECT_DISPLAY_TOKEN`, provisions only the Waveshare dial, and removes the CrowPanel copy. Existing Nginx allowlist remains exactly GET status and POST timed-shower/drain.

- [ ] **Step 1: Write or update integration assertions.** Assert the Nginx file still contains only the three display routes; assert the deployment example names `manual_timed` and keeps admin, display, and Node-RED tokens distinct. Run the relevant tests before editing to see any new assertion fail.
- [ ] **Step 2: Update the runbook.** Document token rotation and CrowPanel retirement, 24 V disconnected software/GPIO validation, both-pin readback, and a separate approval gate for a live valve test. In `docs/PROJECT_STATE.md`, record implementation/test evidence only after verification, without claiming deployment or physical behavior.
- [ ] **Step 3: Run repository gates.** `python -m pytest -q` and `python -m ruff check .`; expect pass. Do not issue real actuator commands from tests. Review `git diff --check` and the final diff.
- [ ] **Step 4: Commit.** `git add deployment/freeze-protect.env.example deployment/CROWPANEL_COMMISSIONING.md docs/PROJECT_STATE.md tests && git commit -m "docs: document manual dial commissioning boundary"`.

The Pi plan is independently testable with simulated adapters. Hardware observations and deployed mode/token values remain a later commissioning step.
