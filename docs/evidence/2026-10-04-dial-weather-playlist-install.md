# Dial weather/playlist USB installation — 2026-10-04

## Scope and identity

The operator confirmed the dial connected to the workstation USB. COM3 was
identified as ESP32-S3 rev 0.2, MAC`d0:cf:13:1e:15:44`, 16 MB flash and 8 MB
embedded PSRAM. Pi restricted status before and after the work returned three
active services and GPIO26/GPIO20 output/high. No valve or media action was sent.
The prior disconnected 24 V boundary remains in force; GPIO is not valve position.

Prepared source`5eb4c4506b031558bfaa3951d10a98dadc09105a`, ESP-IDF 5.5.5,
app 2,188,928 bytes, SHA256
`acb88426f83e532db3570909e4750126e31dab92e0e525a79c1afed133ac4d34`.
All five preserved Dial artifacts matched the original manifest. Historical
manifest dependency-blocker status was superseded by the separately recorded
owner-approved inventory closure; no source rebuild occurred here.

## Protected backup and writes

A fresh 16 MB full-flash/NVS backup was made with esptool 4.12.0 at 460800 and its
built-in device/host transfer-digest check. Backup is in the workstation's
user-only protected Windows directory
`C:/Users/danik/.codex/private/dial-weather-20261004-effc47e4/`.
File`before-weather-fullflash.bin`: 16,777,216 bytes, SHA256
`fe7586ce682fdc514d313f51755fa57154703e7eb1cae796a8d592009c3f8bd4`.
No private NVS contents were printed or copied into the repository.

The first post-read local fsync used a read-only descriptor, causing Windows
EBADF after the successful flash read. Reopening the completed file r+b allowed
flush/fsync; size, read-back hash and manifest writing then passed. The backup
factory app matched the previous 2,129,600-byte artifact, SHA256
`38e29badcf6e80927ede5acb955204ff1cc65b39a4d971eba2b6271d8bd25c58`.
The backed-up partition table matched the candidate. An immediate pre-write
16 KiB NVS read was byte-identical to the full-backup NVS at 0x9000.

Four regions were written: bootloader 0x0, partition table 0x8000, initial OTA
data 0xd000, application 0x10000, using dio/80MHz/16MB. No whole-chip erase.
Both write-time verification and a separate verify_flash passed for all four
regions. Esptool updates the bootloader flash-parameter header/digest; separate
verification used the same parameters, so this is a verified tool-transformed
bootloader, not a claim of unchanged raw bootloader-file bytes on flash.
A further NVS read before boot was byte-identical to the immediate pre-write
copy. These records do not prove later runtime persistence or a tested rollback.

## Bounded startup and read-only checks

A 50-second serial observation emitted only allowlisted metadata, no raw logs:
273 lines, 1 startup, 0 selected fault markers, app label`2.5.3-valve.1-dev`,
ELF prefix`ea03fb082`, IP`192.168.114.173`, configured zone
`roon:16017dc9fce2394fbbeffe3b7e26203cd174`, minimum observed valve-worker stack
5596/12288bytes. The ELF prefix matches the preserved ELF artifact; the fixed
version label alone is not source attestation. This is bounded boot evidence,
not long-term stability or resource exhaustion proof.

GET /admin 200; GET /admin/api/session 200 with setup_required=false and
authenticated=false; unauthenticated GET /admin/api/settings 401. Existing PIN
configuration is present; successful user login and settings behavior require
operator observation. The post-flash restricted Pi status again found three
active services and both outputs high.

## Remaining work

Operator screen/PIN acceptance was requested. Scoped playlist credentials and
weather-settings credentials remain unprovisioned by this phase. Live favorites,
queue replacement, encoder/touch/rotations and weather behavior need separate
runtime acceptance. Weather remains at the earlier disabled/manual_timed staging
checkpoint; this USB installation did not change Pi settings. No playlist/media
command, timed shower, physical test, merge, tag or release was performed.

