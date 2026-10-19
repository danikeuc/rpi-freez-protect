# gen4 display verification — 2026-10-18

Scope: application source/build checks in `firmware/gen4`. During these
checks no flash write occurred. The subsequent LCD-only bench upload, full
recovery verification and serial runtime receipts are recorded separately in
[BENCH.md](BENCH.md). No Pi connection, display-token provisioning, valve GPIO
command or physical valve test was performed.

## Executed host tests

All **18 Unity tests passed**, with zero failures and zero ignored tests.
They compile and execute the actual `src/model.cpp`, `src/action.cpp`,
`include/touch_sample.h` and `include/http_exchange.h`,
using ArduinoJson 7.2.1, Unity 2.6.1 and the Zig 0.13.0 bundled C/C++ compiler.

Covered: Hub JSON parsing, clearing old permission after invalid data,
safe/automatic start restrictions, stale and wraparound timing, pending-state
handling, release/hold/one-action gestures, cancellation on movement and
connection loss, action receipt matching, delayed-poll race, failed preflight,
no retry after a failed receipt, and expiry before/after preflight.
Additional regressions cover truncated/NACK touch reads, multi-touch and
coordinate rejection, GT ready/ACK handling, sample gaps, partial HTTP writes,
fragmented/delayed headers/body, absolute deadlines including clock wrap,
malformed/truncated/oversized responses, and connection changes before or
during action preflight. Transport tests use deterministic I2C/socket fakes
at the byte boundary; they do not establish hardware or live TCP behavior.

The missed-sample hold regression failed before the gesture fix (unexpected
START). The reconnect-within-TTL regression failed before the session fix
(unexpected accepted action). Both now pass. Independent review identified
these cases and the slow-response issue; final source review found no
remaining concrete critical or important defects. This is a source-review
result, not a deployment or hardware-safety certification.

The initial `python -m platformio test -e native` could not run because this
Windows workstation has no gcc/g++ on PATH. The same test sources were then
built and executed directly with the local Zig compiler:

```powershell
# Run from firmware/gen4 after PlatformIO has resolved native dependencies.
# Zig is installed in the ignored .pio/host-tools directory.
New-Item -ItemType Directory -Force .pio/build/native | Out-Null
& .pio/host-tools/ziglang/zig.exe cc -c .pio/libdeps/native/Unity/src/unity.c -I.pio/libdeps/native/Unity/src -o .pio/build/native/unity-host.o
& .pio/host-tools/ziglang/zig.exe c++ -std=c++11 -Wall -Wextra -Werror -Iinclude -I.pio/libdeps/native/ArduinoJson/src -I.pio/libdeps/native/Unity/src src/model.cpp src/action.cpp test/test_model/test_main.cpp .pio/build/native/unity-host.o -o .pio/build/native/gen4-tests.exe
& .pio/build/native/gen4-tests.exe
```

Zig emitted warnings in its own bundled unwind runtime. The application/test
translation units passed with `-Wall -Wextra -Werror`.

## Build and static checks

Both targets are checked with no secret header (offline setup image), and
with a separate ignored build configuration containing dummy network settings
and the documentation-only IP 192.0.2.1. The latter checks link the network
code that can otherwise be optimized out of an unconfigured image; they do
not execute any network request. Final source builds all exited zero:

| Target | Unconfigured image | Network-enabled link check |
| --- | --- | --- |
| gen4_28 | PASS (22.822 s) | PASS (50.167 s) |
| gen4_28ct | PASS (22.899 s) | PASS (50.116 s) |

The tested working tree is based on commit
`f1d284b32a0d5f521ad09391815073cd29b9f552`; the new support is uncommitted.
Local final logs are ignored build outputs: `.pio/review-build.log` and
`.pio/review-network-build.log`. An intermediate CT build failed because
`Pressed` collided with a vendor macro; the prefixed enum names fixed it,
and the four builds above verify the corrected sources. Network-check images are separate from
the normal unconfigured images and must not be used for commissioning.

- Markdown links in the changed README files resolve locally.
- CI workflow YAML parses.
- Patch/new-file whitespace checks pass.
- The added CI workflow runs host tests and both firmware configurations.
  It has not been executed on GitHub in this session.
