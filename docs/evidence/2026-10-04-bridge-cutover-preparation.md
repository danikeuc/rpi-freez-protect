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


## Playlist connection helper prepared after Pi acceptance

The operator returned WEATHER_CREDENTIAL_VERIFIED with manual_timed and
weather_enabled=false and protected Pi state `/root/.scope-provision-_x54h4n1`.
The next prepared Synology helper adds only UHC_DIAL_TOKEN_SHA256, UHC_DIAL_ID
and the exact Sauna UHC_DIAL_ZONE_ID, preserving the current candidate image,
host network, restart policy, data mount and three existing Compose inputs.
Its new private scope.json becomes a required fourth input for future upgrades.
No playlist selection, queue operation, playback or actuator request is sent.

Frozen files (SHA256):

- common.py: `9aa1dca7e8b3d9761e5c546add0c2f876e685e1fc3710f6fb235fdda49bc8d64`
- playlists.py: `413e5f8294b6bed1153b0ca7b23d46e80ec8b476e7e5a43561292db45d43e9b9`
- unchanged cutover_checks.py: `6c259297cb4891c26b510fddb314aee366721715a2a73e63f2da022986b3b08b`
- playlist-connection.tar.gz: `93afc346d0ee922a3d2ca923cf014d1e628cb3fedc64f25ad9ba7265209d3858`

Independent source/API/recovery review PASS_WITH_ADVISORIES; independent
23-test offline run passes. Implementer rerun and Ruff pass. The corrected
30-second login timeout is included. After credential save, the old session
must become invalid before fresh login and unchanged weather/duration/rotation
readback; this is limited restart evidence, not a separate boot identity.
Keep admin idle during that observation. Ambiguous save outcomes retain the
backend token and private state for an exact-state continuation, not a rerun.

A Synology-only temporary transfer server was started, and the archive digest
was independently read back locally. This records prepared delivery only;
live Synology credential provisioning and playlist acceptance await receipt.


### Initial connection preflight stopped; saved endpoint confirmed

Operator received raw PROVISION_STOPPED=DIAL_BRIDGE_CHANGED before the helper
returned PRIVATE_STATE. In this helper the unwrapped error occurs at the first
Dial bridge read, before Docker mutation. Operator confirmed the saved base is
`http://192.168.111.130:8088`. The initial helper incorrectly required a /roon
suffix; the firmware appends /roon itself when absent. This was a helper
compatibility defect, not evidence that the user's saved bridge had changed.

The corrected helper accepts only the two exact bases on the same pinned
host/port, with or without /roon, and preserves the original string. It rejects
other paths, hosts, userinfo, query/fragment, missing/duplicate inputs and
trailing slash forms. New regressions failed against the earlier helper;
all 25 offline tests pass, independently rerun, and independent source review
passes with the existing recovery/session/Compose-input advisories. Common
SHA256 is `3eef95d8f0f9d5aca3277135b027669ca982b1eebbe1a0e6149d3064390a3cc1`;
playlists.py and cutover_checks.py remain byte-identical. Corrected archive
playlist-connection-v2.tar.gz SHA256 is
`b38e0697094be4a9cbf7876b717b386f937d3b2e687af0f3e46c664917949051`.
Transfer digest verified; repository 576 tests, Ruff and 110 commissioning
checks pass. This corrected setup still awaits an operator success receipt.


### Weather preflight stopped before Synology changes

The operator verified the corrected package and reported raw
PROVISION_STOPPED=WEATHER_DISABLED_REQUIRED, with no PRIVATE_STATE receipt.
The initial Dial snapshot runs before private setup and Docker mutation.
Firmware source confirms that enabled is a top-level boolean in the weather
GET response. Operator later confirmed the admin displayed weather enabled;
this was an intentional preflight rejection, not an API schema defect.

A read-only restricted Pi status found all three services active and paired
GPIO26/20 output/high. The operator was instructed to save weather assistance
disabled and replied affirmatively after the request for confirmed-disabled
state. Treat this as operator-reported settings state; the unchanged helper
must re-read and verify disabled state before continuing. The same reviewed
archive was re-served with verified digest. Synology provisioning still awaits
a success receipt; no hardware or physical valve acceptance is implied.