## Newly identified provisioning blocker

Before entering any playlist credential, source inspection found both real
NVS branches use namespace`playlist_private` (16 characters). The exact build
ESP-IDF 5.5.5 nvs.h defines NVS_NS_NAME_MAX_SIZE=16 includingNUL, and explicitly
limits namespace names to 15 characters. Existing PLAYLIST_HOST_TEST persistence
bypasses nvs_open, so its passing token tests did not establish device storage.
The installed app is not accepted for playlist provisioning. A narrow namespace
correction and production-path regression are in progress; no failed user
credential entry or secret disclosure occurred. The successful flash/boot
evidence above remains valid for its limited scope.

## Namespace repair source checkpoint

Source commit`4c0a15c08f1ca05fb948cc8c65890ec423eeedf9` uses shared
`playlist_priv` for both real NVS calls and asserts its size, including NUL,
against NVS_NS_NAME_MAX_SIZE. No valid credential namespace could previously
be created under the rejected16-character name, so no persisted credential
migration is claimed or required for this unprovisioned device.

The new regression compiles the real production persistence branch against
the exact ESP-IDF nvs.h with a file-backed NVS adapter enforcing name limits.
It failed before repair and passes afterward, covering separate-process
restart, exact endpoint binding, storage failures and failed readback. The
implementer reports full playlist/admin/valve runners and dependency checker
plus self-test PASS; dependency policy is unchanged.

Independent source/test-design review PASS, no material blocker. Source file
SHA256`9eb56f626ace0b4c99b6fd15529aad394c30689eed01e2fc24dd7585c85f43af`.
Independent test execution was not completed: cc was absent, and automatic
approval review rejected the temporary compiler wrapper and its inspection
over unverified execution/private-data concerns. No bypass was attempted;
implementer test results and independent source review remain distinct.
Firmware rebuild and device installation of this repair were pending at this
checkpoint. No credential has been entered or tested on the device yet.

## Repaired firmware installed and observed

The isolated ESP-IDF5.5.5 build for source
`4c0a15c08f1ca05fb948cc8c65890ec423eeedf9` passed1827 steps. App remains
2,188,928bytes with16% partition headroom; SHA256
`7bad18553d3bcb117054bd9c16f6fccb52ad0caa57d6fb9ab839f6a446cd6e3f`.
ELF SHA256`6dac51ba6fcc43cfbf604164ff766ce7fd164762830b362036c5a41a76ca0bdd`.
Locked components and sdkconfig were byte-identical; dependency policy did not
change. The new build's bootloader file differs, but was not installed.

A fresh protected NVS snapshot`nvs-before-4c0a15c.bin` was read and flushed in
the same private backup directory. Only application0x10000 was replaced.
Previously verified bootloader, partition table and initial OTA regions were
retained; partition/OTA artifacts and build settings match. Both write-time
verification and separate verify_flash passed for the exact repaired app.
The subsequent NVS read was byte-identical to this fresh snapshot before boot.
The original full-flash backup and both candidate artifact sets remain intact.

A second50second allowlisted boot observation returned273lines,1startup,
0selected fault markers, expected ELF prefix`6dac51ba6`, same fixed version
label, IP`192.168.114.173`, the same exact Sauna zone ID and valve-worker
minimum5596/12288bytes. GET/admin and GET/admin/api/session returned200,
setup_required=false/authenticated=false; unauthenticated settings returned401.
Post-repair restricted Pi status again found all three services active and
both GPIO outputs high. These bounded observations do not test token
persistence, login, playback or physical valves on hardware.

Source-level namespace blocker is fixed and that repair is installed. Actual
private credential provisioning and hardware save/reboot acceptance remain
pending. The earlier requested operator screen/PIN check has no recorded reply
yet. No media/valve command or weather enablement occurred during either USB
installation. Source commit is local; no push/merge/tag/release is claimed.


## Operator admin observation and incomplete connection setup

