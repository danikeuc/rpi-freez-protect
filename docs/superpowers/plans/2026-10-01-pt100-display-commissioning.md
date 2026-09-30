# PT100 Display Integration and Commissioning Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy and verify the Pi telemetry and Waveshare display changes against the real PT100/MAX31865 while keeping the valve supply disconnected, the controller in `manual_timed`, and both outputs at requested `DRAIN`.

**Architecture:** Commission the two independently verified software artifacts in layers: record baseline, deploy Pi, verify sensor/API, flash the exact firmware, verify the shower-only UI, then record evidence and rollback readiness. The restricted SSH helper is used only for its fixed read-only/status commands; deployment and SPI inspection remain trusted-console work.

**Tech Stack:** DietPi/systemd, Linux spidev, MAX31865/PT100, FastAPI/Nginx, restricted OpenSSH commissioning helper, ESP-IDF 5.5.5, Waveshare ESP32-S3 dial.

**Spec:** [`docs/superpowers/specs/2026-10-01-waveshare-pt100-telemetry-design.md`](../specs/2026-10-01-waveshare-pt100-telemetry-design.md)

## Global Constraints

- Follow `AGENTS.md`, `deployment/WORKSTATION_CODEX_COMMISSIONING.md`, and `deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md` before any network, deployment, service, GPIO, or flash action.
- Keep the 24 V valve supply physically disconnected for the entire plan. Do not issue `SUPPLY` and do not use the timed-shower endpoint.
- Keep `FREEZE_PROTECT_CONTROL_MODE=manual_timed`; do not set `sensor_commissioned=true`.
- `DRAIN` is the requested high/high output state: GPIO 26 high and GPIO 20 high. GPIO readback does not prove relay contacts, valve position, or water routing.
- Stop on any failed service, receipt, preflight, SPI, or paired GPIO check. Leave requested `DRAIN`; do not retry by issuing `SUPPLY`.
- Never place the admin/display/Node-RED tokens in Git, command history, URLs, screenshots, serial captures, or evidence files.
- Resolve `<PI_FEATURE_SHA>`, `<DIAL_FEATURE_SHA>`, `<PI_PREVIOUS_SHA>`, `<DIAL_ARTIFACT_SHA256>`, and `<DIAL_PORT>` before execution and record them in the evidence. Do not deploy a branch name without an exact commit.
- The four actuator fault-injection outcomes remain `NOT_VERIFIED`. This plan verifies sensor telemetry and display only.

## Review Focus

- Verify the physical wiring matches the exact breakout, 3-wire PT100, 430-ohm reference, SPI0 CE0, mode 1, and 500 kHz contract before powering the logic side.
- Verify failed/disconnected sensor cases remove the numeric value from both JSON and dial within the 15-second stale bound.
- Verify Pi deployment does not change `manual_timed`, Nginx exposure, Node-RED ownership, paired GPIO behavior, or secrets.
- Verify the firmware binary flashed is byte-identical to the artifact whose source commit and SHA were reviewed.
- Keep software status, GPIO level, relay contact, valve position, and hydraulic path as separate evidence layers.

---

### Task 1: Freeze exact artifacts and rollback points

**Files:**

- Update after execution: `docs/PROJECT_STATE.md`
- Update after execution: `docs/evidence/<YYYY-MM-DD>-pt100-display-commissioning.md`
- Update after execution in firmware repo: `/mnt/c/users/danik/projects/roon-knob-valves/docs/valve-dial-commissioning.md`

- [ ] **Step 1: Require green repository evidence.** Pi: `python -m pytest -q`, `python -m ruff check .`, `python -m mypy src`, `python -m build`, and `git diff --check`. Dial: `PATH=/tmp/knob-bin:$PATH ./scripts/test_valve_dial.sh`, `bash /tmp/knob-idf-build.sh`, and `git diff --check` under ESP-IDF 5.5.5.
- [ ] **Step 2: Record exact candidate identities.** Capture `git rev-parse HEAD` and clean `git status --short --branch` in both repositories. Hash `idf_app/build/hiphi_dial.bin` and record its size. Set those results as `<PI_FEATURE_SHA>`, `<DIAL_FEATURE_SHA>`, and `<DIAL_ARTIFACT_SHA256>`.
- [ ] **Step 3: Preserve rollback artifacts.** Keep Pi's installed pre-deploy SHA as `<PI_PREVIOUS_SHA>`. Preserve the immutable dial release `v2.5.3-valve.1` and its published image/SHA as the firmware rollback. Do not overwrite either release artifact.

