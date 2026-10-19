# Isolated gen4 touch diagnostic - 2026-10-19

Status: **v2 flashed and verified; basic touch and drag alignment confirmed**.
See the final section for serial evidence and the operator's confirmation.
Earlier sections retain the initial negative observations and diagnostic steps.
The operator could identify the module only as 2.8-inch gen4. Exact suffix and
PCB revision remain unknown. No Pi/Hub connection or valve command occurred.

## Version 1 boundary and implementation

`gen4_28_touch_probe` compiles only `src/touch_probe.cpp`. Production targets
exclude it. The diagnostic includes no credentials, Wi-Fi or action code.
It uses the shared LCD class already confirmed visually by the operator.
SDA 10 / SCL 9 are traced to the pinned manufacturer's
`gfx4desp32_spi_panel_t.cpp`, commit
`2a36bda388985608a0d5ea64746f5d1b100d268b`.
Only addresses 0x38, 0x5d and 0x14 are probed; mask bits are 1, 2 and 4.
Only a single address response selects the existing checked TouchReader.
No touch reset/interrupt pins or controller configuration are written.
GT frame consumption acknowledges the ready register; FT frames are read.
An ACK is a protocol candidate, not an exact module identification. No ACK
would be inconclusive because this probe intentionally omits reset/config.

## Source and build verification

Independent source review found no blocking defects or unintended network or
control paths. All four environments built successfully after source-filter
changes, using the pinned dependencies and PlatformIO 6.2.0:

| Environment | Result | Duration |
| --- | --- | --- |
| gen4_28 | PASS | 58.872 s |
| gen4_28ct | PASS | 49.250 s |
| gen4_28_bench | PASS | 41.247 s |
| gen4_28_touch_probe | PASS | 51.439 s |

Log: ignored `.pio/touch-probe-build.log`. Upstream library warnings remain.
CI YAML and tracked patch whitespace checks passed. CI now builds the probe;
GitHub CI was not executed. The application and TouchReader logic were not
changed; the prior 18 host tests are recorded in [VERIFICATION.md](VERIFICATION.md).

## Device and recovery gates

COM7 re-enumerated as USB VID 303A / PID 1001. ROM readout confirmed the same
ESP32-S3 MAC `cc:8d:a2:0c:f0:b8`. Secure Boot and flash encryption were both
reported disabled. Commands used esptool 5.3.0, Python UTF-8 mode, 115200 baud,
`--no-stub`, with flash header parameters preserved. No erase-all/eFuse writes.

The complete pre-bench recovery image from [BENCH.md](BENCH.md) was retained
and its SHA-256 rechecked before this upload. A second recovery file holds
the accepted LCD bench: `.pio/recovery/lcd-bench-20261018.bin`, 527,216 bytes,
read from the device in 32.7 s and matching the original artifact SHA-256
`2069d6c9af15b8d8934a75ba1bc6b97bd674b490f7ea9afca69c30c26deff225`.
Both files are local and ignored by Git; never print, attach or commit them.

An initial verify command could not open the previous build artifact while
PlatformIO rebuilt its directory; it failed argument validation before
connecting to hardware. The direct ROM read above then independently verified
and preserved the installed LCD image. Recovery copies live outside rebuildable
`.pio/build/` directories.

## Upload and serial receipts

Uploaded `.pio/build/gen4_28_touch_probe/firmware.factory.bin` at offset 0.
Length: 528,224 bytes. SHA-256:
`da928ee70ee23f12e5f798d61144c4d8a60e0ce7f7344f4046841b704e5117bf`.

- ROM write: exit 0; 7.0 s transfer; written-data hash verified.
- Separate verify: exit 0; 2.03 s; digest matched.
- Reset: ROM flash-id with hard-reset completed successfully.
- A bounded 15-second serial capture accepted only exact diagnostic records.
  It observed `mask=1 bus=1`, so only 0x38 responded. Released-frame samples
  increased from 0 to 190; pressed, invalid and waiting counters remained 0.
  This demonstrates the candidate FT-compatible protocol returning valid
  no-contact frames, not yet a physical tap or alignment acceptance.
- A subsequent 45-second capture (`touch-probe-interaction.log`) observed
  released increasing to 1180 with pressed/invalid still zero. No operator
  confirmation of tapping arrived during this interval; it does not establish
  a failed touch test. Documentation links and whitespace checks passed.

Logs under ignored `.pio/recovery/`: `read-current-lcd-bench.log`,
`before-touch-security.log`, `write-touch-probe.log`, `verify-touch-probe.log`,
`reset-touch-probe.log` and `touch-probe-serial.log`.

## Remaining observations

