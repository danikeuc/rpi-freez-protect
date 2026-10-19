# Read-only reconnect acceptance — 2026-10-19

Operator identification: **gen4-ESP32-28CT**. The PCB revision is still unknown.
The temporary `gen4_28_network_bench` target uses the verified shared LCD path,
`GEN4_TOUCH=0`, and an independent rejection of every POST before transmission.
Normal targets compile out this diagnostic. A compile-time guard rejects
combination with touch controls or the offline bench flag.

## Bounded fault injection

One serial `n` can arm the test only with Wi-Fi connected and fresh Hub status.
The display disables automatic reconnection and disconnects only its own Wi-Fi.
After 30 seconds it restores automatic reconnection and begins the same local
Wi-Fi configuration once. The normal application handles invalidation and status
recovery; the test does not force model validity or modify Hub state.
Phase 3 requires a successful disconnect API result, an observed loss of both
connection and freshness, and recovery within 30 seconds. Phase 4 is failure
or timeout. A reset is required before another test can be armed.

Numeric serial telemetry is whitelisted; credentials and arbitrary logs are
not captured. The host also independently requires sustained offline samples,
status invalidation within 3 seconds, a new connection generation, fresh status
on recovery and zero attempted POSTs. A single valid status poll is not enough
to pass an outage test.

Tests first failed, then passed. Independent review found a false recovery
case (no actual outage) and a late-success deadline issue. A regression
reproduced the failure; both were fixed. Final host suite: **22 tests, zero
failures/ignored**. Final diagnostic build passed in 31.531 s. Source review
passed after the fix. GitHub CI has not run in this session.

## Flash preflight and mutable data

The complete factory-image digest no longer matched after normal network use.
No write followed that failed check. The default 16 MB partition table places
mutable NVS at `0x9000..0xdfff`. Separate ROM checks matched every other byte
of the accepted image: boot `0..0x7fff`, partitions `0x8000..0x8fff`, OTA data
`0xe000..0xffff`, and application at `0x10000`. Thus the mismatch is confined
to NVS, not the program. The precise changed NVS entries were not inspected.

The original full backup and accepted read-only image hashes were rechecked.
A private NVS snapshot was read and verified separately. Subsequent replacement
and restoration use app-only writes at `0x10000`, preserving NVS, boot code,
partitions and OTA data. All images and backups stay in ignored `.pio/recovery/`;
they may contain credentials and must not be shared.

## Device result

Diagnostic app-only image: 1068528 bytes, SHA-256
`cf6ab9de3dfc7de013cd672a244fa20401f67f887a1c3a313b85f8707022aeb7`.
The diagnostic factory's boot/partition/OTA bytes matched the accepted image
before app-only replacement. The app write at `0x10000` completed in 14.2 s;
write digest and independent ROM verification both passed. Logs:
`.pio/recovery/reconnect-write.log`, `reconnect-verify.log`.

The bounded device capture passed (`.pio/recovery/reconnect-result.log`):

| Uptime ms | Phase | Wi-Fi | Fresh status | Generation | Blocked POST attempts |
| --- | --- | --- | --- | --- | --- |
| 6000 | Ready, then armed once | 1 | 1 | 0 | 0 |
| 7006 | Deliberate outage | 0 | 0 | 1 | 0 |
| 37011 | Recovery started | 0 | 0 | 1 | 0 |
| 40019 | Recovered | 1 | 1 | 1 | 0 |

30 offline telemetry samples spanned 29000 ms; loss of connection/freshness
was first observed 1006 ms after the pre-arm sample. The disconnect API
returned success. The scheduler requested reconnection after 30 seconds;
fresh status was restored by uptime 40019 ms. There were zero attempted POSTs.
This validates device Wi-Fi/status recovery for the bounded deliberate outage,
not an AP power failure, arbitrary TCP blackhole or physical actuator behavior.
Human confirmation of the visible transition is pending. The accepted normal
read-only app was restored at `0x10000` in 14.2 s. Its write digest and separate
ROM checks of boot, partitions, OTA data and restored app all matched. The
subsequent hard reset completed successfully. Logs: `readonly-restore-write.log`,
`readonly-restore-verify.log`, `readonly-restore-reset.log` in `.pio/recovery/`.
The temporary diagnostic is no longer installed. After restoration, the
operator reported "nacin samo za prikaz UKAZ:DRAIN", confirming the normal
read-only screen and renewed Hub status reception. This confirms the final
screen, not a separate human observation of the entire outage/recovery sequence.
Restoration app: 1067584 bytes, SHA-256
`a1acb69ed589ee5b8406e16b3c44878da28ae3a9b90beea7610f50334b8bf797`.
This is the application portion of the already accepted read-only factory image.
No GPIO, valve, Hub configuration or access-point changes are part of this test.
