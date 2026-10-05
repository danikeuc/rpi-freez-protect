# Waveshare dial commissioning

Weather/playlist candidate procedure: [weather operations](../docs/operations/weather-assisted-shower.md) and [exact repository validation](../docs/evidence/2026-10-03-weather-plan-validation.md). Existing physical/SSH gates remain mandatory. Later candidate staging keeps manual_timed and weather disabled; back up the matching SQLite weather-identity sentinel with its database when present. These source changes do not authorize deployment, timed commands, 24 V connection or flash.

This is the active display procedure for the Waveshare ESP32-S3 Knob 1.8-inch
dial. The Pi remains the valve safety authority. Roon and valve pages share the
dial hardware but use separate service paths.

Read these first:

1. [`../AGENTS.md`](../AGENTS.md)
2. [`COMMISSIONING.md`](COMMISSIONING.md)
3. [`../docs/PROJECT_STATE.md`](../docs/PROJECT_STATE.md)
4. The exact `roon-knob` release notes and the `roon-control` deployment record

## 1. Repository and deployment gates

Before provisioning the dial:

- run the complete checks in
  [`../docs/VERIFICATION.md`](../docs/VERIFICATION.md);
- record exact commits for `rpi-freez-protect`, `roon-control` and `roon-knob`;
- verify the Pi has `FREEZE_PROTECT_CONTROL_MODE=manual_timed`;
- verify `node-red.service`, `freeze-protect-pair-gpio.service`,
  `freeze-protect.service` and Nginx are active;
- verify the old `nodered.service` alias is disabled/inactive;
- run the deployed Node-RED legacy-flow preflight;
- confirm the Hub and Node-RED listeners are loopback-only.

Keep the 24 V valve supply disconnected. A repository check or HTTP response is
not approval for a GPIO or physical test.

## 2. Rotate and provision the display credential

At the trusted Pi console, generate a new independent display token and replace
`FREEZE_PROTECT_DISPLAY_TOKEN` in the protected environment file. Keep it
distinct from the admin and Node-RED tokens. Restart the Hub through the reviewed
Pi procedure and verify locally that:

- `/health` reports service `ok`;
- authenticated display status reports `mode=manual_timed`;
- idle state is `MANUAL_DRAIN`, command is `DRAIN`, remaining seconds is zero;
- an absent, old or malformed display token returns HTTP 401;
- an administrative route through port `8081` returns HTTP 404.

Provision the Pi LAN base URL, such as `http://192.168.114.192:8081`, and the new
display token through the controlled `roon-knob` configuration path. Never put
the token in Git, screenshots, release notes or serial logs.

Remove the retired token from every CrowPanel copy and keep the CrowPanel off the
active valve-control network. Its historical procedure is in
[`CROWPANEL_COMMISSIONING.md`](CROWPANEL_COMMISSIONING.md).

## 3. Roon-only acceptance

Roon acceptance does not touch the valve path:

1. Swipe left/right between Roon and valve pages.
2. Rotate the dial and verify the selected Roon zone changes volume once per
   intended step.
3. Press for play/pause and verify the zone state changes.
4. Interrupt connectivity and verify the display reports unavailable state
   without replaying a queued action after reconnect.

Record displayed state and the independently observed Roon zone result. A UI
animation alone is not end-to-end proof.

## 4. Display-only PT100 telemetry acceptance

This check does not exercise the valve action. Keep the 24 V valve supply
disconnected, `FREEZE_PROTECT_CONTROL_MODE=manual_timed`, and
`sensor_commissioned=false`. Complete the sensor wiring and calibration checks
in [`COMMISSIONING.md` step 4a](COMMISSIONING.md#4a-display-only-pt100max31865-verification)
only after identifying and verifying the exact MAX31865 breakout. Do not switch
to `automatic` for this display feature.

Using authenticated display status, confirm the valve fields remain
`manual_timed`, `MANUAL_DRAIN`, `DRAIN`, zero remaining seconds, and action
enabled. Confirm a fresh sensor returns numeric `pipe_temperature_c` and
`sensor_health=HEALTHY`. Non-automatic modes sample every five seconds; values
at least 15 seconds old are unavailable. Failed or unhealthy readings return a
null temperature with uppercase `STALE`, `INVALID`, or `CALIBRATION_REQUIRED`;
a failed sample clears an earlier numeric value. The display status must not
contain MAX31865 diagnostics, sensor identity, or administrator fields.

Record the repository and installed Pi revisions separately, together with
sample timestamps, sensor health, reference measurements and display
observation. Repository tests and an API response do not prove sensor wiring,
calibration, dial appearance, relay contacts, valve movement or water routing.
Telemetry remains informational and does not change `sensor_commissioned`.

## 5. Disconnected valve acceptance

This step issues an actuator request and requires Danijel's explicit approval in
the same conversation even though 24 V remains disconnected.

1. Confirm 24 V is still disconnected and startup/idle are `DRAIN` with both BCM
   26 and 20 output/high.
2. On the valve page, make one deliberate action. Require one accepted
   600-second interval and both outputs low/low.
3. Repeat the action while active and verify the deadline is not extended.
4. Request immediate drain and require both outputs high/high.
5. Verify disconnect/reconnect, weather activity and sensor state do not start
   `SUPPLY` in `manual_timed`.
6. If testing expiry or restart, require high/high afterward and preserve exact
   timestamps.

Stop on any failed service check, receipt, preflight or readback. Leave the
requested state at `DRAIN`, keep 24 V disconnected and do not retry `SUPPLY`.
GPIO readback is not proof of relay or valve position.

## 6. Live valve gate

A live 24 V test is separate. This document grants no approval to connect valve
power. Only after explicit current-conversation approval and all disconnected
gates pass may the operator use the water-isolated procedure in
[`COMMISSIONING.md`](COMMISSIONING.md#5-connect-and-test-the-valves-with-water-isolated).
Record relay/valve/plumbing observations separately from HTTP and GPIO evidence.

## Rollback

Request `DRAIN`, require paired high/high readback, keep or return 24 V to the
disconnected state, remove the active display credential from the dial and
restore the last reviewed Pi configuration. Do not restore the legacy
unauthenticated Node-RED trigger flow.
