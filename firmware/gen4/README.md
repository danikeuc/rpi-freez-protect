# 4D Systems gen4-ESP32 2.8-inch display

Additional display firmware for Freeze Protect. This is repository support,
not evidence that it is installed or commissioned. The existing Waveshare
installation remains the active installation recorded in
[PROJECT_STATE.md](../../docs/PROJECT_STATE.md).

## Targets and dependencies

| Environment | Module | Input |
| --- | --- | --- |
| `gen4_28` (default) | gen4-ESP32-28, 240 x 320 portrait | Read-only status display |
| `gen4_28_bench` | Shared 2.8-inch LCD, 240 x 320 portrait | Offline colors/edges/memory/uptime; touch disabled |
| `gen4_28_touch_probe` | Shared LCD plus internal CTP bus | Offline address/coordinate diagnostic; documented FT reset, no configuration writes |
| `gen4_28_network_bench` | Shared LCD, read-only network client | One serial-triggered 30-second Wi-Fi outage, numeric telemetry, all POSTs blocked |
| `gen4_28ct_offline` | Shared 2.8-inch CT application layout | Offline application/touch inspection; ignores secrets and disables networking/actions |
| `gen4_28ct_test_hub` | 28CT test application | CT gestures against an isolated in-memory Hub fixture on workstation port 18081; fixed test token and visible simulation banner |
| `gen4_28ct` | gen4-ESP32-28CT / 28CT-CLB | Capacitive touch; confirm hardware and complete isolated acceptance before provisioning |

The 2.8-inch family uses ESP32-S3, 16 MB QIO flash and 8 MB OPI PSRAM. USB enumeration alone
does not identify the LCD or touch variant. The user identified the connected
unit as gen4-ESP32-28CT on 2026-10-19, after the basic LCD/touch tests.
The model identification is operator-provided; the PCB revision remains unverified.

The board driver is the manufacturer's GFX4dESP32 library, pinned to commit
`2a36bda388985608a0d5ea64746f5d1b100d268b` (1.3.0).
Its board-specific initialization selects the LCD revision and owns the
touch reset/detection. A checked FT/GT I2C reader supplies portrait coordinates
using the same mapping; cached vendor touch state is never used for actions.
There is no copied CrowPanel pin map.

