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

**Pending:** operator candidate-image build and ABI receipt, protected consistent
backup of original image/config/data, reviewed cutover/rollback, private scoped
credential provisioning, firmware installation and live playlist acceptance.
The candidate is not recorded as deployed. Pi remains staged with weather
disabled/manual_timed; no actuator command or physical test occurred.
