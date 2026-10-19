# gen4 LCD bench verification - 2026-10-18

Status: **LCD-only image flashed and verified; serial runtime confirmed**.
This is the LCD-only stage record. On 2026-10-19 the isolated
[touch diagnostic](TOUCH_PROBE.md) replaced it; the accepted LCD image was
read back, hash-verified and retained locally for recovery.
A full 16 MB recovery image was read through the ROM path and verified against
the device before writing. On 2026-10-19 the operator confirmed seeing the
expected title, RGB bars, all four corner labels and increasing uptime.
No Pi connection, Hub request, valve GPIO command or valve test was performed.

## Device observations

The operator identified the module as 2.8-inch gen4. COM7 enumeration and
esptool 5.3.0 produced:

| Item | Observation | Limit |
| --- | --- | --- |
| USB | VID 303A / PID 1001, USB-Serial/JTAG, COM7 | Does not identify display/touch suffix |
| Chip | ESP32-S3 QFN56, silicon revision v0.2 | PCB revision remains unknown |
| MAC | cc:8d:a2:0c:f0:b8 | Device identity for this session |
| Flash | 16 MB, manufacturer c8, device 4018, quad, 3.3 V | Identification only |
| PSRAM | Embedded 8 MB AP_3v3 reported by chip identification | No memory integrity test |
| Secure Boot / flash encryption | Both disabled; crypt count 0 | Read-only security query; no eFuse changes |

The 28 and 28CT manufacturer sources share LCD pin definitions and
`gfx4desp32_gen4_ESP32_28_Init.h`. The bench target uses only that shared LCD
path; it does not infer or initialize touch. CT/CLB marking remains unknown.

## Prepared artifact

Environment: `gen4_28_bench`, compiling only `src/bench.cpp`.
It draws a border, corner labels, RGB bars, memory sizes and uptime.
It does not include secrets, application control code, Wi-Fi startup or Hub
requests. Fixed serial output is limited to bench identity, memory and uptime.

- Build: PASS, 50.356 seconds.
- Production targets rebuilt after source-filter change: `gen4_28` PASS
  (52.890 s), `gen4_28ct` PASS (46.851 s).
- Independent read-only source review: no blocking defects or unintended
  control/network paths found in the bench source/configuration.
- Local factory image: `.pio/build/gen4_28_bench/firmware.factory.bin`.
- SHA-256: `2069d6c9af15b8d8934a75ba1bc6b97bd674b490f7ea9afca69c30c26deff225`.
- CI now includes the bench build. GitHub CI was not run in this session.

## Recovery-read investigation

The initial attempts below used only chip/security queries and flash reads.
The RAM flasher stub was temporarily loaded by esptool. Persistent flash was
not changed until the recovery and upload gates in the next section passed.

1. Full 16 MB read at 921600: failed with serial data stream stopped.
2. 4096-byte probe at 115200: reached progress reporting, then failed with
   Windows cp1252 UnicodeEncodeError. This was not a completed backup.
3. Full read at 115200 with Python UTF-8 mode: reached 270336 bytes, then
   failed with chip stopped responding.
4. 1 MB probe with explicit stub version 2 and silent output: also failed
   with chip stopped responding. This did not yield a verified recovery file.
5. ROM-only flash identification (`--no-stub`) succeeded, followed by
   `--after hard-reset`; esptool reported hard reset and exit zero.
   The original application's visible startup was not observed.

These initial attempts produced no complete recovery binary. After the
operator confirmed the requested cable/reconnection step, COM7 and the same
MAC were identified again. A 1 MB stub-based probe still failed (exit 2,
6.12 s). A ROM-only 16 KB probe succeeded (exit 0, 2.06 s), so the full backup
used the same ROM path. This isolates a working transfer path; it does not
establish the precise cause of the stub failure.

Local logs and the recovery binary are under ignored `.pio/recovery/`.
Never print, attach or commit the recovery binary: it may contain provisioning
data. The full-read, length/hash and device-verification gates below passed
before the first flash write.

Espressif documents the ROM-only diagnostic path in its
[flasher-stub guide](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/flasher-stub.html).
A [reported ESP32-S3 read regression](https://github.com/espressif/esptool/issues/1155)
was considered, but its suggested stub-version change did not resolve this
device's read failure. The local root cause remains unknown; it is not
established that the cable, display or flash is faulty.

## Recovery, upload and runtime receipts

All device commands used esptool 5.3.0, Python UTF-8 mode, COM7, ESP32-S3,
115200 baud and `--no-stub`. No erase-all or eFuse operation was issued.

1. `read-flash 0 0x1000000`: PASS, exit 0, 1072.9 s transfer.
   Recovery file: `.pio/recovery/cc8da20cf0b8-before-bench-20261018.bin`.
   Length: 16,777,216 bytes. SHA-256:
   `d46e93b97c4933ec3dabcd5024d2bff560cf01dca0d5f77e08f15103370ed293`.
2. Separate `verify-flash 0 <recovery>`: PASS, digest matched, exit 0,
   30.37 s. Recovery and bench hashes were rechecked before writing.
3. `write-flash --flash-size keep --flash-mode keep --flash-freq keep
   --no-compress 0 <bench factory image>`: PASS, 527,216 bytes at offset 0,
   transfer 7.0 s, written-data hash verified, exit 0. The ROM stayed in
   bootloader after writing; no application had run during verification.
4. Separate `verify-flash 0 <bench factory image>`: PASS, digest matched,
   exit 0, 2.04 s. Header parameters were preserved, matching the artifact
   SHA-256 recorded above.
5. ROM flash identification with `--after hard-reset`: PASS. A 15-second
   serial capture accepted only exact bench protocol lines:
   `GEN4_BENCH_READY v1 width=240 height=320 flash=16777216 psram=8388608`,
   followed by seven ALIVE messages with uptime 2, 4, 6, 8, 10, 12 and 14 s.
   This confirms execution and reported memory sizes, not memory integrity
   or visible LCD output. Unrecognized serial lines were discarded.

Receipts: `.pio/recovery/read-full-rom.log`, `verify-full-rom.log`,
`write-bench-rom.log`, `verify-bench-rom.log`, `reset-after-bench.log` and
`bench-serial-filtered.log`. The recovery image is local and Git-ignored;
restoration has not been exercised. Any future restoration must reidentify
the device, verify this hash and use the complete image at offset 0 while
preserving its header settings. Do not restore or erase as a diagnostic retry.

## Remaining acceptance

On 2026-10-19 the operator answered "ja" to the request to confirm
"GEN4 2.8 TEST", red/green/blue bars, all four corner labels and increasing
uptime. This is operator-observed LCD evidence, separate from the earlier
serial receipts; no screenshot or color measurement was captured.
Touch identification/alignment, application network integration
and valve commissioning remain separate steps. The application firmware
has not been flashed. Keep the 24 V valve supply disconnected; no live valve
test is authorized by this bench record.
