# Waveshare Dial Roon and Timed Valve Control Design

## Intent and confirmed behavior

One Waveshare ESP32-S3 Knob 1.8-inch touch dial controls Roon and the existing
paired Raspberry Pi valve relays. A horizontal swipe changes between a Roon
screen and a valve screen. The valve screen can request `SUPPLY` for up to ten
minutes and can request `DRAIN` immediately. Only an intentional action on this
dial may start `SUPPLY`; weather, temperature, service startup, and network
reconnection never start it. The Raspberry Pi owns the timer and actuator
decision. Losing power leaves the relays de-energized in `DRAIN`.

The logical relay contract is `DRAIN = 0` (both relays released) and
`SUPPLY = 1` (both relays energized). The existing active-low GPIO interface
uses BCM 26 and 20 high/high for `DRAIN` and low/low for `SUPPLY`. No client
may address one relay independently. GPIO readback confirms output levels,
not physical valve position.

## Existing evidence and scope

The repository implements a server-controlled timed shower, a minimal
token-protected display API, a loopback Node-RED bridge, and a paired-GPIO
daemon with a 60-second `SUPPLY` lease. Its automatic weather policy can
currently request `SUPPLY`; its present `DRAIN` action is not a persistent
manual mode. The Waveshare firmware is the separate `muness/roon-knob` project;
`danikeuc/roon-control` is the Rust Unified Hi-Fi Control bridge, which already
serves the dial's Roon commands. The firmware currently uses vertical swipes
for art mode; horizontal swipes require a firmware change.

These are repository observations. The installed Raspberry Pi software,
Waveshare firmware revision, 24 V supply, GPIO outputs, and physical valve
positions are not verified by this design work. The CrowPanel remains a
separate existing client, and it is not a control surface for the proposed
manual mode.

## Approaches considered

1. **Selected: one dial, two narrow HTTP clients.** Keep Roon traffic on the
   Unified Hi-Fi Control bridge and send valve requests directly to the
   Freeze Protect display API. The Pi retains the actuator authority. A Roon
   outage does not prevent the dial from requesting `DRAIN`.
2. Route valve requests through Unified Hi-Fi Control. This gives the dial one
   server address but makes a music bridge part of the valve control path and
   requires a new authenticated proxy surface there.
3. Command GPIO or Node-RED directly from the dial. This bypasses the Pi
   control service's timer, audit trail, paired-output receipt, and lease, so
   it is excluded.

## Raspberry Pi control model

Add a `manual_timed` operating mode to Freeze Protect. The deployed mode must
be explicit; absent or invalid mode configuration holds `DRAIN` and refuses
`SUPPLY`. Automatic weather and temperature evaluation remains available in
source for a future separately configured mode but never runs in
`manual_timed`. Weather and sensor availability therefore have no authority
over the paired outputs in this mode.

In `manual_timed`, startup commands paired `DRAIN` and clears any prior active
timer. Idle state is `MANUAL_DRAIN`. A valid authenticated
`POST /api/v1/display/actions/timed-shower` changes both outputs to `SUPPLY`
enters the existing `TIMED_SHOWER` state, and starts one server-side
600-second monotonic deadline. Repeated requests
while active acknowledge the current interval without extending it. The
controller renews the daemon's 60-second `SUPPLY` lease only while that
interval is active. At expiry it commands paired `DRAIN` and returns to
`MANUAL_DRAIN`; no automatic cycle may reopen it. An authenticated
`POST /api/v1/display/actions/drain` cancels the deadline and commands paired
`DRAIN` immediately. No duration, pin number, or relay value is accepted from
the dial.

On Hub restart or failure, a Node-RED/daemon failure, a failed paired receipt,
or a persistence fault, the existing fail-safe path requests `DRAIN` or lets
the daemon lease expire. A failed or uncertain `SUPPLY` response is not retried
automatically. The dial losing Wi-Fi does not cancel a previously accepted
interval; the Pi still drains it at the deadline. On reconnection, the dial
reads Pi status instead of replaying an action. A power outage releases the
relays by the stated hardware contract; physical validation remains a
commissioning task.

Keep the current loopback Hub and Node-RED boundaries. Nginx exposes only the
valve status and two action routes to the trusted LAN. Give the Waveshare dial
its own provisioned display token, separate from the admin and Node-RED
tokens. Rotate the current display token and retire the old CrowPanel's copy
so only the Waveshare dial can start `SUPPLY` in this installation. The status
response reports the selected mode, logical relay
command, fault/reason, and server-computed remaining seconds. A reported
command is a software/paired-GPIO receipt, not proof of physical movement.

## Waveshare dial behavior

Extend a maintained fork of `muness/roon-knob`; keep `roon-control` unchanged.
The dial stores the Roon bridge URL and Pi display URL/token in local device
configuration, never in Git or logs. A left or right swipe on either main
screen switches Roon and Valves. Horizontal navigation is disabled while the
Roon zone picker, settings, or art mode is open. Existing vertical art-mode
gestures and Roon playback/volume controls keep their behavior. The swipe
handler consumes the gesture so its initial touch cannot also activate a
valve button.

The valve screen shows `DRAIN (0)`, `SUPPLY (1)`, or `UNKNOWN/FAULT`. Starting
`SUPPLY` requires a continuous two-second touch on a labeled control. A single
touch on `DRAIN` sends the stop request immediately. After the Pi acknowledges
`SUPPLY`, the screen shows a ten-minute countdown based on Pi-reported
remaining time; it never owns the actuator deadline. The Roon screen shows a
small active-valve indicator while the timed interval runs. The dial refreshes
status on entry, after each request, and periodically while awake. A wake from
sleep is status-only. If status is stale or a request times out, the screen
shows `UNKNOWN`, disables the `SUPPLY` action until fresh status returns, and
does not claim that a valve moved. No valve commands are queued offline.

Because the Unified Hi-Fi Control bridge can download upstream dial firmware
for OTA updates, the custom build must use a controlled firmware update path;
an upstream automatic update must not replace the valve-capable image.

## Implementation boundaries

- `rpi-freez-protect`: add the mode and manual state transitions in the
  application service, adapt the display status contract, preserve the
  paired-GPIO daemon and the current authenticated Nginx route allowlist, and
  add focused service/API/lease tests.
- Waveshare firmware fork: add horizontal gesture navigation, valve page,
  authenticated Pi client, status-driven countdown, and tests for gesture
  suppression and failure states.
- `roon-control`: keep the existing Roon API and adapter. Configure its OTA
  behavior for the custom firmware without adding valve routes.

## Verification and commissioning

Software tests must prove startup `DRAIN`, no weather-initiated `SUPPLY` in
`manual_timed`, one interval capped at ten minutes, no extension on duplicate
press, immediate manual `DRAIN`, expiry, restart, failed receipt, persistence
failure, and lease expiry. Firmware tests must prove that swipes never trigger
valve actions, Roon controls remain in the Roon context, an ambiguous response
is not replayed, and reconnection displays the Pi's current status. Python
tests and Ruff follow the repository's `AGENTS.md` gate; firmware build and
target-specific tests follow its own repository instructions.

The first integrated test runs with the 24 V valve supply disconnected. It
checks the API response and both GPIO outputs together through the existing
documented diagnostics. Physical valve movement, power-loss behavior, and a
live `SUPPLY` test require a separate bounded commissioning procedure and
Danijel's explicit approval in that conversation. Repository tests or GPIO
readback alone do not establish the physical valve state.
