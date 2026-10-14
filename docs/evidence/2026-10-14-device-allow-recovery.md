# DeviceAllow ordering repair and recovery candidate

Operator output confirmed closed policy and exactly /dev/gpiochip0 rw followed
by /dev/gpiomem rw. Old ordered-list equality failed on this valid reversal.
A regression demonstrated one failing reversed-order case before the fix.
Sorted exact-line comparison accepts both orders while rejecting duplicates,
missing/extra devices, changed permissions and unsupported flattened formatting.
The effective-unit verifier is shared with a separate one-shot console recovery.

The original installed package and failed job are immutable historical evidence.
The recovery verifies that exact package, original failure, prepared boot/venv,
backup hashes, installed files, settings/data/flow and idle GPIO before starting
pair, verifying DRAIN and ownership, then starting Hub and checking USER_OFF.
No replacement, automatic retry/rollback, supply/light action or SSH policy change.
Original failed receipt remains; separate recovery SUCCESS.json is authoritative
only after exact target acceptance. Physical state remains unverified.

Full suite: 864 passed, one existing dependency deprecation warning; Ruff and
git diff --check passed. Migration/recovery focused suite:61 passed, including
reverse-order acceptance, broadened permission rejection, changed baseline and
failure rejection, real temporary backup/artifact checks, preserved old evidence,
startup order, no commands on preflight failure and no DRAIN retry after failure.
These substitute host/service/GPIO boundaries and are not hardware acceptance.

Package: paired-device-allow-recovery-20261014-v1.tar.gz
SHA256: 92ff7a1493b06adebd6bf9560ddfa40fd16fa45c72f2d69b8c1c820b0fea24ef
Bytes: 15037
Seven regular members; exact source equality and compilation verified. Inner
manifest pins five runtime/docs files; SHA256SUMS covers those and manifest.
The unchanged operator checks and client match original archive byte-for-byte.
Root-console delivery prepared; recovery has not yet been run on Pi.

[Recovery procedure](../../deployment/paired-gpio-migration/RECOVERY_DEVICE_ALLOW.md).

## Target continuation stopped

The operator verified outer and member hashes and ran the one-shot recovery.
It returned RECOVERY_STOPPED at
/root/paired-gpio-migration.xj0q8tgi/device-allow-recovery. A fresh restricted SSH
status shows the candidate paired service active/running (PID7906), Hub inactive,
Node-RED active and candidate daemon/dropin hashes unchanged. The old maintenance
job still reports the original DeviceAllow error, not this new recovery cause.
The exact new failure must be read from recovery private evidence. No retry,
SUPPLY or further service action was performed after this stop.

## Remote diagnosis and HTTP readiness continuation

After the operator installed the status-only diagnostic update, direct restricted
SSH identified ConnectionRefusedError in recover_device_allow.py167/146 and
operator_checks.py163. Recovery STARTED/FAILED exist; no SUCCESS. Pair PID7906
remains active, Hub inactive and Node-RED active. The failure occurred in the
HTTP status read after pair acceptance and Hub start, not the device allow check.

A bounded refusal-only HTTP readiness wait is added to migration and recovery.
A separate continuation starts only Hub after verifying active pair ownership and
the full preserved baseline. It requires the exact previous failure and callsite;
those source line bindings were verified against the delivered recovery archive.
It also extends status diagnostics to its own fixed recovery directory without
changing any other helper behavior (AST comparison passed).

Full suite889 passed; focused migration/access111 passed; Ruff and diff whitespace
passed. Tests cover bounded refusal handling, no retry for state/auth/HTTP/DNS/
timeout errors, process exit, active-pair preflight, one-shot historical evidence,
and Hub-only start without paired restart. No hardware acceptance is implied.

Package: paired-hub-readiness-recovery-20261014-v1.tar.gz
SHA256: 2d2868e283699a507efa54a237571b89def67a64e58421cdb49403f414f35c8e
Bytes: 20512
New diagnostic helper SHA256: df06b46bd206dbadbbbd201aeb80529df9deb790b7df448b29e1ff2ba15c6a9c
Nine regular members, exact source bytes, hashes and Python compilation verified.
Target continuation has not yet run; no release/commit/push claimed.

## Target recovery verified over restricted SSH

After the operator reported completion, a fresh maintenance status showed
hub_recovery markers STARTED=true, SUCCESS.json=true, FAILED=false at
/root/paired-gpio-migration.xj0q8tgi/hub-readiness-recovery. All three checked
services are active/running: pair PID7906, Hub PID8331, Node-RED PID572,
Result=success, NeedDaemonReload=no. The installed daemon SHA is
ef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f; the paired
dropin SHA is8198c016d5688b0573f68908d3e4e7c0b8e36fcfa33cc6811963daac28f4bacd.
Original Hub/base pair units and readiness hashes remain unchanged. The pair PID
remains7906: this recovery did not restart the running paired service.

A separate original-helper status connection independently returned three active
services and GPIO26/GPIO20 both output/high. Thus source/package, installed
identities, durable recovery success marker, live service state and electronic
readback are distinct corroborating evidence. The complete private SUCCESS.json
was not exported; the reviewed recovery writes it only after USER_OFF, data,
flow, ownership and final readback checks pass. No physical position or fault
injection acceptance is claimed. Lighting remains disabled under the recovery
contract; no third-relay activation, SUPPLY, firmware upload or power reconnection
was performed. Both loads remain under the operator's disconnected envelope.

The original maintenance install job still says MIGRATION_FAILED and the first
recovery still says ConnectionRefusedError. These are preserved historical
failures, superseded for current startup acceptance by the separate successful
hub-readiness recovery; they are not erased or relabelled.
