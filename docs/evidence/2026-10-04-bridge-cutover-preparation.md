# Synology cutover helper preparation — 2026-10-04

This records prepared operator tooling, not an executed cutover. The earlier
[image, backup and dry-run evidence](2026-10-03-bridge-fullstack-preparation.md)
remains authoritative for observed Synology state.

## Initial frozen helper and checks

- `cutover.py`: 21,244 bytes, SHA256
  `2d4796b6ef99426f759733fa7213bb2bbf76ebc7f9c4919798d76ebef0c7fa89`.
- `cutover.sh`: 173 bytes, SHA256
  `9f75893439e63ee3dd62c89bf033f86a3cc3f2f5ef8e4835dfde865e4de8694c`.
- Independent scoped review: PASS, no material blocker for the frozen helper.
- Thirteen focused offline tests, shell syntax and Python 3.8 grammar: PASS.
- Existing application source and compiled artifacts are unchanged. No broad
  application suites were repeated for this standalone operator helper.

Tests intercept Docker/HTTP and use local temporary files. Coverage includes
success, fresh checkpoint metadata, ENOSPC, stop/up effects followed by errors,
failed candidate validation, failed original recovery, unknown Compose effects,
process-group cleanup, candidate runtime drift, explicit-empty versus inherited
argv, credential preservation checks and public error suppression. These tests
are not live Docker, NAS, playback or actuator evidence.

## Operation boundary

The helper requires exact original image `b7397d2c7620...`, candidate
`66b41727d29c...`, protected verified backup
`/volume1/docker/unified-hifi-control-4-backup-20261003.ypgw2e8q`, and both original
Compose inputs unchanged from that backup. It privately compares effective
execution settings and environment with actual original runtime. Image tags
must resolve to pinned IDs; image pull/build are disabled.

Before candidate replacement, it stops the original, creates and verifies a
fresh data checkpoint, and extracts/compares/synchronizes a restore tree.
Private candidate/baseline overrides persist under the project in the unique
printed `PRIVATE_STATE` directory. Success requires exact candidate/runtime,
version/source, Roon connection and HTML plus five JS/WASM/CSS hashes. There is
no playback command, credential provisioning, Pi/Dial change or valve action.

Known failure recovery preserves candidate-mutated data, restores the fresh
checkpoint and requires verified original runtime/status/Roon recovery. Local
checkpoint failure before candidate attempts original restart. Unknown Compose
effects prohibit data swapping; failed or uncertain recovery is reported
explicitly. No unattended host/power-loss recovery is claimed. Browser hydration
and user acceptance remain later checks.

## Delivery

`dist/synology-playlists-cutover-20261004/` in the workstation clone contains
reviewed files, report, tests, review and operator instructions. The archive is
16,204 bytes, SHA256
`c2adc34ba5aab0fd4f085a7bbd8d16af83d69060a59dc4ccd20ff044efe3b3da`.
Local HTTP read-back verified that exact digest.

The final operator block checks archive/source hashes, copies helper files to a
fresh root-private persistent `/volume1/docker/uhc-cutover-tool.*` directory,
and runs the reviewed wrapper. `CUTOVER_TOOL_DIR` and `PRIVATE_STATE` are distinct
and must both be preserved. This replaces the README's generic example helper
path with the actual printed tool directory. A deliberate later rollback uses
that same helper and the exact private state path, subject to its documented
limits; do not retry after an unknown outcome without inspecting state.

**Pending:** operator `CUTOVER_VERIFIED` or failure receipt. No actual cutover or
restoration is claimed. Playlist credentials and firmware installation remain
unperformed by this handoff. Pi weather remains staged disabled/manual_timed.

## Operator preflight failure and v2 correction — 2026-10-04

The operator ran the initial helper from
`/volume1/docker/uhc-cutover-tool.lo9BTaHt` and received
`OPERATION_STOPPED=PRIVATE_DIRECTORY_REQUIRED` before `PRIVATE_STATE`.
Read-only operator inspection confirmed original image
`sha256:b7397d2c762076ecfa13abea142374a170aaaed1578a655adfc7bc4a5d7ecd36`
with running=true, host networking and restart=always. The project had mode0775,
uid1026/gid100; newly created `.playlists-cutover-njgal8w` had mode0755,
uid0/gid0. This explains the guard failure. Why the NAS produced0755 is not
separately established. Code order shows this failure precedes preflight,
private state writes and Docker mutations.

V2 explicitly chmods only its freshly created empty state directory to0700
before the unchanged root-owner/type/mode check. It does not reuse the failed
directory or change project, backup or data permissions. The transfer block
also chmods its own newly created tool directory to0700.

- New regression failed against v1 with the exact guard, then passed with v2.
- All15 focused tests PASS, including failure-before-preflight if chmod is
  ineffective. The two new tests model root ownership on a non-root test host.
- Shell syntax and Python3.8 grammar PASS.
- Project pytest576passed, one existing Starlette/httpx deprecation warning;
  Ruff PASS. These tests are not live NAS evidence.
- Independent scoped review PASS for Python SHA256
  `6c259297cb4891c26b510fddb314aee366721715a2a73e63f2da022986b3b08b`.
- Wrapper unchanged, SHA256
  `9f75893439e63ee3dd62c89bf033f86a3cc3f2f5ef8e4835dfde865e4de8694c`.
- Separate delivery `dist/synology-playlists-cutover-20261004-v2/`, archive
  `synology-playlists-cutover-9490cef-v2.tar.gz`,14535bytes, SHA256
  `553527cb9277f67c01d8f1c7f4c0cf6166547447af446b6cb0301e8c405151c2`.

Candidate installation, NAS permission correction and runtime acceptance
remain pending operator execution of v2. Original bridge is running per the
operator's latest inspect. No playback, Pi, firmware, provisioning or valve
operation occurred in this repair phase.

## Successful operator cutover and independent status — 2026-10-04

The operator returned all v2 archive/member hashes OK and:

```text
CUTOVER_TOOL_DIR=/volume1/docker/uhc-cutover-tool.5ZXSqJT5
PRIVATE_STATE=/volume1/docker/unified-hifi-control-4/.playlists-cutover-vgbix_si
CUTOVER_VERIFIED; read-only status and assets passed; playlist credentials NOT_PROVISIONED
```

This is operator-returned helper evidence that the exact candidate passed its
runtime, Roon connection and embedded HTML/static checks. The earlier v1
preflight stop and pending-v2 text above are historical checkpoints.

An independent workstation GET of `/status` at2026-10-03T22:48:16.929780+00:00
(2026-10-04 local) returned service `unified-hifi-control`, version
`0.0.0-valve-candidate.9490cef`, exact git SHA
`9490cef370a17e83480431d1791303fd663abce6`, and roon_connected=true.
This separately confirms the running service identity and Roon connection;
it does not independently repeat the helper's filesystem/runtime checks.

Preserve both printed paths and original backup
`/volume1/docker/unified-hifi-control-4-backup-20261003.ypgw2e8q`.
No rollback was performed. Browser rendering, actual playback and playlist
acceptance are not proved by these GET checks. Playlist credentials remain
unprovisioned; compatible Dial firmware is not yet recorded as flashed.
No Pi setting, weather enablement, valve or playback command occurred in this
verification phase. Published release identities are unchanged.

The operator subsequently confirmed that after opening/refreshing the web UI,
the interface and Sauna zone are visible. This closes the basic UI rendering
check by operator observation; it does not prove playback or favorites.
