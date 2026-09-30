# Project state and evidence register

**Evidence snapshot:** 2026-09-30

**Active Pi mode observed:** `manual_timed`

**Physical valve position:** `UNKNOWN / NOT_VERIFIED`

This is the canonical current-state record. Repository content, deployed
Raspberry Pi state, dial/Roon behavior and physical installation observations
are separate evidence classes. A source commit, HTTP response or GPIO readback
must never be promoted into a physical claim.

## Current contract

- The Raspberry Pi Hub is the valve safety authority. In the deployed
  `manual_timed` mode, idle is `MANUAL_DRAIN` / `DRAIN`; one authenticated
  deliberate display action may start one fixed 600-second `SUPPLY` interval.
  Duplicate actions do not extend it. Weather and sensor inputs cannot start
  `SUPPLY` in this mode.
- BCM 26 and BCM 20 are one paired active-low actuator. `DRAIN` is high/high and
  `SUPPLY` is low/low. The daemon is the sole GPIO writer and expires an
  unrenewed `SUPPLY` lease within 60 seconds.
- Nginx exposes only display status, timed-shower and drain routes on trusted-LAN
  port `8081`. The Hub remains on `127.0.0.1:8000`; Node-RED remains on
  `127.0.0.1:1880`.
- The active display is the Waveshare ESP32-S3 dial. Roon control is implemented
  by the separate `roon-knob` and `roon-control` repositories. The CrowPanel in
  this repository is historical and retired from the active valve network.
- PT100/MAX31865 on SPI0 CE0 remains the production source design for a future
  separately commissioned `automatic` mode. DS18B20 is rollback code only.
- The restricted `freezeprotect-commission` SSH identity exposes exactly
  `inventory`, `status`, `diagnose-pair-gpio` and `drain`; it has no shell,
  forwarding, firmware, arbitrary systemd or direct GPIO interface.

## Evidence ledger

| Evidence class | Verified on 2026-09-30 | Limits |
| --- | --- | --- |
| Git repository | `origin/main` was `b861c0a67dd484264dc810aa5b7525c18731736c` (merge of manual timed control). Its tree `6ce434e37f0da8fc408f283163ba10835114779f` is exactly equal to feature head `dab832f4dd98095db8e68d2189d7f159abc93183`. This reconciliation runs on a branch created from that merge. | Tree equality proves source files only. It does not prove installed packages, copied unit/config files, process state, firmware or hardware. |
| Repository checks | After making the ownership-sensitive SSH rollback simulation portable and adding documentation-link coverage, the complete Python suite passed: **224 tests** with one dependency deprecation warning. Ruff and strict mypy passed. Source and wheel distributions built successfully. The Node-RED export contained 11 nodes and no structural issues; JSON, JavaScript and shell syntax passed. | These checks use simulated/local adapters and do not prove deployed or physical behavior. The exact final commit and CI result belong in the branch/PR record. |
| Pi source and mode | The Pi checkout was observed at `dab832f4dd98095db8e68d2189d7f159abc93183`, whose tree equals the merged `main` tree above. `/etc/rpi-freeze-protect/environment` reported `FREEZE_PROTECT_CONTROL_MODE=manual_timed`. | The environment value was observed without exposing token values. A checkout does not prove every copied root-owned artifact matches it. |
| Pi services | `node-red.service`, `freeze-protect-pair-gpio.service` and `freeze-protect.service` were observed active. The broken legacy alias `nodered.service` was disabled/inactive. The Hub `/health` response was `{"service":"ok","state":"MANUAL_DRAIN"}`. | A service marked active does not prove its full request path or physical output. Logs and runtime dependency versions were not captured in this reconciliation. |
| Node-RED and gateway | The deployed-flow preflight exited zero and reported no active legacy GPIO 26/20 or `/trigger` paths and exactly one paired bridge route. Port 1880 was loopback-only. Nginx listened on `8081`; its active configuration showed the three display routes. An unauthenticated display request returned 401 and an unexposed route returned 404. | Exact Node-RED/Node.js versions, palette dependency versions and installed settings/package file hashes remain **UNKNOWN**. The gateway is trusted-LAN HTTP, not an internet boundary. |
| Display API | Authenticated status reported `mode=manual_timed`, `command=DRAIN`, `remaining_seconds=0`, `state=MANUAL_DRAIN`, `reason=manual_idle` and `action_enabled=true`. | This is logical controller status. It is not relay or valve feedback. |
| Disconnected output test | The operator stated the 24 V valve supply was disconnected. GPIO readback was high/high at `2026-09-30T13:56:18+00:00`, low/low during the approved timed action at `13:57:47+00:00`, and high/high again at `13:58:34+00:00`. | The 24 V statement was not an electrical measurement. This proves paired Pi output levels, not relay contact state, valve movement or the plumbing path. |
| Roon interaction | The operator observed volume changes and play/pause transitions (`playing` → `paused` → `playing`) from the Waveshare dial and reported that it worked. | This is operator-observed end-to-end behavior without a retained protocol trace. Exact current firmware identity on the dial remains separate evidence. |
| Waveshare firmware | Release `v2.7.0-alpha.6` exists in `roon-knob`. Recorded SHA-256: application image `0bfc90c60c8aa5a19cb772452be03451a2d5200dddacfd9056fd9586b36a574a`; merged image `cd00abed1b967cb0d46766d4aa959f70397d1e06bddf1f1f77e5dd27d244d766`. The hardware-tested development image had SHA-256 `66624aa234280d68ffc0192b73b42ed317ba963836bab5456d6dfecbc3fbb6ad` on ESP32-S3 MAC `d0:cf:13:1e:15:44`. | The release image has **not been verified as flashed**. The user-observed behavior applies to the hardware-tested development image, not automatically to the release artifact. |
| Physical installation | No energized valve movement or plumbing-path observation was performed in this reconciliation. | Relay contacts, both valve positions, return-capacitor behavior, water isolation, supply rating and safe plumbing outcome remain **UNKNOWN / NOT_VERIFIED**. |
| PT100/MAX31865 | Source adapter, storage binding and tests exist for `MAX31865_PT100_SPI0_CE0`. | Installed breakout revision, 430-ohm reference, terminal mapping, fault behavior, calibration and commissioning status remain **UNKNOWN / NOT_VERIFIED**. |