On 2026-10-04 the operator reported that the admin page opens but location and
playlist controls cannot save; hovering shows a busy cursor without an action.
The supplied screenshot shows authenticated settings, unavailable weather and
playlist status, and disabled save/browse controls. This establishes that the
operator reached the settings page; it does not establish successful saving.
Coordinates entered in the screenshot are unsaved input, not verified Pi state,
and are intentionally not reproduced here.

At installed source `4c0a15c08f1ca05fb948cc8c65890ec423eeedf9`,
`idf_app/main/admin_page_dial.h` applies `cursor:wait` to every disabled button.
The weather and playlist unavailable handlers disable controls when their
confirmed revision is absent. Thus the cursor does not demonstrate a pending
save request. The presentation is misleading for unavailable connections.

Deployment records still leave the separate weather-settings and playlist
credentials unprovisioned. Unauthenticated GETs of both scoped backend routes
returned 401; these responses alone do not establish server configuration.
Bridge read-only status remained source `9490cef370a17e83480431d1791303fd663abce6`
with Roon connected. Private operator-local connection setup is being prepared;
no credential setup success, location save, playlist selection or weather
activation is claimed by this observation.


### Pi connection helper prepared, not yet executed

The reviewed operator-local helper appends only the previously absent weather
settings credential, preserves the original environment in root-private state,
and checks manual idle DRAIN/disabled weather/services/paired HIGH before and
after a bounded Hub restart. It uses the existing protected Dial form with
Origin, session cookie and CSRF, then reads weather settings through the Dial.
It does not write a location, enable weather assistance or issue a valve action.
An ambiguous Dial write retains the backend credential and private recovery
state; rerunning is intentionally refused rather than rotating credentials.

Frozen helper SHA256 values:

- `common.py`: `548b608399ccca70627c232f70ec285d292753b8593c6ec5cd91d8902e38e3b9`
- `weather.py`: `44bebbc94ddae8da334bc98dbad843e6bc40cf4674999669ef3033a1ae282d8d`
- Pi-only `weather-connection.tar.gz`: `491ea3d7a28d43446dfaa33d04033d526fc09a65a0972bcce2def672442ad27a`

Independent source review passed with the explicit uncertain-result recovery
advisory; independent offline execution passed 18 focused tests. Helper Ruff
passed. Repository checks passed 576 tests (one existing dependency deprecation
warning), Ruff and 110 commissioning-asset tests; documentation link test passed.
A temporary Pi-only transfer server was started and its archive hash verified
from the workstation. Live execution and credential persistence remain pending
operator receipt. Synology credential setup remains a separate next step.


### Pi connection attempt stopped before configuration changes

The operator verified all transferred hashes but received
`PROVISION_STOPPED=UNCLASSIFIED_FAILURE` after entering the existing PIN, with
no PRIVATE_STATE receipt. A Pi-side unauthenticated session GET returned
setup_required=false/authenticated=false. The reviewed login-only diagnostic
then reported PIN_INPUT_OK, successful READ_SESSION, and TimeoutError during
LOGIN at common.py's eight-second opener timeout. This localizes the failure
to waiting for login; it does not establish a wrong PIN or a hashing defect.
Backend mutation is later than this failed stage and was not reached.

A second login-only diagnostic keeps eight seconds for session/logout and
allows thirty seconds for the single login attempt, adding monotonic elapsed
times. SHA256 `48a4b25119bef309f88e39f50f3220f2cf4e4618900ac9283f11bac66be93144`.
Four offline tests and Ruff pass; independent source review passes. The
firmware uses 100000 PBKDF2-SHA256 iterations, so slow PIN verification is a
hypothesis to measure, not a confirmed root cause. The original provisioning
helper remains unchanged. No weather credential configuration is accepted yet.


### Login timeout confirmed and Pi helper v2 prepared

