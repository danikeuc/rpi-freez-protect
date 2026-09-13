# M1 Weather, paired-valve, and CrowPanel design

**Status:** Approved for implementation on 11 September 2026.

## Goal

Extend the M0 local control core into a safe Raspberry Pi installation for the outdoor shower. M1 delivers a cached Open-Meteo forecast adapter, a protected Node-RED bridge for the existing relay board, and CrowPanel display firmware. The DS18B20 adapter is prepared now but automatic normal operation remains disabled until the sensor arrives, is wired, and passes commissioning.

## Confirmed installation

| Component | Confirmed configuration |
| --- | --- |
| Control hub | Raspberry Pi 4 Model B on DietPi |
| Relay execution | Existing DietPi `node-red.service` with the Waveshare RPi relay board |
| Relay polarity | Active-low inputs: GPIO `0` energizes a relay and GPIO `1` releases it |
| Relay 1 | BCM GPIO 26, header pin 37, controls valve V1 |
| Relay 2 | BCM GPIO 20, header pin 38, controls valve V2 |
| Relay 3 | BCM GPIO 21, header pin 40, reserved and never used by M1 |
| Valves | Two U.S. Solid USS-MSV10023 1/2-inch, two-wire, 9-24 V AC/DC T-type valves |
| Valve supply | Existing 24 V transformer, with at least 1 A continuous output required for both 5 W valves |
| Valve plumbing | Situation 2: each powered valve connects `Dovod` (right) to `Tuš` (left); each unpowered valve connects `Tuš` (left) to `Izpust` (bottom) |
| Pipe sensor | Waterproof DS18B20, 2.5 m cable, not yet available; expected in approximately three weeks |
| Display | Elecrow CrowPanel 1.28-inch HMI rotary display, ESP32-S3R8, 240x240 capacitive touch screen and rotary encoder |

The valve's two ports are a bidirectional physical connection. The supplier's flow illustration is treated as the normal supply direction; in drain mode water from the shower pipe may flow from `Tuš` to `Izpust`.

## Safety invariant

`DRAIN` is the physical safe state and is always represented by both relay inputs released. `SUPPLY` is represented by both relay inputs energized. The two valves are one logical paired actuator: M1 never commands one valve without the other.

| Logical command | Relay 1 / GPIO 26 | Relay 2 / GPIO 20 | Plumbing result |
| --- | --- | --- | --- |
| `DRAIN` | released (`1`) | released (`1`) | `Tuš` to `Izpust` |
| `SUPPLY` | energized (`0`) | energized (`0`) | `Dovod` to `Tuš` |
| Startup, restart, fault | released (`1`) | released (`1`) | `DRAIN` |

The two-wire auto-return valves must receive continuous 24 V while `SUPPLY` is required. The old Node-RED five-second pulse flow must not be used for normal operation. At commissioning, power both valves for at least one minute before testing an automatic return, as required to charge their return capacitors.

## Behaviour before the DS18B20 is installed

The missing sensor is a planned commissioning state, not permission to infer a safe pipe temperature from the weather forecast. The Hub therefore remains in `FROST_PROTECTION` with `DRAIN` commanded until a DS18B20 has a healthy, commissioned reading.

Open-Meteo is fetched, persisted, validated, and shown now. It is a readiness indicator only until the sensor is installed. It must never cause automatic `SUPPLY` by itself.

The local display may request `TIMED_SHOWER` while in `FROST_PROTECTION`, including its `sensor_pending` reason. This is the confirmed explicit user exception: the Hub starts `SUPPLY` for its server-configured duration, default 10 minutes and hard maximum 30 minutes, then unconditionally returns to `DRAIN`. The display cannot submit a duration and cannot override the maximum.

## M1 control states

M1 replaces the M0 operational labels with states that match the installed plumbing and UI. Every state carries a machine-readable reason for the portal, display, and audit log.

| State | Requested paired actuator state | Entry condition |
| --- | --- | --- |
| `STARTING` | `DRAIN` | Process boot or restart before a relay-bridge health check |
| `FROST_PROTECTION` | `DRAIN` | Cold pipe, unsafe/missing forecast, sensor pending, or a completed timed shower |
| `NORMAL` | `SUPPLY` | Healthy commissioned sensor above the re-open threshold and seven eligible forecast minima |
| `TIMED_SHOWER` | `SUPPLY` | Accepted display request; ends at the Hub's recorded deadline or a drain action |
| `FAULT` | `DRAIN` | Relay bridge cannot confirm the requested state, persistence fails, or configuration is invalid |

