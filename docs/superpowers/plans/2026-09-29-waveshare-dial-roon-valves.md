# Waveshare Dial Roon and Valves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a valve page to a Waveshare ESP32-S3 Knob so horizontal swipes switch between Roon and paired-valve control, with a deliberate two-second `SUPPLY` hold.

**Architecture:** Fork `muness/roon-knob` and keep its Roon bridge client. Add a target-specific Pi HTTP client, a small valve state machine, and an LVGL overlay on the Dial target. The Pi remains authoritative for relay state and the ten-minute deadline. Turn off the upstream firmware update path for this custom image.

**Tech Stack:** ESP-IDF 5.5.5 target profile, C11, LVGL 9, ESP HTTP client, NVS, a host C test harness. Pi contract from the companion plan.

**Spec:** `docs/superpowers/specs/2026-09-29-waveshare-roon-valve-control-design.md` in `rpi-freez-protect`; companion Pi plan: `docs/superpowers/plans/2026-09-29-manual-timed-pi-control.md`.

## Global Constraints

- Hardware target is the Waveshare ESP32-S3 Knob 1.8-inch touch LCD; preserve existing Roon encoder, tap, zone picker, settings, sleep/wake, and vertical art-mode behavior.
- Left or right swipe switches between the Roon and valve main screens. Suppress navigation in zone picker, settings, and art mode. A swipe must never click a valve action.
- `DRAIN = 0`, `SUPPLY = 1`; the dial has no pin-level access. `SUPPLY` requires a continuous 2,000 ms touch; `DRAIN` is one touch. No automatic start, request replay, offline queue, or client-side deadline.
- Use `X-Display-Token` with the three Pi routes: GET `/api/v1/display/status`, POST `/api/v1/display/actions/timed-shower`, POST `/api/v1/display/actions/drain`. A fresh manual-mode DRAIN status is required before enabling a new `SUPPLY` hold.
- Show `UNKNOWN/FAULT` on stale status, timeout, malformed response, or uncertain POST. Fetch Pi status on entry, after action, on wake, and periodically while awake. The Pi reports `remaining_seconds` in 0..600.
- No tokens in Git, logs, URL query strings, or rendered settings; keep the current Roon bridge unchanged. Hardware flashing and live actuator verification are separately gated by both repositories' instructions.

## Review Focus

1. A swipe beginning on `DRAIN` must not emit a DRAIN POST; test gesture consumption and widget click ordering in Task 3.
2. A touch interrupted at 1,999 ms must not emit `SUPPLY`; test hold cancellation in Task 3.
3. A 200 response with missing/contradictory fields must become `UNKNOWN`, not `SUPPLY`; test parser validation in Task 2.
4. Wi-Fi reconnection after an ambiguous POST must fetch status without replaying the POST; test request state in Task 2.
5. A configuration page response or log must not disclose the display token; test the new provisioning path in Task 1.

## File structure and contract

Paths in Tasks 1-4 are relative to a maintained fork/checkout of `muness/roon-knob`, not this Pi repository. Obtain the fork and exact base SHA before edits; read its `AGENTS.md`, inspect open issues, and use its approved issue/PR workflow. The upstream paths below were verified on its current `master`, but recheck them against the chosen SHA before executing.

Use a separate NVS namespace for the Pi endpoint and token; do not change the v3 `rk_cfg_t` blob or remote bridge configuration. Add `idf_app/main/valve_config_dial.{h,c}` for storage and `idf_app/main/valve_client_dial.{h,c}` for HTTP. Put pure state and gesture decisions in `idf_app/main/valve_logic.{h,c}` so the host harness can test them without ESP-IDF. Add `idf_app/main/valve_ui_dial.{h,c}` for LVGL only. The Roon page remains the existing `common/ui.c` page; an LVGL overlay hides it while valve view is selected. Add a small indicator through `common/ui.h`/`common/ui.c`. Compile Dial-only sources through `idf_app/main/CMakeLists.txt`; do not add valve behavior to Frame.

The firmware consumes the Pi JSON fields `mode`, `state`, `command`, `reason`, `remaining_seconds`. It recognizes only `mode=manual_timed`; `state=MANUAL_DRAIN` with `command=DRAIN` means ready, `state=TIMED_SHOWER` with `command=SUPPLY` means active, and any `FAULT`, `SAFE_DRAIN`, unknown value, or contradiction means `UNKNOWN/FAULT`. Numeric countdown is display-only and must be corrected by every Pi poll.

### Task 1: Local Pi endpoint and token provisioning

**Files:** Create `idf_app/main/valve_config_dial.h`, `idf_app/main/valve_config_dial.c`; modify `idf_app/main/config_server.c`, `idf_app/main/CMakeLists.txt`; test `tests/valve_dial/test_valve_config.c` and `scripts/test_valve_dial.sh`.