Operator diagnostic receipt: PIN_INPUT_OK, initial session GET 0.04 s,
LOGIN 8.53 s, authenticated session GET 0.02 s, LOGIN_VERIFIED, logout 0.03 s,
and DIAGNOSTIC_COMPLETE. The measured successful login exceeds the original
eight-second helper timeout. Authentication delay origin is not established;
PIN verification itself succeeded. No provisioning was performed by that test.

Pi helper v2 changes only the exact Dial login POST timeout to thirty seconds;
all other calls keep eight seconds and no retries are added. Two regressions
failed against v1 and pass against v2; all 23 helper tests and helper Ruff pass.
Independent source review passes. Common SHA256 is
`9aa1dca7e8b3d9761e5c546add0c2f876e685e1fc3710f6fb235fdda49bc8d64`;
weather.py remains byte-identical to the reviewed original. Archive SHA256 is
`5dbf343744dfc8acc12cd15df89bc5226efb917d977087878d7b980857937c62`.
Transfer hash verified. Live weather connection provisioning remains pending.


### Pi weather connection provisioned

Operator receipt on 2026-10-04: PRIVATE_STATE=`/root/.scope-provision-_x54h4n1`,
WEATHER_CREDENTIAL_VERIFIED, manual_timed, weather_enabled=false, no weather
setting or action changed. This is execution evidence for the v2 helper's
backend and authenticated Dial weather readback gates, with its protected
original environment and credential recovery state retained on the Pi.
It does not establish a location save, enabled weather behavior, reboot
persistence or physical water routing. Playlist provisioning remains pending.


### Configuration HTTP stack repair packaged; not installed

The operator's follow-up read-only diagnostic passed private runtime, backend
status/capabilities/favorites and Dial session/settings/weather reads. Dial
favorites still returned503 unconfirmed in37ms; logout returned200. The
credential save remains unconfirmed and CONTINUATION_SAVE_PENDING must be
retained. No further credential submission was performed.

Local Dial revision358fff1ba6bacbac84cee8018d0b003d7a2de66a already contains
the scoped HTTP task-stack repair, parent4c0a15c. Its existing review records
a supported8256-byte call chain against the8192-byte HTTP task stack, and
raises that budget to16384. This is a source/artifact defect; the particular
observed reset/timeout still lacks a captured panic proving that cause.

After the host changed to native Windows, the former temporary SDK/build
directories were unavailable. ESP-IDF v5.5.5 and its ESP32-S3 toolchain were
restored from official sources under /home/danik/.cache/freeze-build. An
isolated Git archive of exact358fff1 plus the current sdkconfig and locked
managed components built successfully. Original and isolated sdkconfig/lock
bytes match. No tests were rerun in this continuation; prior source-review
test claims remain the dated evidence in the Dial review document.

Package: C:/Users/danik/Projects/rpi-freez-protect/dist/dial-config-stack-358fff1-20261004.
App length2188928 bytes, SHA256
4d029f487e394bccfe00be4c51f78fe260117f802d8d7864fdf57c8f18cb7b5f.
Manifest pins every artifact. A separate Windows hash read confirmed all
packaged hashes and unchanged partition-table/initial-OTA bytes against4c0a15c.
Planned write is factory application at0x10000 only, after a new private full
flash backup and active-partition check; preserve NVS/bootloader/partition/OTA.
No USB port was opened and no firmware was written. COM3 is enumerated. A
fresh restricted Pi status returned three active services and paired output
HIGH/HIGH; this does not prove valve position. Exact-artifact upload approval
and device acceptance remain pending.


### Approved stack repair installed; playlist acceptance pending

The operator explicitly approved the fresh backup and exact 358fff1 firmware
upload on COM3. On 2026-10-04 the chip identity matched ESP32-S3 revision 0.2,
MAC d0:cf:13:1e:15:44. A new private 16 MiB full-flash backup was completed and
verified against the expected 4c0a15c application hash, partition table and
initial OTA selection (factory). Candidate artifact hashes also matched.
Private backup: C:/Users/danik/.codex/private/dial-stack-20261004-b1f1cc14.

