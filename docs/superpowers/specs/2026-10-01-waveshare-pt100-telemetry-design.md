# Waveshare PT100 Telemetry Display Design

## Status

Approved in chat on 2026-10-01 for implementation planning. This design extends
the active Waveshare ESP32-S3 shower page with display-only PT100 telemetry. It
does not enable automatic valve control or commission the sensor for safety
decisions.

## Goal

Show the Raspberry Pi's PT100/MAX31865 pipe temperature on the Waveshare shower
page while preserving the released manual valve-control behavior. A healthy
reading is rendered with one decimal place and a decimal comma, for example
`6,4 °C`. A missing, invalid, failed, or stale reading is rendered as `---`.

The temperature is informational. It must not start, extend, stop, or authorize
`SUPPLY`; it must not change the ten-minute server deadline; and it must not
change `DRAIN` handling.

## Verified baseline

- Raspberry Pi `origin/main` is `e231a401b9a689f8f8bc13ba28fafcc1a7000dc2`,
  tagged `v0.2.0-rc.1`. It contains the production
  `Max31865TemperatureSource`, its deterministic unit tests, Linux SPI service
  permissions, source binding, and commissioning documentation.
- The deployed Pi evidence supplied before this design identified commit
  `dab832f4dd98095db8e68d2189d7f159abc93183` in `manual_timed` mode. That
  revision intentionally omits sensor fields from manual display status and is
  older than `v0.2.0-rc.1`.
- The Waveshare prerelease `v2.5.3-valve.1` points to
  `b32fd8a2ee1f3b2731fbc13179c605e86a8c0d0a`. It polls the Pi every five
  seconds for valve state but does not parse or render temperature.
- The hardware contract confirmed by the user is a three-wire PT100 through a
  MAX31865 with a 430-ohm reference resistor.
- Installation, wiring, SPI availability, calibration, and physical sensor
  fault behavior remain `NOT_VERIFIED` until the commissioning procedure is
  executed against the actual Pi and breakout.

## Scope

### Included

- A display-only temperature sampler for non-automatic Pi modes.
- Healthy/invalid/stale temperature fields in the existing authenticated
  display status response.
- Independent temperature parsing and rendering in the Waveshare firmware.
- Host tests, clean firmware build, read-only Pi diagnostics, disconnected-load
  sensor commissioning, and visual display verification.

### Excluded

- Switching the deployed mode from `manual_timed` to `automatic`.
- Setting `sensor_commissioned=true`.
- Forecast display or forecast-based control.
- Temperature labels such as `PT100`, `fresh`, or diagnostic fault text on the
  dial.
- Roon-page temperature, MAX31865 registers, SPI paths, or administrator-only
  diagnostics in the display API.
- Changes to the relay daemon, GPIO mapping, paired-output invariant, ten-minute
  duration, display authentication, or Nginx route allowlist.

## Hardware contract

The existing production sensor contract remains authoritative:

| Raspberry Pi signal | BCM | Header pin | MAX31865 signal |
| --- | ---: | ---: | --- |
| 3.3 V | - | 1 or 17 | verified input for the exact breakout |
| Ground | - | 6 | GND |
| SPI0 MOSI | 10 | 19 | SDI/MOSI |
| SPI0 MISO | 9 | 21 | SDO/MISO |
| SPI0 SCLK | 11 | 23 | CLK/SCK |
| SPI0 CE0 | 8 | 24 | CS |

The Linux device is `/dev/spidev0.0`, SPI mode 1, 500 kHz maximum, eight bits
per word, three-wire compensation, 50 Hz filtering, and a 430-ohm reference.
The breakout revision, power input label, `4300` reference marking, terminal
mapping, input-filter timing, and disconnected-lead safeguard must still be
visually and electrically verified before sensor commissioning. The 24 V valve
supply remains disconnected throughout that work.

## Architecture and authority

The application composition root owns a `TemperatureTelemetrySampler` in
`manual_timed` and `safe_drain` modes. The sampler calls the existing
`Max31865TemperatureSource` every five seconds and stores an immutable,
thread-safe snapshot containing the reading and sample time.

The existing `ControlService` remains the sole actuator authority. It does not
consume the sampler snapshot in either non-automatic mode. No telemetry method
can call an actuator driver or mutate a valve deadline.

Automatic mode keeps its current path: `ControlService` reads the production
temperature source and its `last_reading` supplies display telemetry. The new
background sampler is not started in automatic mode. This prevents concurrent
SPI transactions and preserves the existing automatic policy and commissioning
gate.

```text
MAX31865 -> TemperatureTelemetrySampler -> display status -> Waveshare UI

display action -> ControlService -> paired actuator -> GPIO 26/20
```

The two paths share no command interface. Operating mode is selected at process
startup, so there is no runtime transition that can leave both readers active.

## Sampler lifecycle and freshness

At process startup the cache is unavailable. The sampler starts within the
FastAPI lifespan only after the existing startup `DRAIN` completes. It performs
one immediate sample and then waits five seconds between sample starts. Shutdown
signals the sampler and joins it before the existing final `DRAIN` cleanup.

Every sample replaces the previous snapshot:

- a finite in-range `HEALTHY` reading stores its value and observation time;
- `INVALID`, `STALE`, calibration-required, SPI open/transfer failure, MAX31865
  fault, impossible ratio, or out-of-range result stores no displayable value;
- a failed read never leaves an earlier numeric value available;
- unexpected sampler-loop exceptions are caught, logged without secrets, and
  converted into an unavailable snapshot before the loop continues.