The operator was asked to touch the center and all four corners, releasing
between points, and confirm coordinate/green-marker alignment. The operator
answered "ne" (no). A fresh 15-second capture (`touch-probe-after-no.log`)
then observed pressed=0, invalid=0 and released increasing to 2064. Version 1
therefore has no demonstrated physical touch response. The working I2C reads
do not establish that the touch surface is sensing a finger.
P/R/E counters count samples, not taps. A GT waiting frame may hide the marker
between ready frames; coordinates and counters are also diagnostic evidence.
Do not infer PCB revision or distinguish CT from CT-CLB from I2C alone.
Application firmware is not flashed/provisioned. Network, deliberate action,
fault/recovery and physical-valve acceptance remain separate tasks.

## Version 2 reset diagnostic

After the negative physical observation, comparison with the pinned vendor
`gfx4desp32_spi_panel_t.cpp` found that version 1 omitted its FT reset sequence.
That is a hypothesis for the missing touch response, not an established cause.
Version 2 applies that sequence only after the unique 0x38 response: GPIO 11
low for 100 ms, then high for 50 ms, GPIO 8 input followed by input/pullup.
No controller configuration register or network/action code was added.
Read-only snapshots cover registers 0x00, 0xa3, 0xa6, 0xa8 and 0xa5 (mode,
chip/cipher, firmware, vendor and power). Register meanings were checked in
[Espressif's FT5x06 driver](https://github.com/espressif/esp-bsp/blob/master/components/lcd_touch/esp_lcd_touch_ft5x06/esp_lcd_touch_ft5x06.c).
Any failed post-reset read disables sampling. Successful reads alone do not
prove identity or readiness. Independent source review found no blocker.

- Build: PASS, `gen4_28_touch_probe`, 27.192 s; log `.pio/touch-probe-v2-build.log`.
- Before upload, the installed v1 image was independently digest-verified,
  with the same MAC observed. Its artifact was preserved as ignored
  `.pio/recovery/touch-probe-v1.bin`; the full recovery hash was rechecked.
- Version 2 factory image: 528,688 bytes, SHA-256
  `cb2c8f32c764e629957f839df8f3d0989fa271a46b11d11c9ea3bd4681201b49`.
- ROM write at offset 0: exit 0, 7.0 s transfer, written hash verified.
  Separate `verify-flash`: digest matched. Reset then bounded serial capture
  completed with exit 0. Flash mode/frequency/size headers were preserved.
- Serial observed version 2, mask=1, bus=1 and reset=1. Before-reset values
  were `0,100,2,17,1`; the immediate post-reset snapshot was `0,0,0,0,0`.
  These are decimal bytes, not an exact-module identification. The after
  snapshot was taken after 50 ms and is stored, not refreshed; zero IDs could
  reflect startup timing and must not be treated as a confirmed controller ID.
- Initial released count reached 190, with pressed/invalid both zero. The
  operator was asked to hold the center for three seconds, release, then touch
  one corner on the `GEN4 DOTIK V2` screen. Physical response remains pending.

Version 2 logs under ignored `.pio/recovery/`: `before-v2-verify-v1.log`,
`write-touch-v2.log`, `verify-touch-v2.log`, `reset-touch-v2.log` and
`touch-v2-serial.log`. `reset=1` records that firmware executed the pin sequence;
it does not prove electrical reset or a repaired touch surface.

A further 45-second capture (`touch-v2-interaction.log`) ended at released=1114,
pressed=0, invalid=0. No new operator answer arrived during this capture.
This leaves post-reset physical touch response unresolved. Final patch,
source whitespace and local documentation-link checks passed.

## Confirmed basic touch and alignment - 2026-10-19

After the operator mentioned coordinates, a fresh 15-second capture
(`touch-v2-coordinates.log`) observed pressed=4, invalid=0 and last x=151,
y=180; released increased from 1348 to 1576. These are cumulative sample
counts, not four distinct taps. This confirms valid pressed samples followed
by released samples in v2. It does not by itself establish sustained holds.

The operator then explicitly answered "Da, sledi pravilno" to the instruction
to drag from the upper-left corner to the lower-right and back and confirm
that the green marker follows the finger at the correct position. This is
human-observed basic alignment evidence, separate from the serial capture.
LCD and basic touch/drag alignment are confirmed for the isolated diagnostic.
All-edge accuracy, multi-touch rejection, hold-to-act behavior, restart/power
cycles and network/control integration remain separate acceptance items.
The observation supports the FT-compatible touch path but does not establish
an exact PCB revision/CT-CLB suffix or prove the reset was the sole cause.

The 45-second capture during the alignment prompt (`touch-v2-alignment.log`)
ended at pressed=37, released=2468, invalid=0, last x=62/y=236. Together with
the explicit operator confirmation, it supports basic touch/drag response.
Documentation link and whitespace checks passed after recording this result.