- [Module datasheet](https://resources.4dsystems.com.au/datasheets/esp32/gen4-esp32/)
- [Manufacturer library](https://github.com/4dsystems/GFX4dESP32/tree/2a36bda388985608a0d5ea64746f5d1b100d268b)
- [Pinned board definition](https://github.com/4dsystems/GFX4dESP32/blob/2a36bda388985608a0d5ea64746f5d1b100d268b/src/gfx4desp32_gen4_ESP32_28CT.h)

Platform: pioarduino `55.03.311`; Arduino-ESP32 `3.3.11`, matching the
manufacturer's stated tested core. Libraries: SdFat `2.3.0`, ArduinoJson
`7.2.1`. GFX4dESP32 is Apache-2.0; retain its bundled notices when distributing.

| Onboard function | ESP32 GPIO / interface |
| --- | --- |
| LCD | SPI MOSI 13, MISO 12, clock 14, DC 21, reset 7; no GPIO CS |
| Backlight | GPIO 4, managed by the manufacturer's driver |
| Capacitive touch (CT target only) | I2C SDA 10, SCL 9; manufacturer's reset/detection sequence |
| USB | Native USB on GPIO 19/20; never used as valve outputs |

These are display-module pins, not Raspberry Pi BCM numbers. No external
relay/sensor wiring is needed. The module is nominally 5 V with 3.3 V logic.
Use its USB-C connection for the initial unprovisioned bench inspection.

## Build and configure

From this directory, with PlatformIO Core available:

```text
python -m platformio test -e native
python -m platformio run -e gen4_28 -e gen4_28ct
```

Native tests require a host C++ compiler on PATH. Both firmware targets build
without any secret file; the resulting image shows a setup screen and sends
no network requests. For a provisioned build, copy
`include/secrets.example.h` to the ignored `include/secrets.h` and edit it
locally. Use Wi-Fi credentials, the trusted-LAN Nginx URL on port 8081 and only
the display token. The URL must be `http://<LAN-IPv4>:8081` (an optional
trailing slash is accepted). Hostnames, HTTPS and URL path prefixes are not
supported: numeric IP avoids unbounded DNS resolution. Reserve the Hub's
LAN address in DHCP. Do not use the Hub's loopback address or admin token.
Never paste credentials into chat, logs or Git. Do not copy the retired
CrowPanel's credentials.

Do not infer upload authorization from these build commands. Review
[workstation commissioning](../../deployment/WORKSTATION_CODEX_COMMISSIONING.md)
and [its focused prompt](../../deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md)
before any upload. Confirm the touch suffix and PCB marking, preserve the
existing firmware/provisioning recovery path, then use the corresponding
target on the verified port. Firmware builds and uploads remain workstation
operations; the restricted Pi account has no firmware privileges.

## Isolated LCD bench image

Build with `python -m platformio run -e gen4_28_bench`. This environment
compiles only `src/bench.cpp`; it cannot include credentials or the application
network/action code, even if a local secret header exists. The manufacturer
28 and 28CT classes use the same LCD pin definitions and initialization.
The bench image does not initialize or identify touch.

Expected screen: portrait white border and TL/TR/BL/BR corner labels, red,
green and blue bars, `BREZ OMREZJA`, memory sizes and an updating uptime.
Fixed serial messages `GEN4_BENCH_READY` / `GEN4_BENCH_ALIVE` confirm code
execution only. A human must separately confirm the visible picture.

Before replacing an existing image, verify chip identity, flash capacity,
Secure Boot/encryption status, and save/verify a full flash recovery image.
Recovery files belong only in ignored `.pio/recovery/`; they may contain
credentials and must never be printed, attached or committed. Preserve them
until the replacement has been accepted. See [bench evidence](BENCH.md) for
the actual device record and remaining checks.

## Isolated touch diagnostic

Build with `python -m platformio run -e gen4_28_touch_probe`. This target
compiles only `src/touch_probe.cpp`, with no secrets, network or action code.
It uses the already-tested shared LCD class and the internal CTP bus
(SDA 10 / SCL 9), traced to the pinned manufacturer's
`gfx4desp32_spi_panel_t.cpp`. It sends address probes only to 0x38, 0x5d and
0x14. The mask bits are 1, 2 and 4 respectively. Only one responding address
selects the existing checked FT/GT frame reader. Multiple responses stop
sampling; no response is inconclusive, not proof of a non-touch variant.

Version 2 adds the pinned manufacturer's FT reset sequence only after a
unique 0x38 response: reset GPIO 11 low for 100 ms, then high with 50 ms
settling, and interrupt GPIO 8 as input/pullup. FT mode/ID/firmware/vendor/power
registers are read before and after reset; failed reads disable sampling.
No touch configuration is written. GT sampling acknowledges consumed frames
by clearing ready status; FT sampling only selects/reads registers. An address ACK
identifies a candidate protocol, not an exact model or PCB revision. The
screen shows coordinates, a green marker while pressed, and sample counters
(P pressed, R released, E invalid). Fixed `GEN4_TOUCH_PROBE` serial records
repeat every two seconds. Counters measure samples, not distinct taps.

Observe taps, release and marker alignment at the four corners and center.
Unknown identity, missing/invalid responses or incorrect coordinates must
not be promoted into application-control acceptance. This isolated probe
uses the same recovery and upload gates as the LCD bench image. See the
[touch diagnostic record](TOUCH_PROBE.md) for actual upload and runtime evidence.

## Offline application inspection

Build with `python -m platformio run -e gen4_28ct_offline`. This uses the actual
application UI and touch reader after the LCD and isolated FT touch tests.
`GEN4_OFFLINE_BENCH=1` excludes `secrets.h` even when present and forces
`configured=false`; no Wi-Fi setup, queues or network worker can start.
The model has no valid Hub status, so both touch commands remain disabled.
The screen labels this mode `OFFLINE PREIZKUS` and shows setup guidance.

Fixed serial records `GEN4_APP_READY` and `GEN4_APP_BENCH` report only mode,
uptime and pressed/invalid/action counters. Counters measure samples, not taps.
This is evidence for application startup and offline input handling only;
it cannot validate enabled holds, API traffic or physical outputs. See the
[application bench record](APPLICATION_BENCH.md) for evidence and remaining gates.
The working FT protocol and LCD pin path justify this isolated inspection;
they do not establish the exact CT/CLB suffix or PCB revision.

## First network observation without controls

After the offline inspection, `gen4_28` can be used on the tested shared LCD
path, including this CT-capable unit, for a status-only connection to the
selected Hub. Its `GEN4_TOUCH=0` excludes touch handling and the only action
queue producer. The screen shows `SAMO PRIKAZ`; there are no action buttons.
This stage validates status reception only. It does not accept touch controls
or replace the isolated fake-Hub and commissioning gates before control use.
See [read-only network evidence](NETWORK_BENCH.md).

`gen4_28_network_bench` is a temporary acceptance target: once fresh status is
available, serial `n` triggers one 30-second Wi-Fi disconnect on this display
and one recovery attempt. It cannot compile with touch controls enabled and
also rejects POSTs before transmission. Numeric phase/status telemetry allows
a bounded host capture without credentials. Restore the accepted normal
read-only app afterward. See [reconnect evidence](RECONNECT_BENCH.md), including
why app-only writes preserve the mutable NVS partition after network use.

## Isolated CT action test

`gen4_28ct_test_hub` keeps the locally provisioned Wi-Fi connection but
overrides the Hub URL and display token after loading the local secrets header.
Its URL is fixed to the reviewed workstation address in
`include/test_hub_config.h` for this bounded bench session. The build rejects a
non-CT or conflicting diagnostic configuration; runtime accepts only port
18081. A changed workstation address requires reviewing and rebuilding this
test target. Every accepted response must contain the typed JSON marker
`"simulated":true`. This marker checks the response contract; it is not a
cryptographic identity proof, so keep this target confined to the private bench
LAN and restore the read-only app after testing. The screen labels this mode
`SIMULACIJA - BREZ VENTILOV`.

The workstation fixture is `tools/test-hub.mjs`. It binds an explicit
private IPv4, accepts only its fixed test token, keeps the 600-second timer in
memory, never contacts the real Hub, and stops after 20 minutes. The control
file selects `normal`, `reject`, `unauthorized`, `malformed` or `slow`
mode. Traces count accepted requests and in-memory state without logging
tokens. Run `node --test tools/test-hub.test.mjs` before use. Preserve
bootloader, partitions, OTA data and mutable NVS: replace only the app at
`0x10000` after the recovery and immutable-slice checks in
[reconnect evidence](RECONNECT_BENCH.md). Restore the accepted read-only app
after this bounded test. A simulated SUPPLY indication is only fixture state;
it says nothing about Pi GPIO or valve position.

## Behavior and authority

The UI labels the Hub's logical command as `UKAZ: DRAIN/SUPPLY`. It does not
claim to measure valve position. The countdown is a local display estimate
from `remaining_seconds`; reaching zero never issues a command or invents
a confirmed DRAIN state.

The CT version requires release after boot, then a continuous two-second
hold on the start button. Moving away, losing valid status, pending requests
or a changed action cancels the gesture. A failed/short touch read, multiple
contacts, out-of-range coordinates or a sample gap above 100 ms cancels and
disarms the hold until a verified release. A separate IZPUST button requests
DRAIN. Holding a button sends at most one action until release. The non-touch
target offers status viewing only. This firmware does not implement Roon or
the forecast page.

Only the existing display API is used, with `X-Display-Token`:

| Request | Purpose |
| --- | --- |
| GET /api/v1/display/status | Poll every two seconds |
| POST /api/v1/display/actions/timed-shower | Bodyless, deliberate start |
| POST /api/v1/display/actions/drain | Bodyless, deliberate drain |

Start is enabled only for fresh, explicitly permitted MANUAL_DRAIN in
manual_timed mode. `weather_assisted` is explicitly accepted for status
viewing and never grants START. Other modes remain display-only for starting; DRAIN
remains available with fresh status. The Hub chooses the fixed 600 seconds.
Before start, firmware rechecks Hub permission. Queued requests expire after
one second; a start preflight must finish within three seconds of the gesture.
POSTs are never retried or persisted. Wi-Fi disconnect events invalidate the
connection generation: queued and in-flight intent is rejected before
preflight, before POST and before each socket read/write after reconnection.
The gesture also requires a new verified release. Failed/nonmatching receipts invalidate
the display state; periodic GETs may reconcile it without resending the action.

HTTP runs in a separate task so network waits do not block touch handling.
TCP connect is limited to one second; the entire exchange has a two-second
deadline, including partial writes and fragmented headers/body. I/O is
nonblocking, and cleanup closes rather than drains the socket. Redirects
and chunked encoding are rejected. Headers are capped at 2048 bytes total
and 255 bytes per line. Status must be younger than five seconds measured
from request start. Responses need HTTP 200, Content-Length
of 1..4096 bytes and a valid typed JSON contract. Oversized, truncated,
unauthorized or malformed responses fail closed. An older poll cannot clear
the pending state of a newer action.

## Failure boundaries and hardware acceptance

Legal Pi outputs remain paired high/high for DRAIN and low/low for SUPPLY;
mixed levels are illegal. This firmware has no Pi GPIO interface.

| Fault | Required behavior / enforcer | Verification boundary |
| --- | --- | --- |
| Display-Hub communication loss | UI becomes unknown and disables start within five seconds (immediate on observed Wi-Fi loss). A manual shower started by this display remains bounded by the Hub's 600-second timer; other Hub modes can report up to 1800 seconds. Reconnect never replays a start. | Host tests cover stale logic and request expiry; network/device tests pending. |
| Display crash/hang; Hub crash/hang | Display cannot renew or extend a shower. Hub bounds it; if Hub renewal stops, existing daemon lease requests DRAIN within 60 seconds. | Existing controller design; new display crash/lease observation not performed. |
| Display or Pi reset | Display boots without a queued action and requires release before touch control. Pi controller is designed to start at paired DRAIN. | Gesture/model tests only; startup electrical behavior not measured here. |
| Loss/restoration of display, Pi, relay or valve power | Display restart sends no automatic command. Physical DRAIN after loss of other power domains is not established by display software. | Physical fail-safe behavior remains UNKNOWN; use the project evidence ledger and separately approved tests. |

First inspect an unprovisioned image: readable portrait layout, colors,
orientation and (CT only) touch alignment at all edges, including release
and hold behavior. Then use an isolated fake Hub to check 401/409, malformed
JSON, delayed replies, disconnect/reconnect and one POST per deliberate
gesture before provisioning the real controller.

Keep the 24 V valve supply disconnected. Any real timed-shower/GPIO
acceptance requires explicit current-conversation approval and all documented
service, paired-output and deployed-flow gates. Stop on failed evidence;
do not retry SUPPLY. Actual valve movement and power-failure behavior need
their own bounded physical test. No hardware acceptance is claimed by a
successful build.