Only the factory application at 0x10000 was written. Esptool verified the
application digest. Before starting it, the first 64 KiB were read back and
matched the backup byte-for-byte: bootloader, partitions, NVS and OTA metadata
were preserved. App SHA256 remains
4d029f487e394bccfe00be4c51f78fe260117f802d8d7864fdf57c8f18cb7b5f.

A bounded 40-second redacted serial observation captured boot and expected IP,
ELF SHA prefix 5ed7ee58a matching the packaged ELF, with none of the monitored
panic/stack/watchdog/brownout/assert/abort markers in 270 lines. This is bounded
startup evidence, not sustained or configuration-save acceptance. The admin
session endpoint responded with setup_required=false, authenticated=false.
Restricted Pi status again returned three active services and GPIO26/20 HIGH.
No physical valve position is inferred. No credential submission, playback,
weather setting, relay action or service change was performed.

Public artifact execution record: dist/dial-config-stack-358fff1-20261004/
installation-evidence.json. The original build manifest remains a preparation
record. Authenticated Dial favorites readback has been requested from the
operator. CONTINUATION_SAVE_PENDING remains untouched; another credential save
has not been authorized by this firmware-upload approval.


### Missing playlist credential localized after stack repair

Operator authenticated readback still returned {"error":"unconfirmed"}.
The official ESP-IDF v5.5.5 nvs_partition_tool parser inspected the private
preserved-after.bin NVS region (0x9000..0xcfff), which matched pre-flash bytes.
All nonempty page header CRCs matched. Across Written entries of Active/Full
pages, namespace playlist_priv count was zero and no credential entries existed.
Only this redacted presence report was emitted; credential bytes were not printed.
Thus the inspected installed snapshot cannot satisfy playlist_private_load,
which returns failure before any network request. No subsequent config save
has been performed by the agent. This localizes a concrete cause without proving
that the historic timeout itself was caused by stack overflow.

Prepared, not executed: dist/playlist-stack-recovery-20261004.tar.gz,
SHA256 35717082328555b04ac8245aff85bd7de6be6d968d50ff98bd01d9a1207962c4.
It retains original checks, requires the original CONTINUATION_SAVE_PENDING,
claims a distinct exclusive STACK_358FFF1_SAVE_PENDING before one same-token
save, requires explicit approval flag, and extends the config response timeout
to 30 seconds. Syntax parsed; no full-suite or device acceptance claim.
Separate same-token save approval is pending; firmware approval alone was scoped
to backup and application upload. Old pending markers remain untouched.

Operator approved the single same-token stack-recovery save. Scoped package transfer service started on 192.168.111.30:8765 for two hours; local HTTP byte hash verified. Human Synology execution and device readback remain pending.


### Approved recovery stopped at weather read, before credential write

Operator supplied verified archive and six file checksum receipts. Private
runtime, bridge status/capabilities/favorites and Dial login/bridge/settings
passed. DIAL_WEATHER returned HTTP 503 UNAVAILABLE after 3047 ms and
DIAL_CURRENT_SETTINGS_WEATHER_DISABLED failed; logout passed. The execution
never reached DURABLE_SINGLE_SAVE_GUARD or DIAL_SAVE_SAME_TOKEN_ONCE. This
receipt therefore records no credential save in this run; no marker deletion
or automatic replay is permitted.

Follow-up workstation checks: restricted Pi status returned three active
services and paired HIGH/HIGH. Unauthenticated weather-settings and display
status requests to Pi port 8081 returned 401 in 672 ms and 171 ms; Dial session
returned 200 in 78 ms. These prove route reachability from the workstation,
not Dial-to-Pi authenticated weather access. Firmware transport uses a 3000 ms
per-operation timeout; the observed 3047 ms failure is consistent with that
boundary but does not identify the exact cause. Operator authenticated weather
GET requested next; settings and weather policy remain unchanged.


