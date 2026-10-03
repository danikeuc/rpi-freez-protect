# Bridge fullstack preparation — 2026-10-03

## Operator evidence

Synology Heimdall is x86_64 with Docker Compose v2.20.1-6047-g6817716.
Container `unified-hifi-control-4-unified-hifi-control-1` was reported running
image `sha256:b7397d2c762076ecfa13abea142374a170aaaed1578a655adfc7bc4a5d7ecd36`,
network `host`, restart `always`, and bind
`/volume1/docker/unified-hifi-control-4/data:/data`.
Operator readlink of `/proc/1/exe` reported `/app/unified-hifi-control`.
These are supplied console observations, not evidence of candidate installation.

## New local artifact

Exact bridge source remains `9490cef370a17e83480431d1791303fd663abce6`.
The earlier 19,734,072-byte server-only artifact is preserved. A new complete
artifact includes the web assets generated with Rust 1.98.1, Dioxus CLI 0.7.10
and Tailwind 4.1.18, followed by the required server embedding rebuild.
All 394 archived source files and Cargo.lock remained unchanged.

- Binary size: 21,288,208 bytes.
- Binary SHA256: `697cec5fd56b5b782d6e331ba998ce744b59e57e9ad7f4ae0a671b7a3d269539`.
- CLI version: `0.0.0-valve-candidate.9490cef`, full source SHA as above.
- x86_64 GNU executable; maximum required glibc symbol version 2.34.
- Required libraries: libgcc_s.so.1, libm.so.6, libc.so.6.
- Fullstack build and embedding rebuild passed.
- GET-only smoke in a separate network namespace with only loopback passed:
  root HTML 200, expected version/source, seven served asset hashes matching
  generated files, valid WASM magic/MIME and all normalized HTML asset URLs 200.
- No live Core, production data or playback was accessed. Browser hydration,
  device interaction and actual Synology runtime compatibility remain unverified.

Local build manifest, report and smoke evidence are preserved under
`/tmp/bridge-fullstack-9490cef-20261003/` and included in the handoff package.
This artifact does not replace the historical software-test manifest.

## Build-only Synology handoff

Package `synology-playlists-9490cef.tar.gz` is 8,724,289 bytes, SHA256
`7931dcac64d91a39818041df97df05b743bb5912c93de7586eb66fa904728fef`.
Final `prepare-candidate.sh` SHA256 is
`fb703c27165ec947965437f3ca49c24e5ec0f498545b27e55337d4d77391491d`.
The scoped independent review approved preparation conditional on final binary
hash pinning; that sole placeholder was filled and independently rehashed.
Shell syntax and exact local HTTP delivery checksum passed.

The script derives a new image from the exact existing local image, replacing
only the executable and adding source labels. It verifies inherited image
execution configuration without printing environment values. The isolated
version check uses no network or production mount. Original container state is
compared before and after; no stop/restart/recreate action is present.
The package is available in the workstation clone's ignored
`dist/synology-playlists-stage-20261003/` directory.

**Pending:** reviewed Compose cutover/rollback,
private scoped credential provisioning, firmware installation and live playlist
acceptance. The later image-build and backup receipts are recorded below.
The candidate is not recorded as deployed. Pi remains staged with weather
disabled/manual_timed; no actuator command or physical test occurred.

## Operator image-build receipt

The operator returned `CANDIDATE_PREPARED` after successfully building
`uhc-candidate:playlists-9490cef-fullstack`, image
`sha256:66b41727d29ce255a2b68be3a1aa1c114bf6550ee6b3cdddba15ac974684d6a6`.
The isolated version command returned `0.0.0-valve-candidate.9490cef` and exact
source `9490cef370a17e83480431d1791303fd663abce6`. This establishes that the
program can load and execute its version path in the derived runtime image.
It does not establish normal startup, browser hydration or live playlists.
The reviewed script's final before/after check reported the original container
and data mount preserved; candidate deployment has not occurred.

Independent GET `/status` at **2026-10-03T20:48:05+00:00** returned the original bridge
`0.0.0-pr6`, `git_sha=b4ba5ac`, `roon_connected=true`. Only these bounded status
fields were retained; no playback command was issued. The temporary candidate
transfer server was closed after the receipt.

## Backup-only helper preparation (before operator execution)

`backup-original.sh` is frozen at SHA256
`57e93de9f6dd4eee8588f6cd87423b2485732573eecf027acf1bd2df4daaf221`
(15,273 bytes). Independent scoped review returned PASS. Seven focused offline
tests, shell syntax and Python 3.8 grammar checks passed. Tests cover successful
backup flow, archive/ENOSPC/stop-response/restart failures, both free-space
guards and a local GNU tar metadata roundtrip. This is not a Synology backup
or restore result.

The operator helper preserves private original image/config evidence, checks
capacity before image save and downtime, stops only the captured original ID
for a metadata-preserving data archive, then attempts to restart that same ID
before any post-stop receipt write. It neither starts the candidate nor
performs cutover. Missing Compose paths remain explicit reconstruction gaps.
Required host Python/tar/fsync checks precede downtime; no tools are installed.
Actual NAS ACL restoration, protection against unrelated concurrent writers
and cleanup after host/power loss or SIGKILL remain unverified.

Reviewed helper, tests, report and review are preserved locally under
`/tmp/synology-playlists-backup-20261003/` and in the workstation clone's ignored
`dist/synology-playlists-backup-20261003/`. The transfer's exact bytes were
verified by HTTP checksum. The subsequent operator receipt is recorded below.

## Operator backup receipt

The operator returned `ORIGINAL_IMAGE_BACKUP_VERIFIED`,
`ORIGINAL_RESTART=VERIFIED`, and
`BACKUP_VERIFIED=/volume1/docker/unified-hifi-control-4-backup-20261003.ypgw2e8q`.
The script reported the original running, candidate not started and no
replacement/playback command. It also reported `COMPOSE_PATH_GAPS=9`.
The later operator path listing below classifies these gaps; neither labeled
Compose input is missing from the backup.
Private original runtime inspect remains preserved. No restore test has been
performed, so backup receipt must not be described as tested restoration.

Independent GET `/status` at **2026-10-03T21:35:50+00:00** returned original
`0.0.0-pr6`, `git_sha=b4ba5ac`, `roon_connected=true`. This supports service
and Roon connection recovery; it is not a playback test. The backup transfer
server was closed after the receipt. The candidate remains uninstalled.

## Compose path reconciliation — 2026-10-04

Operator-supplied filtered backup metadata identifies project
`unified-hifi-control-4`, service `unified-hifi-control`, working directory
`/volume1/docker/unified-hifi-control-4`, and exactly two labeled Compose files:

- `docker-compose.yml`
- `compose.playpause-b4ba5ac-v2.yml`

Both labeled files are present in the backup's saved paths. The nine reported
missing entries consist of the same optional `.env` checked six times and
three unused alternate default filenames (`compose.yaml`, `compose.yml`,
`docker-compose.yaml`). They do not establish a missing active Compose file.
This closes classification of the reported gaps; it does not prove a full
restore or validate every effective Compose setting.

The next operator step is an explicit Compose dry-run using both existing files
and a stdin override selecting the exact already-built candidate tag with
`restart: always` and no pulls/builds/dependencies. The candidate tag must
still match image `66b41727d29ce255a2b68be3a1aa1c114bf6550ee6b3cdddba15ac974684d6a6`
before that preview. No dry-run receipt or cutover has been received yet.
