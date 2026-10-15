# Project state and evidence register

**Documentation reconciliation:** 2026-10-15; device observations retain their original dates

**Latest recorded Pi installation:** 1.3.1, `weather_assisted`, `USER_OFF` / `DRAIN`
(operator installation receipt and restricted GPIO readback, 2026-10-11; not a new live observation on 2026-10-12).

**Physical valve position:** `UNKNOWN / NOT_VERIFIED`

This is the canonical current-state record. Repository content, deployed
Raspberry Pi state, dial/Roon behavior and physical installation observations
are separate evidence classes. A source commit, HTTP response or GPIO readback
must never be promoted into a physical claim. The external observations below
are backed by the redacted
[commissioning record](evidence/2026-09-30-commissioning-observations.md), which
was transcribed from operator-supplied output and is not a live-host attestation.

## Independent light installation package prepared — 2026-10-15

A separate offline light-runtime package has passed independent review and1026
tests and is available for the trusted Pi console. It preserves the shower environment, paired daemon and Node-RED;
initial GPIO21 command is OFF, with camera forwarding still unconfigured.
The VM adapter was freshly confirmed active in observe mode. This is preparation,
not a Pi installation or physical acceptance. See the
[preparation record](evidence/2026-10-15-light-runtime-preparation.md).

## Third-relay bench stopped; diagnostics update prepared — 2026-10-15

Owner confirmed both loads disconnected and STOP; a subsequent restricted read
showed paired outputs HIGH/HIGH. The operator then ran the bounded GPIO21 bench:
LIGHT_LEVEL_MISMATCH, attempted_gpio21=true, final_off_readback=true,
physical_acceptance=NOT_VERIFIED, automation_enabled=false. Evidence is retained
at /root/light-gpio21-bench.ehy6qh3b. Remote diagnostics identify crash_release:
the first sample after SIGKILL retained GPIO21 output/LOW; explicit final OFF
recovery succeeded. All931 stored samples retain paired output/HIGH.
The owner subsequently accepted retained light ON after process crash/hang;
this removes the automatic crash-OFF requirement only for GPIO21. The original
failed receipt remains unchanged; no blind repeat or forwarding activation is
authorized merely by reclassifying the requirement.
[Accepted light failure behavior](evidence/2026-10-15-light-retained-on-acceptance.md).
[Bench evidence](evidence/2026-10-15-light-gpio21-bench-preparation.md).

A status-only helper update was installed from the owner-reported baseline hash
df06b46bd206dbadbbbd201aeb80529df9deb790b7df448b29e1ff2ba15c6a9c.
It adds bounded historical GPIO21 diagnostics to the existing maintenance status
command without changing dispatcher/sudoers or actuator authority. Tests:993 pass;
Ruff and diff-check pass; independent review completed with both findings fixed.
Owner installation and separate restricted SSH acceptance are VERIFIED. New
helper hash:2697465c2d98ab3b34be8da17f145411e900dc50765f02ff3e3a51ceb326364b.
Extra-argument status was rejected; no expanded command or actuator authority.
[Diagnostics preparation](evidence/2026-10-15-light-bench-diagnostics.md).

## Continuous Protect MCP observation installed — 2026-10-15

The approved G4 Pro/person source now has a standalone user service on linuxvm,
independent of Codex. Enabled/running and linger verified through a separate SSH
connection; repeated MCP polls succeeded. **Observe only:** no Pi destination or
camera token is configured, so this does not activate the lamp. Adapter source,
27 focused tests, independent review fixes and deployment identities are recorded
in [adapter evidence](evidence/2026-10-15-protect-mcp-adapter.md).
Pi light service/TLS ingress provisioning and existing disconnected hardware
acceptance remain pending. No new firmware, relay or physical acceptance claim.

## Lighting target inventory received — 2026-10-15