**Interfaces:** `bool valve_config_load(char *base_url, size_t url_len, char *token, size_t token_len)`, `bool valve_config_save(const char *base_url, const char *token)`, and `bool valve_config_clear(void)`; NVS namespace `valve_cfg`, keys `pi_url` and `pi_token`. The URL is the Pi LAN base, such as `http://<pi-lan-ip>:8081`; accept only `http://` with no userinfo, query, fragment, or path. Token is nonempty and bounded to 128 bytes. Blank or corrupted storage disables valve actions.

- [ ] **Step 1: Write failing tests.** Cover empty/corrupt storage, overlong URL/token, invalid URL, a valid round trip, and clearing the config. Add a source/handler assertion that GET HTML contains no token value, POST handling never logs the body, and old `/config` logging cannot receive the new token field.
- [ ] **Step 2: Run host tests.** `./scripts/test_valve_dial.sh`; expect the new config cases to fail. The script compiles pure validation tests with `cc -std=c11 -Wall -Wextra -Werror` and uses an NVS fake for storage tests.
- [ ] **Step 3: Implement storage and provisioning.** Add a separate `/valves-config` form/handler to the existing local config server, with password input left blank on GET, no token echo in success or error, no request-body logging, and a clear action. Call `valve_config_save` only after validation and verified NVS commit/readback. Do not route this form through the existing `/config` handler, which logs its received body. Respect the HTTP server's route limit.
- [ ] **Step 4: Verify.** Run host tests and `idf.py -C idf_app build` in the documented ESP-IDF 5.5.5 environment; expect pass.
- [ ] **Step 5: Commit.** `git add idf_app/main/valve_config_dial.h idf_app/main/valve_config_dial.c idf_app/main/config_server.c idf_app/main/CMakeLists.txt tests/valve_dial/test_valve_config.c scripts/test_valve_dial.sh && git commit -m "feat(dial): provision Pi valve endpoint locally"`.

### Task 2: Strict Pi client and status state

**Files:** Create `idf_app/main/valve_client_dial.h`, `idf_app/main/valve_client_dial.c`, `idf_app/main/valve_logic.h`, `idf_app/main/valve_logic.c`, `idf_app/main/third_party/jsmn.h` (retain its license); modify `idf_app/main/CMakeLists.txt`, `scripts/test_valve_dial.sh`; test `tests/valve_dial/test_valve_logic.c` and a mock Pi HTTP fixture.

**Interfaces:** `valve_state_t` is `VALVE_UNKNOWN`, `VALVE_DRAIN`, or `VALVE_SUPPLY`; `valve_status_t` contains state, `uint16_t remaining_seconds`, and a bounded reason. `bool valve_status_parse(const char *json, size_t len, valve_status_t *out)` validates exact combinations above and 0..600. `valve_client_get_status(valve_status_t *out)` and `valve_client_post(valve_action_t action, valve_status_t *out)` return a result enum (`OK`, `UNAUTHORIZED`, `UNAVAILABLE`, `INVALID`) rather than pretending a timeout is a drain. `valve_action_t` has only `START_600S` and `DRAIN`.

- [ ] **Step 1: Write failing tests.** Cover all valid statuses, missing/contradictory mode/state/command/remaining, negative or >600 remaining, truncated and oversized JSON, HTTP 401/409/500, timeout, and a successful action followed by a status GET. Assert one POST per explicit UI action, zero automatic POSTs after reconnect, and no credentials in logs or URLs.
- [ ] **Step 2: Run tests.** `./scripts/test_valve_dial.sh`; expect new parser/request tests to fail.
- [ ] **Step 3: Implement client.** Use a bounded JSON tokenizer shared with the host tests for strict status parsing. Use ESP HTTP client only on a worker task, with `X-Display-Token`, a 3-second timeout, bounded 2 KiB response, exact route/method selection, and no automatic POST retry. Poll GET on reconnect and after an ambiguous POST. Use the Pi's `remaining_seconds` as the countdown source; local time merely animates between polls and never authorizes a command.
- [ ] **Step 4: Verify.** Run host tests and `idf.py -C idf_app build`; expect pass.
- [ ] **Step 5: Commit.** `git add idf_app/main/valve_client_dial.h idf_app/main/valve_client_dial.c idf_app/main/valve_logic.h idf_app/main/valve_logic.c idf_app/main/third_party/jsmn.h idf_app/main/CMakeLists.txt scripts/test_valve_dial.sh tests/valve_dial && git commit -m "feat(dial): add authenticated Pi valve client"`.

### Task 3: Swipe navigation and valve page

**Files:** Create `idf_app/main/valve_ui_dial.h`, `idf_app/main/valve_ui_dial.c`; modify `idf_app/main/platform_display_idf.c`, `idf_app/main/main_idf.c`, `idf_app/main/CMakeLists.txt`, `common/ui.h`, `common/ui.c`, `idf_app/main/valve_logic.{h,c}`; test `tests/valve_dial/test_valve_logic.c`.

