# M1B CrowPanel firmware Implementation Plan

> **Historical implementation record.** Do not use this plan as a runbook or
> project-status source. See [`../../PROJECT_STATE.md`](../../PROJECT_STATE.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a flashable, local-only Elecrow CrowPanel firmware that displays Hub status and can request a fixed server-controlled shower or immediate drain without knowing relay, weather, or policy details.

**Architecture:** The firmware is a PlatformIO Arduino project with a small pure view-model reducer, a Hub HTTP client, and LVGL hardware/input layers. It uses the vendor-confirmed ESP32-S3 display/touch/encoder pins, polls only the Hub display API, and renders safe disabled actions whenever Wi-Fi or Hub connectivity is unavailable.

**Tech Stack:** PlatformIO, Arduino-ESP32, ESP32-S3, LVGL 8.3.11, LovyanGFX, ArduinoJson, WiFi, HTTPClient, Unity native tests.

**Spec:** `docs/superpowers/specs/2026-09-11-m1-weather-display-design.md`

## Global Constraints

- Target is Elecrow CrowPanel 1.28-inch HMI rotary display: ESP32-S3R8, 240x240 GC9A01 display, CST816D touch, encoder A GPIO45/B GPIO42/button GPIO41, display SPI SCLK GPIO10/MOSI GPIO11/DC GPIO3/CS GPIO9/RST GPIO14, touch SDA GPIO6/SCL GPIO7/RST GPIO13/INT GPIO5, backlight GPIO46.
- Firmware contains no relay pin, Node-RED address/token, weather-provider secret, automatic safety-policy code, or offline control path.
- It sends display credentials only in `X-Display-Token`; Wi-Fi and Hub credentials exist only in an ignored `include/secrets.h` provisioned from `include/secrets.example.h`.
- The home action is `TUŠ 10 MIN` only when the current Hub response marks it available; when a timer runs, it is `ZAPRI TAKOJ`.
- Any unavailable Wi-Fi or Hub response disables actions and renders exactly `NI POVEZAVE — PREVERI HUB`.

---

## File structure

```text
firmware/crowpanel/platformio.ini             # ESP32-S3 board, dependencies and native test environment
firmware/crowpanel/include/board_pins.h       # verified board constants only
firmware/crowpanel/include/secrets.example.h  # compile-safe user-provisioning template
firmware/crowpanel/include/display_types.h    # Hub payload and UI state value types
firmware/crowpanel/include/display_state.h    # pure reducer interface
firmware/crowpanel/include/hub_client.h       # authenticated Hub client interface
firmware/crowpanel/include/hardware.h         # LVGL and input interface
firmware/crowpanel/src/display_state.cpp       # pure payload-to-page reducer
firmware/crowpanel/src/hub_client.cpp          # authenticated GET/POST client
firmware/crowpanel/src/hardware.cpp            # LovyanGFX, CST816D, LVGL, encoder initialization
firmware/crowpanel/src/main.cpp                # five-second poll and event dispatch
firmware/crowpanel/test/test_display_state.cpp # native reducer/action tests
firmware/crowpanel/README.md                   # provisioning, build, flash and physical test sequence
```

### Task 1: Establish a buildable board configuration and secret boundary

**Files:**
- Create: `firmware/crowpanel/platformio.ini`, `firmware/crowpanel/include/board_pins.h`, `firmware/crowpanel/include/secrets.example.h`, `firmware/crowpanel/.gitignore`, `firmware/crowpanel/README.md`

**Interfaces:**
- Produces: `BoardPins` constants and compile-time `WIFI_SSID`, `WIFI_PASSWORD`, `HUB_BASE_URL`, `DISPLAY_TOKEN` only from ignored `include/secrets.h`.

- [ ] **Step 1: Write a compile-boundary test and example template**

```cpp
static_assert(BoardPins::kEncoderA == 45);
static_assert(BoardPins::kEncoderB == 42);
static_assert(BoardPins::kEncoderButton == 41);
```

- [ ] **Step 2: Run PlatformIO environment discovery**

Run: `pio project config --project-dir firmware/crowpanel`

Expected: the configuration is absent or fails before `platformio.ini` exists.

- [ ] **Step 3: Create PlatformIO configuration**

Configure `esp32-s3-devkitc-1`, `framework = arduino`, `board_build.arduino.memory_type = qio_opi`, `board_build.flash_mode = qio`, 16 MB flash, `monitor_speed = 115200`, and library dependencies `lvgl/lvgl@8.3.11`, `lovyan03/LovyanGFX`, and `bblanchon/ArduinoJson`. Ignore `include/secrets.h`; template must have literal replacement values and never a usable credential.

- [ ] **Step 4: Build the empty firmware**

Run: `pio run -d firmware/crowpanel`

Expected: PASS once `src/main.cpp` prints a boot banner and includes the provisioned header.

- [ ] **Step 5: Commit the firmware base**

```bash
git add firmware/crowpanel
git commit -m "feat: scaffold CrowPanel firmware project"
```

### Task 2: Implement testable display-state and action semantics

**Files:**
- Create: `firmware/crowpanel/include/display_types.h`, `firmware/crowpanel/src/display_state.cpp`, `firmware/crowpanel/test/test_display_state.cpp`

**Interfaces:**
- Produces: `DisplayModel reduceStatus(const HubStatus&, bool wifi_connected, bool hub_connected)` and `Action nextAction(const DisplayModel&)`.
- Consumes: Hub fields `state`, `reason`, `pipe_temperature_c`, `sensor_health`, `forecast_minima_c[7]`, `forecast_fetched_at`, `timed_shower_deadline`, and `action`.

- [ ] **Step 1: Write native reducer tests**

```cpp
void test_offline_disables_actions_and_shows_required_copy() {
  DisplayModel model = reduceStatus(healthyStatus(), true, false);
  TEST_ASSERT_FALSE(model.action_enabled);
  TEST_ASSERT_EQUAL_STRING("NI POVEZAVE — PREVERI HUB", model.connection_text.c_str());
}

void test_active_timer_maps_primary_action_to_immediate_drain() {
  HubStatus status = healthyStatus(); status.action = Action::CloseNow;
  TEST_ASSERT_EQUAL(Action::CloseNow, nextAction(reduceStatus(status, true, true)));
}
```

- [ ] **Step 2: Run native tests to verify failure**

Run: `pio test -d firmware/crowpanel -e native`

Expected: FAIL because reducer sources are absent.

- [ ] **Step 3: Implement a pure reducer**

Map absent temperature to `SENZOR ČAKA`; map all seven forecast minima into fixed display rows; map `TIMED_SHOWER` or Hub action `CLOSE_NOW` to the immediate-drain action. Never calculate a safety decision or manufacture a fallback action in the reducer.

- [ ] **Step 4: Run native tests and embedded build**

Run: `pio test -d firmware/crowpanel -e native && pio run -d firmware/crowpanel`

Expected: PASS.

- [ ] **Step 5: Commit display-state behavior**

```bash
git add firmware/crowpanel
git commit -m "feat: add CrowPanel safety display state"
```

### Task 3: Add Hub client and hardware/input UI

**Files:**
- Create: `firmware/crowpanel/src/hub_client.cpp`, `firmware/crowpanel/src/hardware.cpp`
- Modify: `firmware/crowpanel/src/main.cpp`, `firmware/crowpanel/include/display_types.h`

**Interfaces:**
- Produces: `HubClient::poll() -> HubResult`, `HubClient::startTimedShower() -> bool`, `HubClient::drain() -> bool`, `HardwareUi::render(const DisplayModel&)`, and `HardwareUi::pollInput() -> InputEvent`.

- [ ] **Step 1: Write a compile-time request contract test**

```cpp
void test_action_paths_are_display_api_only() {
  TEST_ASSERT_EQUAL_STRING("/api/v1/display/actions/timed-shower", HubClient::kTimedShowerPath);
  TEST_ASSERT_EQUAL_STRING("/api/v1/display/actions/drain", HubClient::kDrainPath);
}
```

- [ ] **Step 2: Run test to verify failure**

Run: `pio test -d firmware/crowpanel -e native`

Expected: FAIL because `HubClient` constants are missing.

- [ ] **Step 3: Implement bounded networking and LVGL UI**

Use an HTTP timeout of five seconds and `X-Display-Token` on all Hub calls. Treat a non-200 response, JSON parse failure, or Wi-Fi disconnect as `hub_connected=false`; never retry an action automatically. Configure LovyanGFX GC9A01 with the listed SPI pins, CST816D I2C with the listed touch pins, LVGL 240x240 draw buffer, encoder rotation to select Home/Forecast, and touch/encoder press only to invoke an enabled primary action. Render Home with state, pipe temperature or `SENZOR ČAKA`, forecast readiness, connectivity, and button; render Forecast with seven dates/minima, fetched time, and reason.

- [ ] **Step 4: Run native tests and firmware build**

Run: `pio test -d firmware/crowpanel -e native && pio run -d firmware/crowpanel`

Expected: PASS.

- [ ] **Step 5: Commit UI and Hub client**

```bash
git add firmware/crowpanel
git commit -m "feat: add CrowPanel Hub client and LVGL UI"
```

### Task 4: Prepare repeatable flash and acceptance verification

**Files:**
- Modify: `firmware/crowpanel/README.md`, `README.md`
- Create: `deployment/CROWPANEL_COMMISSIONING.md`

**Interfaces:**
- Produces: copy-paste provisioning, flash, serial-monitor, and six-step physical acceptance procedure.

- [ ] **Step 1: Write explicit hardware acceptance checklist**

Include vendor driver/BOOT USB detection, copy `secrets.example.h` to ignored `secrets.h`, `pio run -t upload`, `pio device monitor`, Wi-Fi join, authenticated status screen, encoder navigation, timed-shower request, immediate drain, and forced Hub-loss screen. State that first hardware execution occurs with valve 24 V power disconnected.

- [ ] **Step 2: Verify documentation references only real paths**

Run: `rg -n "(GPIO ?26|GPIO ?20|Node-RED|Open-Meteo)" firmware/crowpanel/src firmware/crowpanel/include`

Expected: no firmware source references relay pins, Node-RED, or Open-Meteo; documentation may name them only in the safety boundary.

- [ ] **Step 3: Run complete verification**

Run: `pio test -d firmware/crowpanel -e native && pio run -d firmware/crowpanel && python -m pytest -q`

Expected: PASS.

- [ ] **Step 4: Commit test-ready firmware handoff**

```bash
git add firmware/crowpanel README.md deployment/CROWPANEL_COMMISSIONING.md
git commit -m "docs: add CrowPanel flash acceptance procedure"
```
