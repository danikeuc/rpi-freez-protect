# Project state and evidence register

**Evidence snapshot:** 2026-10-01

**Active Pi mode observed:** `manual_timed`

**Physical valve position:** `UNKNOWN / NOT_VERIFIED`

This is the canonical current-state record. Repository content, deployed
Raspberry Pi state, dial/Roon behavior and physical installation observations
are separate evidence classes. A source commit, HTTP response or GPIO readback
must never be promoted into a physical claim. The external observations below
are backed by the redacted
[commissioning record](evidence/2026-09-30-commissioning-observations.md), which
was transcribed from operator-supplied output and is not a live-host attestation.

## Paired v1.1.0 publication — 2026-10-02

This publication checkpoint supersedes the draft/unmerged wording in older
sections below for Pi PR #22 and Dial PR #10. Those sections retain their
historical hardware observations and limitations.

- [Pi v1.1.0](https://github.com/danikeuc/rpi-freez-protect/releases/tag/v1.1.0)
  points to `87b12236af955ec068ddd673b7b702ebc09fe846`.
- [Dial v1.1.0](https://github.com/danikeuc/roon-knob/releases/tag/v1.1.0)
  points to `9bd5fc062d91f9ca7b3c6bd4c54dc60481129007` and preserves the exact
  hardware-tested app from `9b1ca059f0142098d2f510637351941d842f4979`.
- The publication record verified the two merge trees, public tag targets and
  every downloaded asset against SHA256/size (6 Pi assets, 9 Dial assets).
  Both v1.0.0 release/tag/asset identities remained unchanged.
- Pi exact-head CI passed. Firmware remote CI remained unobserved; the release
  explicitly records the scoped manual publication of the tested local image.
- Publication did not redeploy devices or test actuators. Pi 1.1.0 version
  labels are packaged, not confirmed installed. Prior observations remain scoped
  to their recorded revisions; physical fault outcomes remain unverified.

See [v1.1.0 release notes](releases/v1.1.0.md) and the final publication comments
on [Pi PR #22](https://github.com/danikeuc/rpi-freez-protect/pull/22) and
[Dial PR #10](https://github.com/danikeuc/roon-knob/pull/10).
The [weather-assisted proposal](superpowers/specs/2026-10-02-weather-assisted-shower-design.md)
was approved for implementation planning on 2026-10-03; it is not implemented
or commissioned behavior. The owner also requested up to five Roon playlist
favorites in the Dial admin and a long-touch/encoder playlist picker. That
companion [playlist design](superpowers/specs/2026-10-03-roon-playlist-favorites-design.md)
was approved for implementation planning on 2026-10-03; BLE remotes remain excluded. The owner confirmed that
a playlist selection replaces the queue and starts playback from its first track.

## PT100 commissioning update — 2026-10-01

The [partial commissioning record](evidence/2026-10-01-pt100-display-commissioning.md)
supersedes the older rows below for the installed Pi revision, display API and
current Waveshare candidate. The historical rows retain their original scope.

- Operator console evidence records Pi deployment of `7a24387efbbe0772ae88646d1d98182feca43369`, active services, `manual_timed` and high/high outputs.
- Authenticated display JSON reports `24.212243310943986` degrees C / `HEALTHY`, while remaining in `MANUAL_DRAIN`. This is not a calibration result.
- The dial application from source `385979069a20c2a9f11ab7d02ef656563cd7855e`, SHA-256 `c2abd6d1168cac05d3eeb1581fd11d7c64c6e91a43644878584f148c8f4e4b00`, has been flashed to the recorded ESP32-S3. All four flash regions passed digest verification.
- A 50-second boot observation found no selected fault markers, reported `5896/12288` free stack bytes, and was followed by HTTP 200. The operator subsequently confirmed `24,3` on the shower page and no temperature on Roon. A subsequent reference thermometer report of `24,4` gives approximately 0.1 degree C difference for this one comparison. Repeated reference pairs remain uncaptured; cold-point comparisons are deferred and the sensor-fault test is skipped by operator decision. Wi-Fi recovery is subsequently operator-confirmed.
- The operator confirmed the expected `---` / `FAULT / Status unavailable` presentation during the prescribed Hub stop/restart test and temperature/DRAIN recovery afterward. A subsequent restricted status check found all three services active and both GPIO outputs high. Exact transition latency was not measured; stale telemetry with a reachable API remains unverified. The subsequent Wi-Fi report and sensor-test waiver are recorded below.
- The operator confirmed Roon play/pause, one-step volume change and return, and navigation back to shower temperature/OFF on the flashed PT100 candidate. This is user-observed evidence without a bridge trace or exact observation time.
- The operator reported successful Wi-Fi interruption/recovery during several accidental disconnections: verified by operator observation, without recorded outage timing or logs. The operator waived physical sensor-fault testing for informational display use and deferred lower-temperature testing because it is currently unavailable; neither is recorded as passed.
- The operator confirmed 24 V disconnected; no SUPPLY action was issued. Neither PR has been merged or released.

## Dial admin settings repository candidate — 2026-10-02

**Later installation checkpoint:** Pi source `52c0815c17ecd94d4939c2995a0cced3a40be8bc`
was installed through the trusted operator console on 2026-10-02. All 20
installed Python files matched source; the operator reported manual_timed,
MANUAL_DRAIN, duration capability true and a protocol 2 DRAIN receipt.
Restricted SSH independently confirmed source identity, active Hub/Node-RED/
paired daemon and GPIO26/20 output/high. The paired flow passed the deployed
preflight; unrelated nodes were preserved. The root-only pre-upgrade backup
is `/root/freeze-protect-before-admin.TqLNPDrE`.

Companion dial source `9b1ca059f0142098d2f510637351941d842f4979`, app SHA256
`38e29badcf6e80927ede5acb955204ff1cc65b39a4d971eba2b6271d8bd25c58`, was flashed
after a verified full backup. Four regions and unchanged NVS were verified;
a 50-second boot and GET-only admin checks passed. The first d0b1a28 image
had an IPv4 admin 403 defect and was superseded by this fix. The operator subsequently confirmed private PIN/login, duration save and
browser-reload retention (three minutes then return to ten), and the requested
rotation/touch/swipe checks. The operator also confirmed PIN, duration and selected rotation retained
after a USB power cycle. Quantitative timing remains unverified.
No timed/SUPPLY or energized physical test was performed; 24 V was confirmed
disconnected. These installation observations supersede the source-only
status in the historical candidate description below, not the remaining
hardware acceptance gates. Both PRs remain draft and unmerged.

Draft [Pi PR #22](https://github.com/danikeuc/rpi-freez-protect/pull/22)
adds strict one to ten minute manual timing and the status capability consumed
by draft [dial PR #10](https://github.com/danikeuc/roon-knob/pull/10).
These branches are candidate source and local check evidence; neither this
section nor their builds establish the installed Pi package, flashed firmware,
relay contacts, valve position or hydraulic behavior. The earlier sentence
"neither PR has been merged or released" above describes the 2026-10-01
checkpoint before the v1.0.0 publication recorded below; it is not a claim
about the two new draft PRs or the current GitHub release state.

The candidate defaults to 600 seconds for legacy empty requests. A valid
explicit request is a whole-minute 60–600 seconds, rejected outside that
range. A dial with a saved short duration blocks START without fresh Pi
capability, including rollback to an older Pi API. Dial admin setup protects
configuration surfaces on both station and AP servers; interrupted first PIN
setup after an established marker may require deliberate recovery. The code
no longer automatically erases all NVS on boot initialization error. These
are source properties awaiting exact-artifact bench validation; preservation
of existing settings after flash and actual PIN behavior are pending device
checks. The browser UI remains on a trusted LAN.

No live Pi/device session, SUPPLY command, 24 V change, flash, or deployment was
performed for this candidate entry. Final local verification belongs in draft
[Pi PR #22](https://github.com/danikeuc/rpi-freez-protect/pull/22) and
[dial PR #10](https://github.com/danikeuc/roon-knob/pull/10); exact local
artifact identities are in the user-accessible `dial-admin-candidate/manifest.json`.
Historical operator observations below retain their own
source revisions and test boundaries. The four fault domains remain pending
for the candidate as described in the [operations runbook](operations/dial-admin-settings.md).

## Current contract

- The Raspberry Pi Hub is the valve safety authority. In the deployed
  `manual_timed` mode, idle is `MANUAL_DRAIN` / `DRAIN`; one authenticated
  deliberate display action may start a 60–600-second `SUPPLY` interval in
  whole minutes. The legacy/default request remains 600 seconds.
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

| Evidence class | Recorded evidence and provenance | Limits |
| --- | --- | --- |
| Git repository | [Repository reconciliation](evidence/2026-09-30-commissioning-observations.md#repository-reconciliation) records that `origin/main` was `b861c0a67dd484264dc810aa5b7525c18731736c` (merge of manual timed control). Its tree `6ce434e37f0da8fc408f283163ba10835114779f` is exactly equal to feature head `dab832f4dd98095db8e68d2189d7f159abc93183`. This reconciliation runs on a branch created from that merge. | Tree equality proves source files only. It does not prove installed packages, copied unit/config files, process state, firmware or hardware. |
| Repository checks | The PT100 display telemetry implementation is present in commits `8752efa`, `e9b748f`, `ccb653f`, and `c7d4160`. After the final review fix, **267 tests passed** with one dependency deprecation warning; Ruff, strict mypy and `git diff --check` passed. Source/wheel build and deployment JSON/JavaScript/shell syntax passed after the earlier Task 4 documentation update. | Repository checks use local/simulated adapters. They do not prove this revision is installed, that Pi SPI or the sensor wiring works, that the dial displays the value, or that relays, valves or water routing behave as intended. |
| Pi source and mode | The [operator-supplied Pi record](evidence/2026-09-30-commissioning-observations.md#raspberry-pi-observations), dated 2026-09-30 for `192.168.114.192`, records the checkout at `dab832f4dd98095db8e68d2189d7f159abc93183`, whose tree equals the merged `main` tree above. `/etc/rpi-freeze-protect/environment` reported `FREEZE_PROTECT_CONTROL_MODE=manual_timed`. | The environment value was observed without exposing token values. A checkout does not prove every copied root-owned artifact matches it. |
| Pi services | The [operator-supplied Pi record](evidence/2026-09-30-commissioning-observations.md#raspberry-pi-observations), dated 2026-09-30, records `node-red.service`, `freeze-protect-pair-gpio.service` and `freeze-protect.service` as active. The broken legacy alias `nodered.service` was disabled/inactive. The Hub `/health` response was `{"service":"ok","state":"MANUAL_DRAIN"}`. | A service marked active does not prove its full request path or physical output. Logs and runtime dependency versions were not captured in this reconciliation. |
| Node-RED and gateway | The [operator-supplied Pi record](evidence/2026-09-30-commissioning-observations.md#raspberry-pi-observations), dated 2026-09-30, records that the deployed-flow preflight exited zero and reported no active legacy GPIO 26/20 or `/trigger` paths and exactly one paired bridge route. Port 1880 was loopback-only. Nginx listened on `8081`; its active configuration showed the three display routes. An unauthenticated display request returned 401 and an unexposed route returned 404. | Exact Node-RED/Node.js versions, palette dependency versions and installed settings/package file hashes remain **UNKNOWN**. The gateway is trusted-LAN HTTP, not an internet boundary. |
| Display API | The [operator-supplied Pi record](evidence/2026-09-30-commissioning-observations.md#raspberry-pi-observations), dated 2026-09-30, includes authenticated status with `mode=manual_timed`, `command=DRAIN`, `remaining_seconds=0`, `state=MANUAL_DRAIN`, `reason=manual_idle` and `action_enabled=true`. The later repository implementation adds `pipe_temperature_c` and `sensor_health` to display status. | The Pi observation predates commits `8752efa`, `e9b748f`, `ccb653f`, and `c7d4160`; it does not prove these fields are deployed or visible on the dial. Logical controller status is not relay or valve feedback. |
| Disconnected output test | The [timestamped GPIO record](evidence/2026-09-30-commissioning-observations.md#disconnected-gpio-sequence) records that the operator stated the 24 V valve supply was disconnected. GPIO readback was high/high at `2026-09-30T13:56:18+00:00`, low/low during the approved timed action at `13:57:47+00:00`, and high/high again at `13:58:34+00:00`. | The 24 V statement was not an electrical measurement. This proves paired Pi output levels, not relay contact state, valve movement or the plumbing path. |
| Roon interaction | The [Waveshare/Roon record](evidence/2026-09-30-commissioning-observations.md#waveshare-and-roon-observations), dated 2026-09-30, records that the operator observed volume changes and play/pause transitions (`playing` → `paused` → `playing`) from the Waveshare dial and reported that it worked. | This is operator-observed end-to-end behavior without a retained protocol trace. Exact current firmware identity on the dial remains separate evidence. |
| Waveshare firmware | The [Waveshare/Roon record](evidence/2026-09-30-commissioning-observations.md#waveshare-and-roon-observations) ties `roon-control` commit `f0e5138d57f07899b307d75778ad7da14ab1b274` and `roon-knob` commit `8acbd418b599886d7c3442c2f674c1ee084359a5` to release `v2.7.0-alpha.6`. Recorded SHA-256: application image `0bfc90c60c8aa5a19cb772452be03451a2d5200dddacfd9056fd9586b36a574a`; merged image `cd00abed1b967cb0d46766d4aa959f70397d1e06bddf1f1f77e5dd27d244d766`. The hardware-tested development image had SHA-256 `66624aa234280d68ffc0192b73b42ed317ba963836bab5456d6dfecbc3fbb6ad` on ESP32-S3 MAC `d0:cf:13:1e:15:44`. | The release image has **not been verified as flashed**. The user-observed behavior applies to the hardware-tested development image, not automatically to the release artifact. |
| Physical installation | The [commissioning record](evidence/2026-09-30-commissioning-observations.md#disconnected-gpio-sequence) records no energized valve movement or plumbing-path observation during this reconciliation. | Relay contacts, both valve positions, return-capacitor behavior, water isolation, supply rating and safe plumbing outcome remain **UNKNOWN / NOT_VERIFIED**. |
| PT100/MAX31865 | The [2026-10-01 partial commissioning record](evidence/2026-10-01-pt100-display-commissioning.md) records installed Pi source `7a24387`, SPI device/service permissions, a live authenticated `HEALTHY` reading, verified flash and bounded boot of the exact dial candidate, operator-observed `24,3` on shower only, and one independent thermometer report of `24,4`. | Exact breakout safeguards, calibration, repeated reference pairs and stale telemetry with a reachable API remain unverified. Physical lead/sensor fault testing is skipped by operator decision; cold-point comparisons are deferred. Wi-Fi recovery is verified by operator report. Hub/API unavailability and display recovery were operator-confirmed in the subsequent stop/restart test. This session did not change `sensor_commissioned`; its persisted value was not independently read back and must not be treated as automatic-policy approval. |

## Gap reconciliation

| Claim or required proof | Current evidence | Source and limit | Category | Minimal next fix | Owner |
| --- | --- | --- | --- | --- | --- |
| Active Pi uses `manual_timed` | Environment value and authenticated status agree | Deployed observation; token values intentionally omitted | Closed | Recheck after any deployment | Pi operator |
| Only paired GPIO commands are active | Deployed preflight passed; disconnected high/high → low/low → high/high observed | Does not prove relay/valve movement | Closed for software output | Keep preflight in every cutover | Pi operator |
| LAN exposes only display API | Active Nginx configuration plus 401/404 behavior observed | Installed file hash was not retained | Closed for route behavior | Capture config hash at next maintenance | Pi operator |
| Roon dial control works | Operator confirmed play/pause, one-step volume round trip and shower-page return on the identified PT100 candidate | [Current candidate record](evidence/2026-10-01-pt100-display-commissioning.md); no retained bridge trace or exact observation time | Closed for this bounded candidate check | Recheck after a firmware change; release acceptance remains separate | Firmware maintainer + operator |
| Valve physical `DRAIN`/`SUPPLY` follows GPIO | No energized observation | GPIO cannot prove physical position | Pending | Separately approved water-isolated 24 V test with both valves observed | Hardware operator |
| Hub-to-daemon communication loss returns to `DRAIN` | Lease behavior covered by repository tests | No deployed timed/physical fault injection | Partial | Approved disconnected deployed lease-expiry test; physical test later | Pi operator |
| Hub crash/hang returns to `DRAIN` | Renewal stops by design and in tests | No deployed process-failure timestamps or valve observation | Partial | Approved disconnected service-stop test and later physical confirmation | Pi operator |
| Controller restart starts at `DRAIN` | Code, unit ordering and high/high observations support it | No retained end-to-end restart trace for this revision | Partial | Capture service restart timeline and both-pin readback with 24 V disconnected | Pi operator |
| Power loss/restoration is physically safe | Conservative startup is implemented | Electrical relay/GPIO behavior and valves were not observed | Pending | Planned power-cycle test with water isolated and explicit live approval | Hardware operator |
| PT100 is ready for `automatic` | Display-only live telemetry and shower-page presentation observed; one sequential room-temperature reference comparison | [Partial commissioning record](evidence/2026-10-01-pt100-display-commissioning.md); not calibration or automatic-policy acceptance | Pending | Revisit waived/deferred sensor fault and reference checks before any separately reviewed automatic-policy commissioning | Hardware operator + policy reviewer |
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

The operator-confirmed display, Hub recovery, Wi-Fi recovery and bounded Roon
checks are recorded. Physical sensor-fault testing is skipped by operator decision
for informational display use; cold-point comparisons are deferred as currently
unavailable. Do not request those tests again as immediate prerequisites for this
scope. Other evidence limitations remain in the commissioning record.
Keep `manual_timed`; automatic-policy commissioning remains separate.

Record each new result against the installed Pi source and exact firmware hash.
Both PRs remain draft. Energized valve tests and automatic-policy commissioning
require their separately defined approval and test boundaries; GPIO readback
must not be described as valve-position evidence.

## v1.0.0 release authorization

The operator requested release v1.0.0 after accepting the informational display
scope and the recorded skipped/deferred tests. [Release scope and component
identities](releases/v1.0.0.md) distinguish the tested dial binary, Pi package
metadata update and remaining evidence limits. Earlier draft statuses describe
their historical checkpoints; current publication state is on GitHub.

## Weather and Roon playlist planning — 2026-10-03

Both written designs are owner-approved. The [weather implementation plan](superpowers/plans/2026-10-03-weather-assisted-shower.md)
and [playlist implementation plan](superpowers/plans/2026-10-03-roon-playlist-favorites.md)
are written for owner review and execution-method selection; neither has been
executed. New bridge routes require explicit contract approval as part of plan
review. The weather plan proposes conservative USER_OFF recovery after an
unclean AUTO exit, in addition to the approved interrupted-manual behavior.

The plans reference actual Pi, Dial and bridge interfaces. Documentation checks
are recorded separately from code/runtime evidence. No source, firmware,
configuration, device playback, GPIO or release artifact changed during planning.
Playlist identity across Core reconnect and preexisting shuffle behavior require
the P1 protocol characterization before playback implementation claims.

Planning validation: `git diff --check` passed; a local Markdown-link check
resolved all 34 relative links across the ledger, four matching design documents
and both new plans. This is documentation evidence only; no software tests or
runtime checks were run for these documentation-only changes.