**Interfaces:** `valve_ui_show(bool visible)`, `valve_ui_set_status(const valve_status_t *status)`, and `valve_ui_set_unknown(const char *reason)` run on the LVGL/UI task; HTTP completion posts a message into that task. `valve_gesture_classify(dx, dy, elapsed_ms, rotation, context)` returns `NONE`, `SWITCH_SCREEN`, `ART_UP`, or `ART_DOWN`; only dominant horizontal movement of at least 60 px within 500 ms switches screen. `valve_hold_update(pressed, moved, now_ms)` emits `START_600S` only after uninterrupted 2,000 ms on the labeled control.

- [ ] **Step 1: Write failing logic tests.** Cover left/right swipes at both 0° and 180°, vertical art swipes, diagonals, zone picker/settings/art suppression, wake touch, swipe beginning on either valve control, 1,999 ms release, motion cancellation, exactly 2,000 ms hold, and one-tap DRAIN. Assert no SUPPLY action when displayed status is stale, unknown, or active SUPPLY; DRAIN remains available. Assert Roon encoder/tap actions remain routed only on the Roon page.
- [ ] **Step 2: Run host tests.** `./scripts/test_valve_dial.sh`; expect new cases to fail.
- [ ] **Step 3: Implement UI and input.** Intercept a recognized swipe in `platform_display_idf.c` before LVGL can deliver a click; defer page change to `platform_display_process_pending()`. Keep existing up/down art gesture logic. Create a full-screen valve overlay on `lv_screen_active()`; hide it for Roon. On valve entry and wake, request GET only. While awake poll at a fixed 5-second interval; stale after 10 seconds without a valid response. `SUPPLY` button enables only on a fresh `MANUAL_DRAIN` status, requires continuous hold, and sends one POST. `DRAIN` sends one POST on touch. After any POST, show pending/unknown until a fresh GET confirms status. Add a small Roon indicator for a fresh active timed interval.
- [ ] **Step 4: Verify.** Run host tests and `idf.py -C idf_app build`; use the PC simulator if it includes the modified shared UI. Record build SHA and any unavailable hardware gate separately; build success alone is not physical validation.
- [ ] **Step 5: Commit.** `git add idf_app/main/valve_ui_dial.h idf_app/main/valve_ui_dial.c idf_app/main/platform_display_idf.c idf_app/main/main_idf.c idf_app/main/CMakeLists.txt idf_app/main/valve_logic.h idf_app/main/valve_logic.c common/ui.h common/ui.c tests/valve_dial && git commit -m "feat(dial): switch Roon and valve pages by swipe"`.

### Task 4: Controlled firmware update and integration gate

**Files:** Modify `idf_app/main/main_idf.c`, `idf_app/main/ui_network.c`, `idf_app/main/ota_update.c` or their call sites, `docs/dev/DEVELOPMENT.md`; add `docs/valve-dial-commissioning.md` in the fork. In the `danikeuc/roon-control` deployment configuration, set `FIRMWARE_AUTO_UPDATE=false` without committing secrets.

**Interfaces:** Custom valve firmware never invokes `ota_check_for_update()` or `ota_start_update()` against the bridge's upstream feed and hides/disables its update button until a controlled custom feed exists. Roon bridge control remains unchanged.

- [ ] **Step 1: Write a build/source gate.** Add an assertion in the Dial test script that the custom target has no reachable bridge OTA check or update UI action; inspect existing call sites before modifying. Verify `roon-control` currently defaults `FIRMWARE_AUTO_UPDATE=true` and record where the deployed override is set.
- [ ] **Step 2: Implement the update guard.** Disable upstream OTA in the custom build, document how a future signed/controlled custom update could be added, and set the bridge deployment flag false. Keep the bridge's Roon endpoints untouched.
- [ ] **Step 3: Run integration verification.** Run `./scripts/test_valve_dial.sh`, `idf.py -C idf_app build`, and a mock Pi/bridge end-to-end session that proves Roon still works, swipe contexts, 2-second hold, one 600-second Pi interval, immediate DRAIN, status recovery after network loss, and no POST replay. Inspect logs for token disclosure. First hardware flash/USB test uses 24 V disconnected and an exact SHA; no live-valve claim from build or GPIO readback.
- [ ] **Step 4: Document and commit.** Record the exact firmware and Pi commits, tested artifact, the remaining physical commissioning gate, token rotation/CrowPanel retirement, and `FIRMWARE_AUTO_UPDATE=false`. `git add idf_app/main docs/dev/DEVELOPMENT.md docs/valve-dial-commissioning.md scripts/test_valve_dial.sh && git commit -m "docs(dial): gate custom firmware updates and commissioning"`.

This firmware plan is independently testable against a mock Pi API. Execution needs a writable maintained firmware fork and a chosen exact base SHA; the Pi plan can be implemented and tested first without the hardware.