### Operator receipt: playlist connection already established

After the operator confirmed weather assistance disabled, the recovery receipt
passed private runtime, bridge status/capabilities/favorites, Dial login,
bridge/settings/weather-disabled snapshot and authenticated Dial favorites.
DIAL_FAVORITES returned HTTP 200 in 93 ms and passed the expected Sauna zone
check. Final private runtime and logout passed. Final result:
PLAYLIST_CONNECTION_VERIFIED=ALREADY_CONNECTED.

This run did not reach the credential-write guard or save phase, so no token
was resubmitted and no Docker, valve, queue or playback mutation was performed.
The current authenticated device result supersedes the older backup-based
absence finding for current connectivity. The earlier snapshot lacks the
playlist namespace, but when/how current credentials became available is not
established by these receipts; do not infer a successful write by this run or
claim a proven causal link to weather being disabled.

Connection acceptance is verified by operator receipt. Admin catalog selection,
favorite persistence and physical Dial playlist-start playback remain separate
acceptance steps. Weather was confirmed disabled by this run's preflight.


### Playlist save observed; picker contrast correction prepared

Operator screenshot shows saved-and-reread status and one Zen Spa favorite,
with GET favorites 200. Earlier save-failure cause is unresolved. Operator
then reported dark text on dark background on the physical playlist picker.
Source set background 0x111827 but no label text colors. Minimal patch now
sets title/selection 0xF9FAFB and zone/hint 0xCBD5E1 explicitly on creation.
No input, playback, storage or weather logic changes.

ESP-IDF v5.5.5 build and git diff --check passed. Artifact manifest pins base
358fff1 plus the uncommitted source.patch and binaries. Package:
C:/Users/danik/Projects/rpi-freez-protect/dist/dial-playlist-contrast-20261004.
Firmware NOT_FLASHED; physical contrast acceptance pending.


### Approved picker contrast firmware installed

Operator explicitly approved backup/upload of the prepared contrast artifact.
Fresh private 16 MiB backup at C:/Users/danik/.codex/private/
dial-contrast-20261004-a1074712 passed device MAC, baseline 358fff1 app,
partition table and factory OTA-selection checks. Only application 0x10000
was written, hash c2309d07ccb6b8f233ac4f30bdedeb5a9e2db6fef4fee772644e4ee8339f7507.
Esptool digest verification passed. Before boot, readback of first 64 KiB
matched the fresh backup exactly, preserving bootloader/partitions/NVS/OTA.

40-second redacted serial observation: 258 lines, BOOT and expected-IP markers,
ELF SHA prefix 13a6d404e matching the packaged ELF, no monitored fault markers.
Admin session reachable, setup_required=false. Restricted Pi status: three
services active, GPIO26/20 HIGH. No playback, weather or valve action issued.
Package installation-evidence.json records the execution separately from build
manifest. Physical readability and playlist selection/playback acceptance
remain pending operator observation. Source remains base 358fff1 plus the
included contrast patch; no release or commit claim.


### 2026-10-05 accepted-command wording fix prepared

Operator confirms audible playlist playback after short tap. Client now separates
explicit accepted receipt from uncertain transport (WAITING); UI retains accepted
knowledge only for current picker, displaying accepted-but-not-playback-verified
on final unknown. No automatic resend. UI regression failed before fix; complete
playlist test suite, git diff --check and IDF v5.5.5 build passed. Package
dist/dial-playlist-acceptance-20261005 pins source patch and binaries; NOT_FLASHED.
LVGL render fixture now checks all four contrast colors.
Operator also reports failed multi-playlist save reloading previous single Zen
Spa favorite. Cause unlocalized; requested draft count/names before saving.


## 2026-10-05 — long-playlist save defect reproduced and corrected locally

