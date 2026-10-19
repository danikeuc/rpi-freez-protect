# Offline application bench — 2026-10-19

Scope: the connected 2.8-inch gen4 after accepted LCD and basic FT touch tests.
The operator chose the same existing Freeze Protect Hub for later provisioning.
No Wi-Fi credentials or display token have been entered by this task. No Pi,
Hub API, GPIO or valve command is part of this offline inspection.

## Build boundary

`gen4_28ct_offline` compiles the application with `GEN4_OFFLINE_BENCH=1`.
This excludes `secrets.h`, forces `configured=false`, and creates no Wi-Fi
connection, request queue or network worker. Invalid initial Hub status
keeps both touch actions disabled. It uses the actual application renderer
and checked touch reader. UI label: `OFFLINE PREIZKUS`.

- All 18 actual-source Unity host tests passed again with Zig 0.13.0.
- A fresh separate build with a poisoned `secrets.h` (`#error`) passed for
  the offline environment in 59.588 seconds.
- Negative control: the regular CT environment with that same include path
  failed with the exact injected error. The header exclusion test is effective.
- CI now forces a clean offline build with a poisoned local header; the
  GitHub workflow itself has not been run in this session.
- Independent review found no blocking defect in the offline branch.

Normal source builds passed: `gen4_28` (49.600 s), `gen4_28ct` (48.426 s),
and `gen4_28ct_offline` (48.300 s). Log: `.pio/application-build.log`.
The normal offline build, not the poison-header or dummy-network build, is
preserved as `.pio/recovery/application-offline-v1.bin` (617376 bytes).
SHA-256: `51db2dd3c8071e8da088af521c034863c4a0719cf76e8a1ed62f7a447c2267e2`.

## Device evidence

COM7 ROM connection reidentified ESP32-S3 rev 0.2, MAC
`cc:8d:a2:0c:f0:b8`, Secure Boot disabled and flash encryption disabled.
The full 16 MB recovery file and touch-probe v2 file hashes were rechecked;
the device's current flash also matched the v2 image before replacement.
See [TOUCH_PROBE.md](TOUCH_PROBE.md) and [BENCH.md](BENCH.md) for recovery hashes.

The offline application was written through esptool 5.3.0's ROM path
(`--no-stub`, no compression, keep flash header settings) at offset 0.
617376 bytes were written in 8.5 seconds with matching write digest.
A separate `verify-flash` command also passed (digest matched); only then
was a hard reset requested. Logs: `.pio/recovery/application-offline-write.log`,
`application-offline-verify.log`, and `application-offline-reset.log`.
The bounded serial startup capture passed, including
`GEN4_APP_READY v1 touch=1 configured=0 worker=0 offline=1`.
Four increasing uptime samples (5001 through 20004 ms) reported
`pressed=0 invalid=0 actions=0 configured=0 worker=0`.
Log: `.pio/recovery/application-offline-startup.log`.
This confirms code execution and the offline configuration. Separately, the
operator confirmed the expected FREEZE PROTECT / OFFLINE PREIZKUS /
TUS NI NA VOLJO display and reported that neither lower button had an effect
after being asked to hold each for about three seconds. This accepts the
visible offline layout and observed lack of action, not enabled control.
A subsequent 45-second capture observed pressed samples rising from 84 to 108,
zero invalid samples and zero generated actions; configuration and worker
remained zero. Log: `.pio/recovery/application-offline-buttons.log`.

Both network-enabled link checks with dummy settings also passed:
`gen4_28` (50.087 s) and `gen4_28ct` (50.437 s).
Log: `.pio/application-network-build.log`. These images were not uploaded;
the settings use documentation-only 192.0.2.1 and no real credentials.

## Remaining acceptance

The visible offline layout and disabled-button inspection passed. Enabled
holds still require separate acceptance. Before provisioning the live Hub,
complete isolated fake-Hub transport and gesture acceptance described in
[README.md](README.md). An ignored `include/secrets.h` template was created
without overwriting any existing file, with empty credential fields and the
Hub URL documented in `deployment/DISPLAY_COMMISSIONING.md`:
`http://192.168.114.192:8081`. That address has not been checked live here.
The operator must enter Wi-Fi credentials and the dedicated display token
locally, never in chat or captured logs. The offline image ignores this file.
Exact model suffix/PCB revision, all-edge accuracy, live network behavior and
physical valve behavior are still unverified. Keep 24 V disconnected; timed
physical/GPIO tests require their own explicit approval and commissioning gates.
