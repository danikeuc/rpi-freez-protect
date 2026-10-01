# Waveshare PT100 Shower Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse the Pi's optional PT100 telemetry and show one decimal temperature on the Waveshare shower page, with exact fallback `---`, while preserving the released Roon and manual valve behavior.

**Architecture:** Extend the existing bounded JSON parser and `valve_status_t` with optional display telemetry. A pure formatter owns decimal-comma output. The new LVGL label is a child of the existing valve overlay, so page switching hides it with the complete shower page and no temperature widget exists on the Roon page.

**Tech Stack:** C11, ESP-IDF 5.5.5, LVGL, JSMN, host-compiled assertion tests, ESP32-S3 target build.

**Spec:** [`rpi-freez-protect/docs/superpowers/specs/2026-10-01-waveshare-pt100-telemetry-design.md`](../specs/2026-10-01-waveshare-pt100-telemetry-design.md)

## Global Constraints

- Firmware repository: `/mnt/c/users/danik/projects/roon-knob-valves`.
- Start a new `codex/waveshare-pt100-display` branch at the immutable `v2.5.3-valve.1` source commit `b32fd8a2ee1f3b2731fbc13179c605e86a8c0d0a`. Do not move or overwrite that release tag.
- Follow the firmware repository `AGENTS.md`: use the GitHub issue as the work record; keep the PR draft until the exact artifact is flashed and visually tested; do not merge or tag without explicit user approval.
- Preserve strict validation of the core tuple `mode`, `state`, `command`, `reason`, and `remaining_seconds`.
- Treat all temperature fields as display-only. They must never participate in `valve_supply_allowed()`, `valve_drain_allowed()`, the two-second hold, request ordering, polling, reconnection, or Roon routing.
- Accept legacy Pi responses with no temperature fields and render `---`.
- Do not display `PT100`, freshness, health, fault, or SPI diagnostic text.
- A host suite or successful ESP-IDF build does not prove the physical display, touch, Wi-Fi, sensor, relay, or valve behavior.

## Review Focus

- Verify malformed optional telemetry cannot turn a valid valve tuple into `VALVE_UNKNOWN`.
- Verify duplicate optional keys, partial pairs, null, wrong types, non-healthy status, and out-of-range values all become unavailable telemetry.
- Verify values at -50.0 and 120.0 are accepted; values outside that closed range are unavailable.
- Verify formatting produces one decimal, a comma, UTF-8 degree sign, no `-0,0`, and exact `---` for unavailable data.
- Verify every transition to unknown/stale/connection loss removes an old temperature immediately.
- Verify the label belongs to the valve overlay and all existing Roon, gesture, action, recovery, and token-redaction tests remain green.

---

### Task 1: Establish the firmware work item and branch

**Files:** None.

- [ ] **Step 1: Inspect issue state.** Run `gh issue list --repo danikeuc/roon-knob --state open --limit 50` and reuse a matching PT100 shower-display issue if one exists. Otherwise create one with the approved spec scope, safety boundaries, exact base SHA, and links to the three implementation plans.
- [ ] **Step 2: Create the feature branch from the released source.** From `/mnt/c/users/danik/projects/roon-knob-valves`, run `git switch -c codex/waveshare-pt100-display b32fd8a2ee1f3b2731fbc13179c605e86a8c0d0a` and verify `git status --short --branch` is clean.
- [ ] **Step 3: Record the issue number in the implementation notes or PR body only.** Do not create a second Markdown task database.

### Task 2: Parse optional telemetry without weakening valve validation

**Files:**

- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/idf_app/main/valve_logic.h`
- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/idf_app/main/valve_logic.c`
- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/tests/valve_dial/test_valve_logic.c`

**Interfaces:**

```c
typedef struct {
    valve_state_t state;
    uint16_t remaining_seconds;
    char reason[96];
    float pipe_temperature_c;
    bool temperature_available;
} valve_status_t;