Operator screenshots show four draft favorites (Female Voice, Buddhattitude,
Costes, NinaSimone) reverting after Save to the previous single Zen Spa favorite.
Inspection found resolve_playlist_exact rejected detail.list.count > 50, although
that count includes all tracks and the load request only limits a page to 50.
Regression with 100 extra fake tracks failed before the fix with the exact
playlist-detail-shape error, then passed after validating detail.offset and
detail.items.len() instead. Unique exact Play Playlist / Play Now checks remain.
All 52 targeted API/catalog/playback/protocol tests passed; no live playback.
Bridge base 8abe29d455087a01552c71cbcdfaff7fa95df99d plus source.patch in
dist/bridge-long-playlists-20261005. Local build preparation only; Synology
installation and real four-favorite save/readback remain unverified.

Final fullstack candidate build PASS using Rust 1.98.1 and Dioxus 0.7.10.
Rust 1.99 attempt failed WASM packaging and was not packaged.
Isolated loopback-only HTTP smoke PASS: exact candidate status, no connected Core,
root HTML and all seven routed CSS/JS/WASM/icon assets match build bytes.
Archive SHA256: 75a42e9f49f5df9f2dffceb7e1820285345b955c3344ccd84edcb562c066d6b2.
State: BUILT_AND_ISOLATED_SMOKE_PASSED_NOT_DEPLOYED.
Synology ABI check and real four-playlist save/readback remain pending.

## 2026-10-05 — operator-reported Synology cutover verified

Operator prepared candidate image prefix 5ea25aada34c and verified executable
version 0.0.0-playlist-long-candidate, source
8abe29d455087a01552c71cbcdfaff7fa95df99d+playlist-long-fix.
Subsequent operator output verified cutover archive SHA256
4d1ca9079e9f2df044715520604206cb84479b81ff231ac67136f19e031bd0f6
and all inner checksums, then reported CUTOVER_VERIFIED: long-playlist fix active;
runtime settings and credentials preserved; device save test pending.
Tool directory: /volume1/docker/uhc-long-cutover.qRF90sL4
Private checkpoint: /volume1/docker/unified-hifi-control-4/.playlists-cutover-e601tnvc
Evidence source is pasted operator output, not an agent SSH execution.
Four-favorite save/readback and Dial rotation remain unverified. Browse afresh
after the bridge restart before selecting favorites. Separate Dial accepted-
command wording candidate remains NOT_FLASHED. No live playback or valve test
was performed by the cutover helper.

## 2026-10-05 — operator acceptance failed after verified cutover

Operator reports four-playlist save still does not persist. Screenshot after
refresh shows old Zen Spa favorite with re-selection required. CUTOVER_VERIFIED
establishes installation/read-only health, not resolution of the reported defect.
Live agent GET /status verified expected long-playlist candidate and Core connected.
Agent browsed a separate diagnostic session through Playlists -> Female Voice
(detail count93) -> Play Playlist menu, then Buddhattitude (count70) -> menu.
All navigation succeeded in15-46ms per combined browse/load HTTP call. Both menus
contained exact Play Now/action. No action execution or favorites write sent.
Costes/NinaSimone were not on first50 catalog rows and were not examined.
Dial admin has5s job budget/3s socket-step timeout and hides backend non-200 bodies.
These are hypotheses/boundaries, not proof of remaining cause. Requested browser
PUT favorites Status Code and Response; diagnosis pending this evidence.
No additional source fix, deployment, credential write or playback performed.

## 2026-10-05 — operator confirms playlist workflow works

After clarification of the catalog/Add/Save workflow, operator said saving now
works and subsequently confirmed the Dial flow works. Treat as operator-reported
save and picker acceptance; no new API capture, fresh independent readback,
playback/queue verification or fault injection was performed in this turn.
The earlier failed-save screenshots remain part of the evidence history.
The exact contribution of the prior resolver defect versus selection UX to each
failed attempt was not proven by a captured PUT response.
Operator now requests better UI/UX. Design discussion started; no UI changes
or additional firmware deployment yet.