- Python application code was not changed; the repository Python suite was
  not run (pytest is absent from this workstation's default interpreter).

## Limits

The manufacturer library emits compiler warnings, including NULL-to-integer
default arguments. It was not modified. Compilation is not proof of display,
touch, PSRAM, USB boot or Wi-Fi behavior on the connected unit.

User identification: 2.8-inch gen4. Earlier read-only USB inventory in this
conversation found COM7; USB descriptors did not identify the touch suffix.
PCB revision and CT/CLB markings remain unverified. At the initial source-check
stage application firmware had not been flashed or provisioned. Subsequent
inspection of the explicitly offline application is recorded separately in
[APPLICATION_BENCH.md](APPLICATION_BENCH.md); its shared LCD/FT path was selected
from the successful isolated diagnostics, not an asserted model suffix.
Later ROM-path recovery, verified LCD-only upload and successful serial
startup are recorded in [BENCH.md](BENCH.md). On 2026-10-19 the operator
confirmed the expected title, RGB bars, four corners and increasing uptime.
The later isolated touch-probe build/upload, valid pressed/released samples
and operator-confirmed diagonal drag alignment are recorded separately in
[TOUCH_PROBE.md](TOUCH_PROBE.md).

Network transport integration, all-edge touch accuracy,
holding/releasing at button edges, device restart and disconnect/reconnect
remain bench acceptance items in [README.md](README.md). Physical valve
position and power-failure behavior remain unverified.

## Read-only network compatibility update — 2026-10-19

After local credential entry, the existing Hub returned HTTP 200 but the
initial parser rejected its `weather_assisted` mode. That mode is also defined
in repository history at `c13adea`; no deployed revision is inferred from it.
The explicit allowlist now recognizes it for display, with manual/start
permission false. Unknown modes remain rejected. The new regression first
failed and then passed; the suite is now **19 tests, zero failures/ignored**.
Updated builds passed: provisioned `gen4_28` (56.938 s) and isolated
`gen4_28ct_offline` (52.512 s). Provisioned build logs and binaries are private
ignored files; their contents must not be published. No Python application
code changed. See [NETWORK_BENCH.md](NETWORK_BENCH.md) for the separate HTTP,
upload and operator-observation evidence. This does not accept CT controls.

## Bounded Wi-Fi reconnect check — 2026-10-19

The operator identified the module as gen4-ESP32-28CT. A separate read-only
network bench target adds one serial-triggered 30-second disconnect/reconnect
cycle, compile-time exclusion of touch controls and an independent POST block.
The schedule tests failed before implementation; review-driven false-recovery
regressions also failed before the fix. All **22 host tests** now pass.
The final diagnostic build passed in 31.531 s, and source review found no
remaining blocker. Device telemetry confirmed Wi-Fi/freshness loss within
1006 ms, sustained outage and fresh status after reconnection, with zero
POST attempts. See [RECONNECT_BENCH.md](RECONNECT_BENCH.md) for exact artifacts,
mutable-NVS verification, restoration and human-observation limits.

## Isolated 28CT test-Hub follow-up — 2026-10-19

The touch-enabled test target is pinned to a workstation in-memory fixture on
port 18081 with a separate test token and typed `simulated:true` response
check. The fixture has no valve or Pi connection. Two Node fixture tests and
24 C++ host tests passed; final read-only and test-target PlatformIO builds
passed. The final app preflight found no real Hub URL or token in the test
binary. A source-review finding about stalled touch frames was addressed by
a 100 ms freshness lease; a separate render timestamp error was corrected.
The fixed image was flashed app-only and independently ROM-verified. During
two subsequent captures there were no touch samples or action POSTs, so the
hold fix remains **unconfirmed on hardware**. The accepted read-only image
was then restored, ROM-verified (four digest matches) and hard reset. A
subsequent independent ROM verification again matched all four slices, and
the operator confirmed `UKAZ: DRAIN` and `SAMO PRIKAZ` on the restored screen.
See [TEST_HUB_BENCH.md](TEST_HUB_BENCH.md) for exact binary hashes, touch
observations and restoration evidence.

A later operator-synchronized test superseded the earlier no-touch windows:
the connected 28CT produced exactly one simulated START and one DRAIN,
with matching fixture POSTs and operator-observed SUPPLY then DRAIN. The
accepted read-only app was restored and ROM-verified afterward. See the
[operator-synchronized bench record](TEST_HUB_BENCH.md) for scope and limits.

## Current-main integration check — 2026-10-19

On a worktree based on the current `origin/main`, all 25 native model and
transport tests, two in-memory fixture tests, four unprovisioned firmware
builds, 654 Python tests, Ruff and the workflow/link validator passed. The
Python suite ran under WSL after normalizing checkout-only CRLF in the
commissioning helper; that helper is unchanged in the patch. Two DRAIN
statuses generated by the current Hub API (`safe_drain` and `manual_timed`)
were accepted by the gen4 parser without hardware or action POSTs. The parser
now accepts the Hub's 1800-second maximum outside manual mode while retaining
the manual 600-second limit. These results cover source compatibility and
workstation simulation, not a new upload or a physical valve test. The device
still has the earlier restored status-only image.

## Ordinary CT target action isolation — 2026-10-19

The provisioned ordinary `gen4_28ct` source previously included action
buttons and POST routes. This conflicted with the accepted status-only scope.
The compiled normal CT target now has no touch controls, action queue or POST
transport. The ordinary non-CT and network-bench targets are likewise
read-only; network action delivery remains only in `gen4_28ct_test_hub` for the
isolated in-memory fixture. The offline CT target retains disabled buttons
for UI inspection and cannot send actions. A new binary check first failed on the old
provisioned CT image because it contained the timed-shower route. After the
change, all five provisioned/diagnostic PlatformIO builds passed, and the
binary check found no action routes or POST method in four ordinary images,
and no action button labels in the normal CT image, while confirming both in
the isolated test image. CI now repeats the check
after linking with dummy network settings, so unprovisioned optimization
cannot mask an action path. This is source and binary evidence only; the
connected device was not reflashed for this change and remains on the earlier
ROM-verified `SAMO PRIKAZ` image.