At serialization, a healthy snapshot older than 15 seconds is classified as
stale and its numeric value is withheld. Fifteen seconds represents three
missed five-second sample opportunities and applies only to display telemetry;
it does not replace the automatic policy's configured sensor staleness rule.

## Display API contract

The existing authenticated `GET /api/v1/display/status` response retains all
manual valve fields and adds these fields in every operating mode:

```json
{
  "pipe_temperature_c": 6.4,
  "sensor_health": "HEALTHY"
}
```

When no value is displayable:

```json
{
  "pipe_temperature_c": null,
  "sensor_health": "INVALID"
}
```

`sensor_health` uses the existing uppercase domain values `HEALTHY`, `STALE`,
`INVALID`, and `CALIBRATION_REQUIRED`. A snapshot expired by the 15-second
display rule is returned as `STALE`. Startup before the first sample returns
`pipe_temperature_c=null` and `sensor_health=STALE`. The display response
does not include the SPI device path, source identity, fault register, settings,
tokens, or administrator diagnostics.

Temperature serialization is independent from valve serialization. A missing
temperature cannot change `mode`, `state`, `command`, `remaining_seconds`,
`action`, or `action_enabled`.

## Waveshare parsing and presentation

The Waveshare valve status model gains an optional temperature value and a
health flag. The parser continues to require the complete, internally
consistent manual valve tuple. It parses the temperature fields independently:

- `HEALTHY` plus a finite numeric value in `-50..120 °C` is displayable;
- `null`, `STALE`, `INVALID`, `CALIBRATION_REQUIRED`, an out-of-range number,
  or a malformed optional temperature field becomes unavailable telemetry;
- unavailable telemetry does not invalidate an otherwise valid valve status;
- malformed core valve fields still produce the existing valve `FAULT` state.

The shower page places a small temperature label at the upper left, balanced
against the relay indicator and valve state at the upper right. It displays one
decimal place, replaces the C-locale decimal point with a comma, and appends
` °C`. The fallback is exactly `---`. It includes no PT100 name, freshness text,
or diagnostic text. The Roon page has no temperature element.

When the Pi connection or valve status is unavailable, the existing
`FAULT / Status unavailable` presentation remains authoritative and the
temperature shows `---`. When valve status is valid but temperature is not, the
valve controls retain their existing enabled/disabled behavior and only the
temperature changes to `---`.

## Safety and failure behavior

| Condition | Display outcome | Valve-control outcome |
| --- | --- | --- |
| Healthy fresh PT100 | One-decimal temperature | Unchanged manual control |
| MAX31865/PT100 fault | `---` | Unchanged manual control |
| Sampler exception or stale cache | `---` | Unchanged manual control |
| Pi communication loss | `FAULT`, status unavailable, `---` | Existing dial action gates apply |
| Pi process crash/hang | No fresh status; `---` | Physical safe outcome remains `NOT_VERIFIED` |
| Pi reboot | Startup unavailable, then new sample | Existing startup `DRAIN`; physical outcome remains separately evidenced |
| Power loss/restoration | No status, then startup sequence | Physical hydraulic outcome remains `NOT_VERIFIED` |

This feature does not close the four actuator fault-injection gates. GPIO state,
software command, relay contacts, valve position, and water routing remain
distinct evidence layers.

## Verification

### Raspberry Pi repository

Automated tests must prove:

- immediate sample, five-second cadence, clean stop, and no overlapping loop;
- healthy snapshot storage and 15-second display expiry;
- every sensor failure replaces an earlier numeric snapshot;
- sampler loop recovery after expected and unexpected read failures;
- sampler exists only for `manual_timed` and `safe_drain`;
- automatic mode uses only the existing `ControlService.last_reading` path;
- display status exposes only the two approved temperature fields;
- temperature health cannot change manual action fields or trigger the actuator;
- all existing manual timing, expiry, authorization, Nginx allowlist, paired
  GPIO, and persistence tests still pass.

### Waveshare repository

Host tests must prove:

- healthy, null, non-healthy, malformed, and out-of-range temperature handling;
- optional temperature failures do not invalidate valid valve state;
- one-decimal decimal-comma formatting and exact `---` fallback;
- temperature is visible only on the shower page;
- valve hold, immediate drain, stale-status, reconnect, settings gesture, Roon
  control, and page-switch regressions remain green.

Build the exact ESP32-S3 target with ESP-IDF 5.5.5. A successful build is source
evidence only; it is not display or hardware evidence.

### Hardware commissioning

1. Record Pi revision, mode, service state, exact breakout, PT100 wiring,
   reference resistor, and `/dev/spidev0.0` permissions.
2. Keep valve 24 V disconnected and both paired outputs in documented `DRAIN`.
3. Compare at least three stable room-temperature readings with an independent
   reference, then test around 0 °C and 8..10 °C as already specified.
4. Disconnect each PT100 lead and exercise permitted representative faults.
   Every case must remove the numeric display and show `---`; no old reading may
   survive.
5. Verify authenticated display JSON without recording the display token.
6. Flash the exact development firmware, verify its SHA and all flash regions,
   then visually confirm the shower-only temperature and fallback.
7. Leave the valves in `DRAIN`. Any energized valve or fault-injection test is a
   separate bounded approval and evidence session.

## Delivery and rollback

Pi and Waveshare changes use separate development branches and commits. The
released `v2.5.3-valve.1` firmware remains immutable. The Pi feature starts from
`v0.2.0-rc.1`; deployment is not claimed until the installed revision is read
back on the Pi.

Rollback restores the prior Pi service revision and the released Waveshare
firmware, then verifies service health, display connectivity, and documented
`DRAIN`. A software rollback does not by itself prove relay contacts, valve
position, or water routing.
