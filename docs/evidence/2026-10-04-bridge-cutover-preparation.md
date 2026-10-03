# Synology cutover helper preparation — 2026-10-04

This records prepared operator tooling, not an executed cutover. The earlier
[image, backup and dry-run evidence](2026-10-03-bridge-fullstack-preparation.md)
remains authoritative for observed Synology state.

## Frozen helper and checks

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