void valve_temperature_format(
    const valve_status_t *status,
    char *buffer,
    size_t buffer_size
);
```

- [ ] **Step 1: Add failing legacy and healthy cases.** Prove the current JSON without temperature remains a valid DRAIN/SUPPLY status with `temperature_available=false`. Add healthy cases for integers, fractions, negative values, exponent notation, and the inclusive -50/120 boundaries.
- [ ] **Step 2: Add a failing unavailable matrix.** Cover `pipe_temperature_c:null`, each non-healthy uppercase enum, lowercase or unknown health, one missing field, wrong JSON types, duplicate optional keys, numbers below -50 or above 120, and a valid optional field nested under another key. Every case must retain the valid core valve state and set `temperature_available=false`.
- [ ] **Step 3: Preserve strict core failure tests.** Keep duplicate/missing/contradictory core fields, malformed JSON, invalid UTF-8, oversized input, invalid countdown, and unsupported modes returning false with `VALVE_UNKNOWN`.
- [ ] **Step 4: Run the host suite and capture the expected failure.** Run `PATH=/tmp/knob-bin:$PATH ./scripts/test_valve_dial.sh`. The new assertions should fail before implementation.
- [ ] **Step 5: Implement bounded optional parsing.** Add independent seen bits for `pipe_temperature_c` and `sensor_health`; keep the required-core mask separate from optional state. Copy a primitive number token into a fixed local buffer, parse it with `strtof`, require complete consumption and `isfinite`, and apply the closed -50..120 range. Only an exactly once pair of numeric value plus `HEALTHY` sets `temperature_available=true`; all optional errors clear availability without changing the accepted core tuple.
- [ ] **Step 6: Run the focused host suite.** Run `PATH=/tmp/knob-bin:$PATH ./scripts/test_valve_dial.sh`; all existing and new parser cases must pass.
- [ ] **Step 7: Commit the parser slice.** Commit with `git add idf_app/main/valve_logic.h idf_app/main/valve_logic.c tests/valve_dial/test_valve_logic.c && git commit -m "feat(valves): parse optional PT100 telemetry"`.

### Task 3: Format the exact dial text

**Files:**

- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/idf_app/main/valve_logic.c`
- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/tests/valve_dial/test_valve_logic.c`

- [ ] **Step 1: Add failing formatter tests.** Assert `6.44 -> "6,4 °C"`, `6.46 -> "6,5 °C"`, `-7.2 -> "-7,2 °C"`, values rounding near zero do not display `-0,0`, and unavailable status produces exactly `---`. For `buffer == NULL` or `buffer_size == 0`, the function is a no-op; smaller nonzero buffers follow bounded `snprintf` truncation and remain null-terminated.
- [ ] **Step 2: Run the focused host binary through the full script and capture failure.** Run `PATH=/tmp/knob-bin:$PATH ./scripts/test_valve_dial.sh`.
- [ ] **Step 3: Implement the pure formatter.** Normalize values whose one-decimal result would be negative zero, format with `snprintf`, replace the decimal point with a comma, append the UTF-8 ` °C` suffix, and emit exactly `---` when `status` is null or unavailable. Keep buffer handling bounded and null-terminated.
- [ ] **Step 4: Run the full host suite.** Run `PATH=/tmp/knob-bin:$PATH ./scripts/test_valve_dial.sh`; all tests must pass.
- [ ] **Step 5: Commit the formatter slice.** Commit with `git add idf_app/main/valve_logic.c tests/valve_dial/test_valve_logic.c && git commit -m "feat(ui): format shower temperature"`.

### Task 4: Render temperature only on the shower overlay

**Files:**

- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/idf_app/main/valve_ui_dial.c`
- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/tests/valve_dial/fakes/lvgl.h`
- Modify: `/mnt/c/users/danik/projects/roon-knob-valves/tests/valve_dial/test_valve_ui_sequence.c`

**UI contract:** Create `s_temperature` as a label parented by `s_overlay`, positioned at the upper left around `(48, 31)`, using `lv_font_montserrat_20` and `ICON_COLOR`. Create it after the existing controls and shower symbol so current fake-object indices remain stable. Every `render()` call sets it from `valve_temperature_format()` when the complete status is fresh; unknown, pending, stale, disconnected, and invalid completion states set `---`.

- [ ] **Step 1: Extend the LVGL fake for semantic assertions.** Record each object's parent and position, provide the minimal `lv_font_t`/`lv_font_montserrat_20` and text style stubs, and add a helper in the sequence test that finds a label by text instead of assigning a new brittle index.
- [ ] **Step 2: Add failing UI sequence cases.** Emit a fresh DRAIN status with `temperature_available=true` and assert the overlay child reads `6,4 °C`. Assert SUPPLY preserves the temperature. Then exercise unknown status, timeout, stale age, disconnect, malformed completion, and reconnect with unavailable telemetry; each must show `---` and must not retain the old number.
- [ ] **Step 3: Prove shower-only visibility.** Assert the temperature object's parent is the valve overlay, `valve_ui_show(false)` hides that overlay, and the label returns only with `valve_ui_show(true)`. Do not add any temperature call or object in the shared Roon UI.
- [ ] **Step 4: Run the host suite and capture the expected failure.** Run `PATH=/tmp/knob-bin:$PATH ./scripts/test_valve_dial.sh`.
- [ ] **Step 5: Implement the label and render updates.** Use a local fixed text buffer in `render()`. Preserve all existing action enabling, shower/snow symbol behavior, relay indicator colors, request ordering, and `ui_set_valve_active()` calls.
- [ ] **Step 6: Run the complete host suite.** Run `PATH=/tmp/knob-bin:$PATH ./scripts/test_valve_dial.sh`. Confirm valve UI, integration, settings gesture, Roon routing, and token-redaction gates all pass.
- [ ] **Step 7: Commit the UI slice.** Commit with `git add idf_app/main/valve_ui_dial.c tests/valve_dial/fakes/lvgl.h tests/valve_dial/test_valve_ui_sequence.c && git commit -m "feat(ui): show PT100 on shower page"`.

### Task 5: Build, review, and prepare the exact artifact

**Files:**

- Modify after verification: `/mnt/c/users/danik/projects/roon-knob-valves/docs/valve-dial-commissioning.md`

- [ ] **Step 1: Run all source gates from a clean tree.** Run `PATH=/tmp/knob-bin:$PATH ./scripts/test_valve_dial.sh`, `bash /tmp/knob-idf-build.sh`, and `git diff --check`. Use ESP-IDF 5.5.5 and do not reuse an unverified binary from another commit.
- [ ] **Step 2: Record artifact identity.** Record `git rev-parse HEAD`, `stat` size, `sha256sum idf_app/build/hiphi_dial.bin`, partition free-space output, and build tool version. Confirm the build did not modify tracked `sdkconfig` unexpectedly.
- [ ] **Step 3: Update source evidence only.** Add the exact commit, commands, results, artifact size/SHA, and remaining physical gaps to `docs/valve-dial-commissioning.md`. Do not claim flash, display geometry, temperature accuracy, or hardware behavior yet.
- [ ] **Step 4: Run `/review` and `/dissent`.** Check alignment with the approved spec, parser attack surface, stale-state clearing, Roon regressions, and the immutable release boundary. Post both reports to the GitHub issue/PR with the exact head SHA and unresolved hardware gates.
- [ ] **Step 5: Create a draft PR.** Push `codex/waveshare-pt100-display`, open a draft PR against the fork's development base, attach the PR to the Codex task, and include purpose, changes, actual tests, documentation/evidence, risks, exact head SHA, and flash/rollback plan. Do not merge or tag.
- [ ] **Step 6: Commit evidence documentation if changed.** Commit with `git add docs/valve-dial-commissioning.md && git commit -m "docs: record PT100 display build evidence"`, rebuild if the commit must identify the exact source state, and update the PR with the final relationship between source and evidence commits.