### Task 2: Record the disconnected Pi baseline

**Files:** Evidence only.

- [ ] **Step 1: Confirm the physical stop gate.** At the installation, visually confirm the 24 V valve supply is disconnected. Record that observation without inferring relay or valve position.
- [ ] **Step 2: Run the fixed restricted checks from the workstation.** Use the dedicated key and exact commands documented in `deployment/WORKSTATION_CODEX_COMMISSIONING.md`: `inventory`, `status`, and `diagnose-pair-gpio`. Do not widen the helper or open a shell through the commissioning account.
- [ ] **Step 3: Require the baseline.** Record the installed SHA, `FREEZE_PROTECT_CONTROL_MODE=manual_timed` without printing the environment file, active `freeze-protect.service`, `node-red.service`, and `freeze-protect-pair-gpio.service`, inactive legacy `nodered.service`, loopback-only ports, preflight exit zero, and GPIO 26/20 output-high.
- [ ] **Step 4: Inspect sensor prerequisites at the trusted Pi console.** Run `ls -l /dev/spidev0.0`, `getent group spi`, `id freezeprotect`, `systemctl cat freeze-protect.service`, and `pinctrl get 26 20` if supported, otherwise query each pin separately. Require `/dev/spidev0.0`, `freezeprotect` access through the `spi` group, and unchanged high/high outputs.
- [ ] **Step 5: Verify the exact breakout before wiring.** Record both module sides, the `4300` reference marking or measured 430-ohm equivalent, three-wire jumper/terminal arrangement, valid 3.3 V input labeling, input filter timing, and the required disconnected-lead safeguard. Stop if any item cannot be established.

### Task 3: Deploy the exact Pi feature at the trusted console

**Files:** Installed Pi checkout and service environment; no token output.

- [ ] **Step 1: Reassert requested DRAIN and stop the Hub.** Run the documented fixed `drain` helper, require JSON `ok=true` with both GPIO values at the DRAIN level, then stop only `freeze-protect.service` at the trusted console. Recheck GPIO 26/20 are output-high.
- [ ] **Step 2: Move the root-owned checkout to the exact reviewed commit.** At the trusted console, fetch the reviewed remote, verify `<PI_FEATURE_SHA>` exists, then run `sudo git -C /opt/rpi-freez-protect checkout --detach <PI_FEATURE_SHA>`. Record `sudo git -C /opt/rpi-freez-protect rev-parse HEAD` and a clean status. Do not merge on the Pi.
- [ ] **Step 3: Refresh the existing virtual environment without exposing configuration.** Run `sudo /opt/rpi-freez-protect/.venv/bin/pip install --no-deps --force-reinstall /opt/rpi-freez-protect`. Do not recreate or print `/etc/rpi-freeze-protect/environment`.
- [ ] **Step 4: Confirm mode and unit contract.** Use a bounded `grep '^FREEZE_PROTECT_CONTROL_MODE=' /etc/rpi-freeze-protect/environment` at the trusted console and require exactly `manual_timed`. Reinstall the reviewed systemd unit only if its hash differs, then run `sudo systemctl daemon-reload`.
- [ ] **Step 5: Start and gate the service.** Run `sudo systemctl start freeze-protect.service`; require active state, `curl -fsS http://127.0.0.1:8000/health`, paired daemon active, Node-RED active, legacy service inactive, deployed-flow preflight exit zero, and GPIO 26/20 output-high. Stop and roll back if any gate fails.

### Task 4: Commission display-only PT100 telemetry

**Files:** Evidence only; do not change automatic-mode settings.