The pipe thresholds, weather threshold, seven-day rule, sensor staleness, forecast staleness, 10-minute default shower duration, and 30-minute shower maximum are persisted settings. The defaults are respectively 5 °C, 7 °C, 5 °C, seven days, two minutes, six hours, ten minutes, and thirty minutes.

`NORMAL` is impossible without a valid, commissioned local sensor. A sensor read failure later returns to `FROST_PROTECTION` and requests `DRAIN` unless a previously accepted `TIMED_SHOWER` is still active. A relay-bridge failure is a `FAULT` because the Hub cannot establish the requested safe position.

## Open-Meteo forecast adapter

The Hub is the only Open-Meteo client. It makes outbound HTTPS requests only; there is no cloud command channel or inbound port.

~~~text
GET https://api.open-meteo.com/v1/forecast
    ?latitude={configured latitude}
    &longitude={configured longitude}
    &daily=temperature_2m_min
    &forecast_days=7
    &timezone={configured IANA timezone}
~~~

The adapter refreshes once per hour, accepts only a response that has exactly seven date-aligned finite daily minima, and stores the source time, retrieval time, location, and values in SQLite. The last valid forecast is usable for at most six hours. A malformed response, HTTPS error, timeout, location mismatch, or stale record is unsafe for `NORMAL` and appears as an explicit status reason. The seven minima must all be strictly greater than the configured forecast threshold; a value equal to the threshold is not eligible.

## DS18B20 adapter and delayed commissioning

M1 includes a `Ds18b20TemperatureSource`, but no sensor-dependent automation is enabled before commissioning. The adapter uses a powered three-wire 1-Wire connection: BCM GPIO 4/header pin 7 for data, 3.3 V, GND, and a 4.7 kOhm pull-up from data to 3.3 V. It identifies the configured `28-*` device ID from the Linux 1-Wire device tree and rejects missing, CRC-invalid, non-finite, and stale readings.

When the probe arrives, commissioning requires: wiring inspection, two stable ambient readings, a plausibility comparison against an independent thermometer, installation directly on the pipe under insulation, and a controlled cold/warm threshold test. Only then may an administrator mark the sensor commissioned and enable automatic `NORMAL`.

## Node-RED relay bridge

Node-RED remains the authenticated HTTP bridge, but it is not the low-level GPIO executor. A dedicated local paired-GPIO daemon owns `/dev/gpiomem`, configures BCM 26 and BCM 20 as outputs, and changes their output latches with one masked GPSET0/GPCLR0 write. It then reads both levels back before returning a result. This gives the two relay inputs one atomic hardware-level state transition rather than two independent Node-RED GPIO messages.

The new flow binds only to loopback and accepts a Hub token. It exposes one idempotent command with two allowed values:

~~~http
POST /internal/freeze-protect/actuator
X-Hub-Token: <secret>
Content-Type: application/json

{"command":"SUPPLY","request_id":"<uuid>"}
~~~

`DRAIN` uses the same endpoint. Node-RED starts a bounded Unix-socket client to the single daemon and does not return `200` until the daemon confirms the requested command and both GPIO levels. Each `SUPPLY` carries a short absolute deadline from the original HTTP request; a delayed or stale request is rejected before it can change GPIO state. `DRAIN` remains accepted even after its deadline. On deployment and Node-RED restart, the daemon must verify GPIO 26 and 20 high before the bridge starts accepting requests. The previous `/trigger/...` routes, single-relay routes, pair routes, and variable-duration triggers are removed from the user path. Before 24 V is connected, a preflight checks that no enabled legacy tab has GPIO 26/20 outputs or `/trigger` routes, and that exactly one paired bridge route is active. Legacy flows may exist only as disabled export/rollback material or in a physically disconnected service test flow.

The Hub uses a short timeout and records the bridge receipt. It retries a failed `DRAIN` request only once, then records `FAULT`; it never retries a failed `SUPPLY` request automatically.

## CrowPanel firmware