### Scoped backend verified; Dial provisioning unconfirmed

Operator receipt from the corrected helper:
PRIVATE_STATE=`/volume1/docker/unified-hifi-control-4/.scope-provision-80suk28s`,
PROVISION_STOPPED=DIAL_PROVISION_UNCONFIRMED. This label occurs only after the
backend apply/verification gates and during the later Dial save/readback path.
The helper deliberately retains the backend scope and existing token; do not
rerun initial provisioning or delete private state. The required fourth Compose
input is the private directory's scope.json. The exact failed Dial substep was
not recorded by the original helper and remains unknown.

Subsequent independent public GET status returned bridge source
9490cef370a17e83480431d1791303fd663abce6 with Roon connected. Dial session GET
returned200, setup_required=false/authenticated=false. Operator refreshed admin
and still saw unavailable playlists; authenticated Dial favorites GET returned
{error: unconfirmed}. Thus a working Dial playlist connection is not accepted.
These GETs do not establish whether the existing token was committed in NVS.
An exact-state continuation with the same token is being prepared, with no
container replacement, new token generation, playlist playback or valve action.


### Same-token continuation reviewed; operator execution pending

Authenticated operator GET `/admin/api/roon/favorites` returned
`{"error":"unconfirmed"}`. This does not distinguish missing/private credential
from downstream capability, connection or response validation failure.

The exact-state continuation audits the saved private token and scope, current
runtime, all four active Compose inputs, and direct backend status/capabilities/
favorites before authenticating the Dial. It requires the unchanged bridge
origin and disabled weather. A working favorites read skips saving. Only the
recognized503 unconfirmed/bridge_credential response permits one protected
form write of the same token and origin. An exclusive durable pending marker
prevents resend across process restarts. Any uncertainty stops the operation.
No Docker mutation, token generation, playback or valve command is performed.

Reviewed continuation SHA256:
`fc36554424344a105a5dc731cb6b99e6f5e0b7a8545f7a3c7c9e102148a602fa`;
diagnostic module SHA256:
`ddad3acf1577b08dbb587feeced5a27ca6ee3fc7413f30197a4048451a52b8d7`.
Independent source review passed with advisories; independent and root offline
execution each passed18 tests, including scope/hash drift, failed initial audit,
weather-enabled rejection, one-save behavior and redacted error output. Ruff
passed. These are local helper results; live connection remains unconfirmed.
Original pre-failure Dial settings were memory-only and cannot be reconstructed;
continuation compares only its own current before/after snapshots. Session
invalidation is limited restart evidence, not physical or power-cycle proof.


### Continuation save response failed; no automatic resend

Operator returned verified transfer hashes and passing private runtime, backend
status/capabilities/favorites, Dial login, unchanged bridge and disabled-weather
gates. Initial Dial favorites remained503 UNCONFIRMED. The repeated pre-save
audit passed and CONTINUATION_SAVE_PENDING was durably created. The single
DIAL_SAVE_SAME_TOKEN_ONCE attempt failed after8012ms with OS_ERROR, without an
HTTP status receipt. Cleanup logout returned401 UNAUTHORIZED. Preserve both
the private state and pending marker; do not resend the credential form.

Source sends a success response after credential commit/readback and then
restarts after one second. Session loss is consistent with a restart but does
not prove that this successful path completed; reset/failure remains possible.
Neither timeout duration nor401 establishes token persistence. A fresh login
and read-only favorites check is pending. No Docker mutation, playback or
valve command was attempted by this continuation.


Operator returned continuation receipt on 2026-10-04: private/runtime and
backend status, scoped capabilities/favorites, Dial login, unchanged bridge,
settings and weather-disabled checks passed. Dial favorites still returned
503 unconfirmed. The single same-token form attempt ended after 8.012 s with
OS_ERROR; subsequent logout returned401. The durable
`CONTINUATION_SAVE_PENDING` marker had already been fsynced, so no retry is
allowed. These results do not prove whether NVS accepted the token before the
connection ended. Run only the packaged read-only diagnostic (fresh login,
GET bridge/settings/weather/favorites, logout) to establish current state; it
never submits `/config`. Playlist acceptance remains pending that receipt.