## Gap reconciliation

| Claim or required proof | Current evidence | Source and limit | Category | Minimal next fix | Owner |
| --- | --- | --- | --- | --- | --- |
| Active Pi uses `manual_timed` | Environment value and authenticated status agree | Deployed observation; token values intentionally omitted | Closed | Recheck after any deployment | Pi operator |
| Only paired GPIO commands are active | Deployed preflight passed; disconnected high/high → low/low → high/high observed | Does not prove relay/valve movement | Closed for software output | Keep preflight in every cutover | Pi operator |
| LAN exposes only display API | Active Nginx configuration plus 401/404 behavior observed | Installed file hash was not retained | Closed for route behavior | Capture config hash at next maintenance | Pi operator |
| Roon dial control works | Operator observed volume and play/pause | No retained protocol trace; release image not flashed | Partial | Flash/identify exact release, then repeat compact acceptance | Firmware maintainer + operator |
| Valve physical `DRAIN`/`SUPPLY` follows GPIO | No energized observation | GPIO cannot prove physical position | Pending | Separately approved water-isolated 24 V test with both valves observed | Hardware operator |
| Hub-to-daemon communication loss returns to `DRAIN` | Lease behavior covered by repository tests | No deployed timed/physical fault injection | Partial | Approved disconnected deployed lease-expiry test; physical test later | Pi operator |
| Hub crash/hang returns to `DRAIN` | Renewal stops by design and in tests | No deployed process-failure timestamps or valve observation | Partial | Approved disconnected service-stop test and later physical confirmation | Pi operator |
| Controller restart starts at `DRAIN` | Code, unit ordering and high/high observations support it | No retained end-to-end restart trace for this revision | Partial | Capture service restart timeline and both-pin readback with 24 V disconnected | Pi operator |
| Power loss/restoration is physically safe | Conservative startup is implemented | Electrical relay/GPIO behavior and valves were not observed | Pending | Planned power-cycle test with water isolated and explicit live approval | Hardware operator |
| PT100 is ready for `automatic` | Source and simulated tests only | Installed sensor chain is unverified | Pending | Complete the documented electrical, fault and calibration procedure | Hardware operator |
| Release artifact equals running Waveshare firmware | Release hashes and device MAC recorded separately | No flash/readback identity tying them together | Pending | Flash exact release or add signed runtime build identity and record it | Firmware maintainer |

## Failure-response proof levels

| Failure | Implemented response | Current proof | Remaining proof |
| --- | --- | --- | --- |
| Hub-to-daemon communication loss | 60-second daemon lease requests paired `DRAIN` | Repository unit/integration tests | Deployed timeout and physical observation |
| Hub crash or hang | Renewal stops; daemon lease requests paired `DRAIN` | Repository logic/tests | Deployed process-failure timeline and physical observation |
| Controller/service restart | Daemon startup requests high/high; Hub starts conservatively | Code/unit files and disconnected high/high observations | Controlled restart trace and physical observation |
| Power loss and restoration | Services are designed to start conservatively | Repository design only | Electrical and hydraulic loss/restore test |

## Authoritative current documents

1. [`../AGENTS.md`](../AGENTS.md) — mandatory safety and access boundaries.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — active component and authority model.
3. [`../deployment/COMMISSIONING.md`](../deployment/COMMISSIONING.md) — Pi,
   Node-RED, sensor and valve procedure.
4. [`../deployment/DISPLAY_COMMISSIONING.md`](../deployment/DISPLAY_COMMISSIONING.md)
   — active Waveshare/Roon/valve display acceptance.
5. [`../deployment/WORKSTATION_CODEX_COMMISSIONING.md`](../deployment/WORKSTATION_CODEX_COMMISSIONING.md)
   — restricted workstation access.
6. [`VERIFICATION.md`](VERIFICATION.md) — repository quality gates.

[`../deployment/CROWPANEL_COMMISSIONING.md`](../deployment/CROWPANEL_COMMISSIONING.md)
and `firmware/crowpanel` are historical/rollback material. Files in
`docs/superpowers/specs/` and `docs/superpowers/plans/` are design history, not
operational runbooks.

## Next safe work

Repository reconciliation and CI can proceed without touching the Pi. The next
hardware step, if desired, is a separately approved water-isolated physical
valve test. Until that gate is explicitly approved, keep 24 V disconnected and
do not describe GPIO status as valve position. Firmware provenance can be closed
independently by flashing or otherwise identifying the exact `roon-knob` release
and repeating the compact Roon/display acceptance.