The firmware targets the Elecrow CrowPanel 1.28-inch HMI rotary display. It uses PlatformIO with Arduino-ESP32 and LVGL 8.3.11. The application owns only presentation, local input, Wi-Fi connectivity, and its Hub device token. It does not include a GPIO library, Node-RED address, relay pin, weather-provider credential, or safety policy.

The firmware polls a read-only Hub status endpoint every five seconds and uses the rotary encoder to switch between two pages:

1. **Home:** state, large pipe temperature or `SENZOR ČAKA`, forecast safety, Wi-Fi/Hub status, and the primary `TUŠ 10 MIN` action.
2. **Forecast:** seven daily minima, last refresh, and the reason automatic normal operation is unavailable.

Touching the primary action or pressing the encoder calls:

~~~http
POST /api/v1/display/actions/timed-shower
X-Display-Token: <secret>
~~~

The Hub chooses the duration. During a timed shower, the same action is replaced with `ZAPRI TAKOJ`, which calls the Hub's drain action. An unavailable Hub disables both actions and shows `NI POVEZAVE — PREVERI HUB`; the display cannot retain or create an offline override.

Wi-Fi SSID, password, Hub base URL, and display token are injected during provisioning and ignored by Git. The repository contains an example template only. Firmware flash and user-input tests run first on the physical CrowPanel; they do not affect the Pi relay process during display development.

## Display LAN gateway

The Hub process remains bound to `127.0.0.1:8000`. A separate local Nginx listener on port 8081 proxies only `GET /api/v1/display/status`, `POST /api/v1/display/actions/timed-shower`, and `POST /api/v1/display/actions/drain`; every other path returns 404. The CrowPanel uses this LAN-only port with its display token. Administrator and Node-RED interfaces are never exposed through the gateway, and the router must not forward port 8081 to the internet.

## Local portal and API additions

The existing administrator token API evolves into the local portal described in the approved shower design. M1 adds these bounded interfaces:

| Consumer | Endpoint | Purpose |
| --- | --- | --- |
| Administrator | `GET/PUT /api/v1/settings` | Location, IANA timezone, thresholds, staleness, display defaults, and sensor commissioning flag |
| Administrator | `GET /api/v1/status` | Actuator command, weather freshness, sensor status, timed-shower deadline, and bridge health |
| Display | `GET /api/v1/display/status` | Minimal display-safe state and seven-day forecast, authenticated by display token |
| Display | `POST /api/v1/display/actions/timed-shower` | Starts the server-controlled default duration |
| Display | `POST /api/v1/display/actions/drain` | Immediately returns both valves to safe drain |
| Hub | `POST /internal/freeze-protect/actuator` on loopback Node-RED | Requests only `SUPPLY` or `DRAIN` |

Administrative movement commands and display actions are audited. Passwords and tokens are never stored in the repository, returned by an API, or printed in the display log.

## Test and commissioning gates

Automated tests must cover forecast parsing and staleness, the strict seven-day rule, sensor-pending safety, timed-shower start/restart/expiry, the hard 30-minute ceiling, the atomic paired-GPIO mask write and readback, rejection of stale `SUPPLY`, bridge timeout handling, and the display API's device-token authorization. Firmware tests cover page state mapping, rotary navigation, disabled offline actions, and action request payloads.

Physical commissioning occurs in this order:

1. With valve power disconnected, confirm Node-RED `SUPPLY` emits low on both GPIO 26 and 20 and `DRAIN` emits high on both.
2. With water isolated, connect 24 V and verify both valves move together; confirm `SUPPLY` connects `Dovod` to `Tuš` and `DRAIN` connects `Tuš` to `Izpust`.
3. Keep `SUPPLY` active for one minute, remove power, and verify return to `DRAIN` for both valves.
4. Flash the CrowPanel, provision its local credentials, and test display status, timed shower, immediate drain, and loss-of-Hub behavior.
5. When DS18B20 arrives, complete the sensor commissioning procedure before enabling automatic `NORMAL`.

## Scope split

Implementation has two independently testable deliverables:

1. **M1A — Hub and relay bridge:** forecast adapter, persistence, safety-state migration, display API, sensor-pending mode, and Node-RED bridge flow.
2. **M1B — CrowPanel firmware:** PlatformIO project, LVGL UI, provisioning, display API client, and hardware flash test.

M1B may be developed in parallel with M1A, but its physical actions remain disabled until M1A's authenticated display API is available.