- [ ] **Step 1: Connect only the verified low-voltage sensor wiring.** With valve 24 V still disconnected, connect MAX31865 power, ground, SPI0 MOSI/MISO/SCLK/CE0, and the three-wire PT100 exactly as recorded in the approved hardware contract.
- [ ] **Step 2: Read authenticated display JSON without recording the token.** At the trusted console use a silent prompt such as `read -rsp 'Display token: ' FP_DISPLAY_TOKEN; echo`, then `curl -fsS -H "X-Display-Token: $FP_DISPLAY_TOKEN" http://127.0.0.1:8000/api/v1/display/status | python3 -m json.tool`, followed by `unset FP_DISPLAY_TOKEN`. Evidence records only the redacted response fields.
- [ ] **Step 3: Require the API contract.** Confirm all manual valve fields remain `manual_timed`, `MANUAL_DRAIN`, `DRAIN`, zero remaining seconds, and action enabled; confirm `pipe_temperature_c` is numeric and `sensor_health` is `HEALTHY`. Confirm admin diagnostics and token values are absent.
- [ ] **Step 4: Compare stable readings.** Record at least three settled room-temperature readings against an independent reference, then repeat around 0 °C and 8..10 °C using the existing PT100 commissioning method. Record uncertainty and stabilization time; do not infer calibration from one point.
- [ ] **Step 5: Exercise sensor-only fault cases.** One at a time, with logic power handled safely, disconnect each PT100 lead and the permitted representative MAX31865 fault arrangements. For each, require the API numeric value to become null immediately on a failed sample or no later than the 15-second stale threshold, with an allowed non-healthy enum. Restore wiring and require a new healthy sample before the next case.
- [ ] **Step 6: Recheck control isolation after every case.** Require service active, mode unchanged, GPIO 26/20 still output-high, no timed shower deadline, and no new `SUPPLY` command evidence.

### Task 5: Flash and visually verify the exact Waveshare candidate

**Files:** Firmware artifact and evidence only.

- [ ] **Step 1: Identify the dial port by disconnect/reconnect.** Record the exact USB device that disappears and returns; set it as `<DIAL_PORT>`. Do not guess from a stale port listing.
- [ ] **Step 2: Recheck artifact identity immediately before flash.** Require clean firmware source at `<DIAL_FEATURE_SHA>` and `sha256sum idf_app/build/hiphi_dial.bin` equal to `<DIAL_ARTIFACT_SHA256>`.
- [ ] **Step 3: Flash the reviewed image.** Use the ESP-IDF 5.5.5 environment and the repository's documented flash path for `<DIAL_PORT>`. Do not alter Wi-Fi/Pi credentials in logs or screenshots, and do not use upstream OTA for this custom valve firmware.
- [ ] **Step 4: Verify boot and connectivity.** Capture a redacted bounded serial boot observation, require no panic/abort/brownout/stack-overflow markers, confirm the dial HTTP root responds, Roon reconnects, and Pi polling resumes.
- [ ] **Step 5: Verify presentation.** On the shower page require the small upper-left value with one decimal and comma, for example `6,4 °C`. Swipe to Roon and require no temperature element. Return to shower and require the same current value.
- [ ] **Step 6: Verify fallback without valve actuation.** Repeat a safe PT100 lead-disconnect case and require the dial to show exactly `---` within the API stale bound. Restore the sensor and require a fresh numeric value. Confirm the shower icon, snowflake/water dots, relay status icon, and action control remain driven only by valve status.
- [ ] **Step 7: Run non-actuating regressions.** Verify page switching, Roon play/pause/next/volume behavior, Pi disconnect/reconnect, `FAULT / Status unavailable`, and recovery. Do not hold the valve action button for two seconds and do not call either action endpoint.

### Task 6: Close evidence and prove rollback readiness

**Files:**

- Modify: `docs/PROJECT_STATE.md`
- Create: `docs/evidence/<YYYY-MM-DD>-pt100-display-commissioning.md`
- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/docs/valve-dial-commissioning.md`

- [ ] **Step 1: Leave the system in the bounded state.** Require `manual_timed`, `MANUAL_DRAIN`, `DRAIN`, zero remaining seconds, healthy services, and GPIO 26/20 output-high. Keep 24 V valve power disconnected.
- [ ] **Step 2: Record evidence layers separately.** Record exact Pi/dial SHAs, firmware hash, test outputs, SPI permissions, sensor comparisons, fault cases, authenticated redacted JSON, serial result, and visual UI results. State that GPIO readback does not prove relay contacts, valve position, or water routing.
- [ ] **Step 3: Keep unresolved gates explicit.** Mark energized relay/valve tests, process crash/hang physical outcome, reboot physical outcome, and power-loss restoration physical outcome as `NOT_VERIFIED` unless separately performed under a new bounded approval.
- [ ] **Step 4: Document rollback commands without executing them.** Pi rollback is detached checkout of `<PI_PREVIOUS_SHA>`, reinstall into the same venv, service restart, health/preflight/high-high verification. Dial rollback is the published `v2.5.3-valve.1` artifact followed by boot, Roon, Pi connectivity, and DRAIN display verification.
- [ ] **Step 5: Review and commit only truthful evidence.** Run Markdown/link tests, repository gates, and `git diff --check`. Commit the Pi evidence separately from firmware evidence. Do not merge either PR or create a release tag until the user reviews the exact artifacts and explicitly approves that action.
