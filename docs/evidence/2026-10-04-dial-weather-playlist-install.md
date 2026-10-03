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