The operator supplied the verified read-only package output. GPIO20/26 report
the paired owner; GPIO21 is unused at observation. Node-RED is active as nodered,
with51 nodes and no enabled lighting ingress. Startup journal reports Node-RED
5.0.7 and matching known paths; Node.js and effective settings remain unverified.
[Exact receipt and file hashes](evidence/2026-10-15-lighting-target-inventory.md).
The inventory request is complete; lighting activation, actual Protect profile
and disconnected/physical acceptance remain pending.

## Lighting continuation — 2026-10-14

[Current handoff](evidence/2026-10-14-lighting-continuation.md) records the verified
paired prerequisite, read-only inventory tool and remaining lighting gates.
The third relay, camera ingress and new Dial firmware are not yet activated.

## Paired GPIO migration recovered and verified - 2026-10-14

The candidate kernel-ownership paired daemon is installed (SHAef96336ec), with
isolated gpiod2.3.0 interpreter and reviewed paired dropin. Initial installation
stopped on an order-sensitive DeviceAllow comparison; the first continuation
then stopped because the Hub HTTP listener was not yet ready. Both defects are
fixed in repository installer code, and their original failure records remain.

A separate Hub-only continuation completed. Fresh restricted SSH confirmed its
durable success marker, no failure marker, Hub/pair/Node-RED active and the exact
installed candidate hashes. Independent helper readback confirms GPIO26 and
GPIO20 both output/high. The running paired PID remained unchanged during final
Hub recovery. Full private receipt was not exported; the reviewed continuation
writes success only after USER_OFF, preserved state, flow, ownership and readback
checks. [Detailed evidence](evidence/2026-10-14-device-allow-recovery.md#target-recovery-verified-over-restricted-ssh).

Lighting remains disabled; third-relay activation and physical acceptance are
pending. Both loads remain disconnected per operator confirmation. This is not
proof of valve/lamp position or crash/power-loss protection. The paired override
retains Restart=no; process recovery needs deliberate assessment. No release,
commit or push is implied by this deployment checkpoint.

## Limited maintenance access activated - 2026-10-14

The owner subsequently asked Codex to carry out the setup. The
[access v1 candidate](../deployment/maintenance-access/README.md) preserves the
original four commands and adds three exact command forms for diagnostics and
single-use preparation/installation of the pinned paired-GPIO migration. It
provides no generic shell, package install or restart permission. Access
installation itself does not run migration or change actuator/service state.
The previous documentation-only entry below is historical.

At the access activation checkpoint, restricted SSH inventory/status/diagnose checks succeeded: DietPi
kernel 6.18.39+rpt-rpi-v8, checkout d0dfeac, all three checked services active,
GPIO26/20 output/high. The installed paired daemon remains 33088ea9 and helper
555ea7cd, matching the recorded baseline. These are electronic readbacks, not
physical valve or light acceptance. The operator installed access package v2 (backup
`/root/freeze-maintenance-access.c8qk1m3v`). Separate SSH inventory/status and
two rejected command forms verified activation. Both migration jobs initially
reported NOT_REQUESTED. Subsequent prepare and status connections timed out at
port22 before command dispatch. Connectivity later returned and prepare was
submitted once; last observed job was activating/start, with original services
active. Another status connection timed out. Operator status subsequently verified prepare success at
`/root/paired-gpio-migration.xj0q8tgi`, with all original services active.
The install SSH connection timed out before dispatch; migrated GPIO ownership
remains unconfirmed. A later SSH check found a partial install stopped at
`EFFECTIVE_DEVICE_ALLOW`: candidate daemon/dropin are present, Hub and paired
service inactive, Node-RED active. Installation is FAILED, not accepted;
operator output confirmed correct permissions in reverse order. A tested
[ordering fix and one-shot recovery](evidence/2026-10-14-device-allow-recovery.md)
were prepared and the operator ran recovery. It stopped again; fresh SSH
shows candidate paired service active, Hub inactive and Node-RED active.
Remote diagnostics identified ConnectionRefusedError while reading Hub HTTP
status immediately after start. A bounded HTTP readiness fix and Hub-only
continuation are prepared; target continuation and acceptance remain pending.
[Candidate validation and package identity](evidence/2026-10-14-maintenance-access.md)
record the exact access activation and subsequent network interruption.

## Limited maintenance access documented - 2026-10-14

The owner explicitly limited this task to documentation. The
[commissioning guide](../deployment/WORKSTATION_CODEX_COMMISSIONING.md#planned-limited-maintenance-access---documentation-decision-2026-10-14)
now describes a future bounded interface for diagnostics, verified package
backup/installation and necessary named-service restarts. Implementation and
activation are pending; the four-command commissioning allowlist remains the
current route. No SSH/sudo/helper code, device permissions or deployed service
was changed by this documentation task. Existing physical approval gates remain
in force. This entry is a policy record, not a new device observation or a
successful paired-GPIO migration receipt.
The [Pi operator guide](../deployment/PI_MAINTENANCE_ACCESS.md) adds host-specific
read-only checks and the future backup/activation/acceptance sequence. Those
commands have not been run on the Pi as part of this documentation task.

## Pi v1.2.0 publication preparation

The owner approved publishing v1.2.0, preserving v1.0.0/v1.1.0. The
[release notes](releases/v1.2.0.md) include weather assistance, optional forecast
icons metadata and the installed P1 repair. Release package/API labels change
to 1.2.0; no device redeployment or new physical acceptance is implied. Final
source, CI and asset identities are recorded in the published manifest and
verification asset. Companion firmware/bridge publication is outside this Pi
release.

## GPIO pending-DRAIN P1 repair installed - 2026-10-05

The [pending-DRAIN repair](evidence/2026-10-05-pending-drain-fix.md) preserves
independent retry after a failed safety DRAIN. Offline verification: 654 tests,
Ruff and configured mypy pass; 12 installer tests pass. The operator completed
the installation under USER_OFF. Independent restricted SSH confirmed the exact
candidate daemon hash, all three services active and both outputs high.
[Installation receipt](evidence/2026-10-05-pending-drain-installation.json)
records backup `/root/freeze-paired-drain-fix._j1g92ni`. No physical valve or live
fault-injection acceptance is claimed. Earlier manual_timed/disabled-weather
sections below retain their historical observations.

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
The approved weather and playlist plans now have implemented repository candidates. See the [2026-10-03 software validation](evidence/2026-10-03-weather-plan-validation.md) and [weather operations](operations/weather-assisted-shower.md). BLE remains excluded. This supersedes planning-only status for source implementation while retaining all historical deployed and physical limits below.

## Weather and playlist candidate — 2026-10-03

Pi source/build `31245c1ad66491d13e36d3201bae946d1fcdefef`, Dial source/build `5eb4c4506b031558bfaa3951d10a98dadc09105a`, unchanged bridge source/build `9490cef370a17e83480431d1791303fd663abce6` were local repaired candidates at the build freeze. The subsequent Pi-only installation is recorded below; Dial and bridge candidates remain uninstalled. Pi full suite 576 and commissioning 110 pass, with Ruff/mypy/build. Dial playlist/admin/valve/browser/shared checks and ESP-IDF5.5.5 build pass. Consolidated repairs address late nonce BEGIN, actual picker navigation to STOP, weather admin observations/rules and configured-zone label; deterministic regression evidence is in [current validation](evidence/2026-10-03-weather-plan-validation.md). Scoped source and documentation re-review found WR-01–04 and the malformed-observation amendment addressed. The owner subsequently approved exactly 36 inventory additions; Dial policy commit `314224b2d817d7f90afb58fbaeeaf91484eb7ac2` changes only expected_edges. Inventory, negative/header-index self-tests and the complete current shared CI command block now pass. The earlier automatic-review rejection is historical; explicit human approval resolved that boundary. Bridge serial suite 1921/0 failed/18 ignored, fmt, production CI Clippy and release build remain passing unchanged. Expanded strict Clippy retains baseline legacy test failures as permitted P5 scope limitations, never a PASS. The subsequent scoped policy/documentation review passed, closing local acceptance. Expanded baseline lint and exact-artifact device/physical limits remain explicit; this does not claim all historical checks passed.

The [manifest](evidence/2026-10-03-weather-playlist-artifacts.json) pins local artifact hashes and build-source revisions; later docs revisions are distinct. At that manifest freeze no candidate had been deployed, flashed, played, released or physically exercised. The later Pi installation below supersedes that deployment status only for Pi; the manifest retains its historical build-time metadata. Source-level fixture coverage uses actual Pi service/driver/daemon logic and actual Dial clients/worker/UI with substituted network/register/RTOS boundaries. It is not electrical/relay/valve proof. Native PlayNow remains Accepted then Unknown when first-track causality cannot be confirmed; runtime checks of empty/populated queue, unchanged volume, Sauna targeting and restart persistence remain pending.

Fresh weather preference is disabled. Any later deployment must retain manual_timed and weather disabled until separately authorized operation/physical gates pass. Keep 24 V disconnected; continuous-duty suitability and independent response to daemon crash, reboot and each power domain remain NOT_VERIFIED. Original v1.0.0/v1.1.0 publications are unchanged.

## Pi weather candidate installed, disabled — 2026-10-03

[Installation evidence](evidence/2026-10-03-pi-weather-installation.md) records the operator's successful trusted-console installation at checkout `d0dfeac61856e0ff716e700348be61709dc68505`, using the exact wheel from build source `31245c1ad66491d13e36d3201bae946d1fcdefef`. The installer reported all 26 installed files verified, `MANUAL_DRAIN`, `weather_enabled=false`, weather capability version 1 and GPIO 26/20 high. It updated the Hub package/source and the single display Nginx configuration; credentials, environment, service unit, Node-RED flow and paired daemon were preserved.

Independent restricted SSH checks completed by **2026-10-03 19:29:16 UTC** confirmed checkout `d0dfeac`, all three checked services active and both GPIO lines output/high. These checks independently establish checkout/service/output state; package byte checks, authenticated idle status and disabled weather are operator-returned installer evidence. No new timed action, continuous SUPPLY, Dial flash, bridge replacement, live playlist test or physical valve test is recorded. The operator confirmed 24 V disconnected before this installation; GPIO levels do not prove valve position.

The protected pre-migration backup is `/root/freeze-protect-before-weather.EesduvpK`; private install evidence is `/root/freeze-weather-install-state`. Keep the backup and any matching weather identity with its database. Later documentation commits do not change the installed revision. Bridge/Dial delivery and separately authorized runtime/physical acceptance remain the next stages. Original published releases remain unchanged.

## Synology fullstack candidate installed — 2026-10-04

[Bridge packaging evidence](evidence/2026-10-03-bridge-fullstack-preparation.md)
records the operator's existing Synology image, `host` networking,
`restart=always`, data bind and executable path. Exact bridge source `9490cef`
now has a separate artifact with embedded web assets; isolated GET-only
HTML/static checks pass. The operator subsequently built candidate image `66b41727d29c` and returned
`CANDIDATE_PREPARED`; its isolated version check passed in the actual runtime
image. Independent GET status still showed original `b4ba5ac`, Roon connected.
The operator also returned `BACKUP_VERIFIED` at
`/volume1/docker/unified-hifi-control-4-backup-20261003.ypgw2e8q` and verified
original restart; independent status again showed `b4ba5ac`, Roon connected.
The operator subsequently confirmed both labeled Compose inputs are backed up;
the nine missing entries are repeated optional `.env` checks and unused default
filenames. The operator Compose dry-run passed. A separately reviewed
[cutover helper](evidence/2026-10-04-bridge-cutover-preparation.md) is prepared
with fifteen passing focused tests after the initial operator run stopped before
Docker changes: the NAS-created working directory was0755 instead of0700.
The reviewed v2 helper explicitly restricts its new empty directory and retains
the privacy guard. The operator subsequently returned `CUTOVER_VERIFIED` with
helper directory `/volume1/docker/uhc-cutover-tool.5ZXSqJT5` and private state
`/volume1/docker/unified-hifi-control-4/.playlists-cutover-vgbix_si`.
An independent GET status at2026-10-03T22:48:16.929780+00:00 confirmed exact
source `9490cef370a17e83480431d1791303fd663abce6`, candidate version and Roon
connected. The bridge candidate is now recorded as installed; rollback has
not been exercised. Preserve both printed directories and the original backup.
The operator confirmed the refreshed web UI renders and Sauna is visible.
The operator subsequently returned DIAL_PROVISION_UNCONFIRMED at private state
`/volume1/docker/unified-hifi-control-4/.scope-provision-80suk28s`: backend scope
verification passed, while Dial credential/save/readback did not complete.
Preserve its scope.json as the fourth Compose input. Subsequent bridge GET
status remained source9490cef/Roon connected; operator Dial favorites still
returned unconfirmed. Initial provisioning must not be rerun. Same-token
continuation passed backend and pre-save gates, but its one Dial form attempt
failed after8012ms with OS_ERROR; logout returned401. Preserve its durable
CONTINUATION_SAVE_PENDING marker. Fresh authenticated readback and live playlist
acceptance remain pending; do not resend the form. The Dial candidate
was installed; see the USB evidence below.
This does not alter the Pi disabled/manual_timed installation above.

## Dial weather/playlist candidate installed — 2026-10-04

[USB installation evidence](evidence/2026-10-04-dial-weather-playlist-install.md)
records the initial source `5eb4c45` installation and a subsequent narrow
production NVS namespace repair. Current installed application source is
`4c0a15c08f1ca05fb948cc8c65890ec423eeedf9`, SHA256
`7bad18553d3bcb117054bd9c16f6fccb52ad0caa57d6fb9ab839f6a446cd6e3f`.
A protected fresh 16 MB full-flash backup and per-write NVS snapshots remain.
The corrected app was separately digest-verified; NVS stayed byte-identical
before boot. Matching ELF prefix, IP and exact Sauna zone were restored with
no selected fault markers during 50 seconds. Admin GET/session returned 200
with existing PIN setup; unauthenticated settings returned 401. Pi restricted
status remained three services active/high/high. The namespace regression,
affected suites, dependency checks, source review and isolated build pass;
independent test execution limitation is explicitly recorded in the evidence.
The operator subsequently reached the admin settings page, but weather and
playlist controls remained disabled; the busy cursor is a misleading disabled
style, not proof of an in-flight save. The operator subsequently returned
WEATHER_CREDENTIAL_VERIFIED using the v2 connection helper: manual_timed and
weather_enabled=false were retained, with protected recovery state
`/root/.scope-provision-_x54h4n1`. The Dial authenticated weather read now passes.
Playlist provisioning, reboot persistence, actual settings saves and weather
commissioning remain pending.
No media or actuator command was sent. No new release is published.

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

- The Raspberry Pi Hub is the valve safety authority. The recorded mode is
  `weather_assisted`, with durable `USER_OFF` / `DRAIN`. A fresh deliberate START
  can select AUTO only with eligible five-day weather, otherwise a bounded
  60-600-second manual interval. STOP inhibits reopening across restarts;
  forecast/settings changes and duplicates do not extend an accepted interval.
- `manual_timed` remains available as a separate mode. Only a deliberate
  authenticated action starts its 60-600-second interval; its default is 600.
  Weather and informational sensor inputs cannot start SUPPLY in that mode.
- BCM 26 and BCM 20 are one paired active-low actuator. `DRAIN` is high/high and
  `SUPPLY` is low/low. The sole GPIO daemon requests DRAIN when its 60-second
  lease expires and retains failed DRAIN for retry until both outputs verify.
- The current gateway source exposes scoped display status, timed-shower,
  drain, weather-settings and explicit start/stop routes on trusted-LAN port
  `8081`. The Hub remains on `127.0.0.1:8000`; Node-RED on `127.0.0.1:1880`.
- The active display is the Waveshare ESP32-S3 dial. Roon control is implemented
  by the separate `roon-knob` and `roon-control` repositories. The CrowPanel in
  this repository is historical and retired from the active valve network.
- PT100/MAX31865 on SPI0 CE0 remains the production source design for a future
  separately commissioned `automatic` mode. DS18B20 is rollback code only.
- The restricted `freezeprotect-commission` SSH identity exposes exactly
  `inventory`, `status`, `diagnose-pair-gpio` and `drain`, plus the activated
  maintenance helper's exact `status`, `prepare`, `install` forms for one pinned
  migration; it has no shell,
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
| Historical Pi mode was `manual_timed` (superseded by 2026-10-05 weather activation) | Environment value and authenticated status agree | Deployed observation; token values intentionally omitted | Closed | Recheck after any deployment | Pi operator |
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
Keep the recorded `weather_assisted` installation in `USER_OFF` / `DRAIN` until
a separately authorized operational test. Physical AUTO acceptance and legacy
sensor-driven `automatic` commissioning remain separate.

Record each new result against the installed Pi source and exact firmware hash.
Earlier draft-PR statements are historical. Energized valve tests and automatic-policy commissioning
require their separately defined approval and test boundaries; GPIO readback
must not be described as valve-position evidence.

## v1.0.0 release authorization

The operator requested release v1.0.0 after accepting the informational display
scope and the recorded skipped/deferred tests. [Release scope and component
identities](releases/v1.0.0.md) distinguish the tested dial binary, Pi package
metadata update and remaining evidence limits. Earlier draft statuses describe
their historical checkpoints; current publication state is on GitHub.

## Historical weather and Roon playlist planning checkpoint — 2026-10-03

This section preserves the earlier planning checkpoint. It is superseded for current source status by the [implemented candidate record](#weather-and-playlist-candidate-2026-10-03) and [exact validation](evidence/2026-10-03-weather-plan-validation.md). The owner subsequently approved both plans, exact new bridge API contracts, subagent execution and conservative interrupted-AUTO recovery; the exact dependency approval is now recorded and its affected local gates pass; the subsequent policy/documentation review passed; the later Pi-only installation above remains separate from pending Dial/bridge and physical acceptance.

At this earlier checkpoint both written designs were owner-approved. The [weather implementation plan](superpowers/plans/2026-10-03-weather-assisted-shower.md)
and [playlist implementation plan](superpowers/plans/2026-10-03-roon-playlist-favorites.md)
were written for owner review and execution-method selection; neither had been
executed at that point. New bridge routes then required explicit contract approval as part of plan
review. The weather plan proposed conservative USER_OFF recovery after an
unclean AUTO exit, in addition to the approved interrupted-manual behavior.

The plans reference actual Pi, Dial and bridge interfaces. Documentation checks
are recorded separately from code/runtime evidence. No source, firmware,
configuration, device playback, GPIO or release artifact changed during planning.
At that checkpoint playlist identity across Core reconnect and preexisting shuffle behavior required
the P1 protocol characterization before playback implementation claims. Current conservative retained-session/reselection and Accepted-to-Unknown limits are in the validation record above.

Planning validation: `git diff --check` passed; a local Markdown-link check
resolved all 34 relative links across the ledger, four matching design documents
and both new plans. This is documentation evidence only; no software tests or
runtime checks were run for these documentation-only changes.

## v1.3.0 shower history release preparation - 2026-10-11

Owner authorized installation, Git documentation and release. Source now adds
[persistent history](SHOWER_HISTORY.md); see [release scope](releases/v1.3.0.md).
666 offline tests passed before the version-label update. Deployment acceptance
remains tied to subsequent exact-artifact receipts, not this source note.

## Pi history installed - 2026-10-11

The operator supplied HISTORY_INSTALLED for package 1.3.0; both history endpoints
returned two rows, USER_OFF/DRAIN and high/high readbacks were confirmed.
See [exact receipt and startup fault](evidence/2026-10-11-shower-history-install.md).
The exact CI Dial v1.3.0-shower.3 application is installed and readback-verified;
authenticated history UI was confirmed by the operator on 2026-10-11. The Node-RED startup readiness
repair is installed in 1.3.1, confirmed by the trusted-console receipt below.

## Startup readiness patch preparation - 2026-10-11

[Pi 1.3.1](releases/v1.3.1.md) uses an ExecStartPre paired-v2 DRAIN receipt gate
before Hub startup. Only refused connections are retried; malformed/failed
receipts stop that invocation. The existing fault latch is unchanged. Local
verification: 685 tests, Ruff, strict mypy (27 source files), diff whitespace
checks. Independent review closed baseline-version validation and timing-claim
findings. Repository tests do not prove a deployed reboot with delayed Node-RED.
The additive updater requires installed 1.3.0 and durable USER_OFF/DRAIN, makes
verified software/database backups, and preserves settings/source checkout.
The operator subsequently supplied STARTUP_READINESS_INSTALLED for 1.3.1;
both history routes returned seven rows and USER_OFF/DRAIN was retained.

## Publication checkpoint - 2026-10-11

Pi history v1.3.0 is published, with the exact installed wheel and installer.
Pi v1.3.1 was published on explicit operator request on 2026-10-11;
trusted-console installation is now confirmed for the exact released wheel.
Dial v1.3.0-shower.3 was published after operator confirmation of visible history. See the [publication evidence](evidence/2026-10-11-shower-history-install.md#publication-checkpoint).
Release branches are committed/pushed; PRs #24 (Pi) and #14 (Dial) are unmerged.

## Pi 1.3.1 installation complete

Operator receipt matches release source d89827d7e0ea8963f5ed00984c3c0070286e2831
and wheel 90b0faa89b9afcc6304d3f8b978428da0056533c34d813e40ac7e22d4279a812.
Both history routes returned seven rows; operation USER_OFF, command DRAIN,
GPIO26/20 high. Subsequent restricted SSH status independently confirmed all
three services active and both pins high. Backup: /root/freeze-before-startup-psoa_xgm.
Source checkout remains d0dfeac61856e0ff716e700348be61709dc68505 by design;
the installed wheel is 1.3.1. A cold boot with delayed Node-RED remains untested.

## Independent lighting documentation - 2026-10-12

The owner accepted an independent third relay for light control from UniFi
Protect and ESP Dial, normal Dial ON while remaining in AUTO, explicit manual
ON/OFF with a persistent reminder, and automatic return to AUTO after one hour
by default. [Canonical specification](superpowers/specs/2026-10-12-independent-lighting-design.md).
The owner confirmed a five-minute camera hold after the last detection, configurable in admin. The owner specifies LED lighting,
maximum 20 W total at 220 V mains (2026-10-12). The actual driver/contact
suitability and Protect POST authentication/delivery profile remain unverified. GPIO21/header40 comes from the
historical board record and requires actual revision/jumper verification.

No lighting runtime, API, flow, firmware, GPIO or wiring change was made. The
paired daemon still owns exactly GPIO26/20. Node-RED export inspection found
11 nodes and zero structural issues; runtime behavior was not retested.
Documentation drift (manual-only architecture, three routes, old release label)
was corrected against current source and dated installation receipts.
[Reconciliation map](evidence/2026-10-12-lighting-documentation-reconciliation.md)
distinguishes accepted behavior, proposed architecture and missing evidence.

## Independent lighting implementation - 2026-10-13

The owner authorized software implementation. The lighting branch now contains
a separate Python controller, durable settings/history, role-scoped API,
leased GPIO21 executor and disabled Node-RED/gateway/systemd examples.
No existing shower source, paired flow or installed gateway was changed.

At Pi source `1c63837`, full verification passed: 739 Python tests, Ruff,
strict mypy over 34 source modules and Python package build. Nine Node adapter
tests and a structural flow inspection also passed. Task reviews resolved
delayed-command fences, revision recovery and uncertain-response handling.
These checks use fake GPIO; they establish no physical relay/contact behavior.
The companion Dial implementation and its checks are tracked in the
[implementation evidence](evidence/2026-10-13-independent-lighting-implementation.md).

The installed Pi 1.3.1 and Dial v1.3.0-shower.3 records remain unchanged.
Actual Protect version/authenticated POST/event identity, board/driver rating
and power/reset behavior remain commissioning prerequisites. No new release,
firmware upload, service activation or mains connection is included.

### GPIO_SHARED_FSEL2_COEXISTENCE — known activation blocker

**Installed migration verified on 2026-10-14; lighting acceptance remains open.**
The exact kernel-ownership daemon and paired dropin are installed on the Pi.
Restricted SSH confirmed the separate Hub-recovery success marker, all three
services active and paired output/high readback. See the
[dated recovery evidence](evidence/2026-10-14-device-allow-recovery.md).

The legacy userspace FSEL writer is no longer the recorded installed backend.
The source repair and installed migration close that part of
GPIO_SHARED_FSEL2_COEXISTENCE. They do not close the disconnected-load
startup/request/release/crash trace or physical acceptance requirements.
Keep lighting templates, flow and gateway disabled. Do not create
/etc/independent-light/commissioned, set LIGHT_GPIO21_ENABLED=commissioned or
grant light DeviceAllow until the remaining disconnected acceptance is recorded.
Kernel-only configuration does not establish atomic initial direction changes,
crash protection, physical independence or valve position. Actual Protect
profile, Node-RED runtime and lamp/wiring gates remain open.


### Paired GPIO source repair - 2026-10-13

The owner authorized this narrow architecture repair. Candidate source now
holds an exclusive libgpiod request before raw mapping, preloads paired DRAIN,
uses kernel output configuration and retains fixed paired latch writes until
unmapping. Unknown platform/chip/profile/metadata or busy lines fails closed.
The existing installed unit still uses /usr/bin/python3; new dependency/config
and an explicit reviewed interpreter override are required before migration.
Disabled candidate examples are supplied; existing activation assets are not
installed or enabled. Verification is recorded in
[repair evidence](evidence/2026-10-13-gpio-coexistence-fix.md).

### GPIO coexistence repair review closure — 2026-10-13

Pi source44091d6 and Dial operational documentation70bc5b5 completed the
independent task and final integration reviews. GPIO-REVIEW-01 (GPIO bus
metadata topology) is closed;778 software tests and Ruff pass. See the
[final review](evidence/2026-10-13-gpio-coexistence-final-review.md).
The source-level FSEL writer race is repaired. The installed legacy daemon
remains an activation blocker until the reviewed migration and physical
acceptance in the [runbook](operations/paired-gpio-migration.md) are complete.
This record does not change installed versions or authorize activation.

### Paired GPIO migration inventory - 2026-10-13

Restricted helper checks confirm the old paired daemon hash33088ea9 remains
installed, services active and GPIO26/20 high. The owner confirmed both valve
24 V and lamp loads disconnected. Trusted-console inventory identifies Pi4
ModelB Rev1.1/BCM2711, kernel6.18.39, canonical gpiochip0 and legacy gpiomem;
Python3.13.5 has no gpiod in either existing interpreter. An exact gpiod2.3.0
ARM64 wheel is verified for an isolated service environment. The two-stage
migration installer is in preparation; there is no new installed version or
live hardware acceptance. See [preflight evidence](evidence/2026-10-13-gpio-migration-preflight.md).

The [two-stage package](evidence/2026-10-13-paired-gpio-migration-package.md)
is now reviewed and ready for trusted-console prepare. Installer replay and
partial-cutover findings are closed;815 Python tests/Ruff pass. Both operator
prepare/install receipts are pending. No installed state or release changes.

Operator prepare attempt stopped before dependency creation/service mutation:
Hub base-unit bytes differ from the initial package. Historical baseline
packaging correction327d8b8 is tested and independently reviewed; live unit
and readiness-dropin identity confirmation is pending before corrected handoff.
Installed migration is not accepted. See migration package evidence above.

Operator confirmed the historical Hub base/readiness hashes and exact effective
paths with NeedDaemonReload=no. Corrected v2 package matches those identities
and its HTTP hash is verified; old download is retired. New prepare receipt is
pending. This supersedes the identity-confirmation-pending note above only.
