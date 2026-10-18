# Limited maintenance access candidate - 2026-10-14

The owner requested execution after the earlier documentation-only step.
[Implementation and operational contract](../../deployment/maintenance-access/README.md)
limit the extension to fixed diagnostics and the exact reviewed paired-GPIO
migration archive. No generic shell, restart or package API is introduced.

## Candidate identity

- Package: `maintenance-access-20261014-v1.tar.gz`, 139471 bytes.
- SHA256: `2d09b5f13bd9a0ff2156b8a07167ac48ebad73d75ae6a3987f0a2a767e5c5078`.
- Nested migration SHA256: `f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513`.
- Nine regular outer members; fixed file names; all manifest and SHA256SUMS
  entries verified. Both packaged Python sources matched the working-tree files at the v1 build.
- Source is a working-tree candidate, not a committed release or Pi installation.

## Validation

Final full repository suite: 833 passed.
Focused access, commissioning and documentation suite: 128 passed. This covers
exact SSH dispatch and argument rejection, original-command compatibility,
package mismatch, boot/expiry/disconnection approval, durable single-use claims,
failed dispatch, missing preparation, malformed receipt paths, large prepared
venv inventories, sanitized diagnostic output, worker failure, concurrent worker
start, installer baseline mismatch and failures before/after dispatcher replacement.
The configured Ruff check passed. Shell syntax is exercised for generated dispatch
in the tests; the installer validates both generated dispatch and sudoers on target.
Installer tests substitute host/filesystem/service boundaries; they are not Pi
activation or hardware evidence. The existing Starlette/httpx deprecation warning
remains unrelated to this change.

## Live evidence and delivery boundary

Existing key-based restricted SSH worked for inventory, status and
`diagnose-pair-gpio`: DietPi, checkout d0dfeac, three services active, paired GPIO
output/high, daemon SHA33088ea9 and original helper SHA555ea7cd. These establish
software/electronic state, not physical valve position or lamp isolation.

The allowlisted local delivery server returns the exact outer package over
HTTP at workstation192.168.111.30:8780; response bytes and SHA256 were verified
from the workstation. Directory listing returns404. No expiry timer is configured;
the workstation/server must stay running. The operator subsequently verified the v1 download and all member checksums on Pi.

The one-time root-console access installation and a second restricted SSH login
remain pending. No new access command or migration phase has been executed on
Pi. No relay activation, service restart, account/group/key change, release,
commit or push is claimed by this evidence record.

## Installer precheck diagnosis and v2 handoff

The v1 root-console attempt stopped at CONFIGURATION_CHECK_FAILED before backup
or installed-file mutation. Operator checks isolated visudo exit1; its output
identified /etc/sudoers.d/nodered with incorrect permissions (required0440).
The operator reported completing chmod0440 and revalidation; the actual final
visudo output was not supplied. The next installation must independently pass
all unchanged validation gates.

The v2 installer reports fixed check names and sanitized reason categories on
validation failure. This changes diagnostics only; it does not bypass sudoers,
SSH, baseline or isolation validation.

- Package: maintenance-access-20261014-v2.tar.gz.
- SHA256: 8e9dc4b74babc82d031779ffcdc7d4369e61af08a19c1e30336789da82de6a96.
- Nested migration unchanged; nine regular outer members, all manifest and
  SHA256SUMS entries checked, packaged Python byte-equal to current source.
- Full repository suite: 841 passed, one existing dependency warning. Ruff passed.
- Activation, second restricted login and migration remain pending.

## Access activated; migration not yet confirmed

Operator v2 receipt: BACKUP_COMPLETE=/root/freeze-maintenance-access.c8qk1m3v;
MAINTENANCE_ACCESS_INSTALLED; migration NOT_REQUESTED. A separate workstation SSH
connection verified original inventory and maintenance status (access_version1,
pinned package SHA). Both jobs reported NOT_REQUESTED. Original Hub/pair/Node-RED
services were active and artifact hashes matched the baseline. An unknown harmless
command and maintenance status with an extra argument were both rejected.

These observations satisfy the second-login/command-boundary activation gate.
The subsequent prepare SSH attempt timed out while connecting to port22, before
a remote command could be sent. A following read-only status connection also
timed out. No migration submission or completion is claimed; reconcile status
before another submission. Physical isolation remains the operator statement.

## Connection restored and prepare submitted

The operator reported fail2ban-client absent. No network cause was established.
TCP22 and TCP8081 later accepted workstation connections. Restricted status
confirmed both jobs still NOT_REQUESTED, then the exact prepare command returned
submitted=true. The next status showed prepare activating/start (PID7479),
PENDING_OR_INTERRUPTED, and all three original services active. A later status
connection timed out before SSH dispatch. Preparation completion must be
reconciled; do not repeat its one-shot request. Install has not been requested.

## Preparation verified by operator status

The operator ran the installed maintenance status at the existing root console.
It reports prepare verified=true, evidence /root/paired-gpio-migration.xj0q8tgi,
prepare service active/exited with exit0, and install NOT_REQUESTED. All original
services remain active; original artifact hashes are unchanged. The subsequent
workstation install attempt timed out connecting to SSH port22 before dispatch.
No installation submission is claimed. The existing root session is the fallback
for invoking the same fixed, approved install operation.

## Partial migration stopped at effective device allow check

A later direct restricted SSH status confirmed install was invoked and failed
at EFFECTIVE_DEVICE_ALLOW, evidence /root/paired-gpio-migration.xj0q8tgi.
Installed daemon SHAef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f
and dropin SHA8198c016d5688b0573f68908d3e4e7c0b8e36fcfa33cc6811963daac28f4bacd
are present. Hub and paired service are inactive; Node-RED remains active.
The maintenance wrapper service reports exited/0 but its job receipt explicitly
says verified=false/MIGRATION_FAILED; wrapper exit is not migration success.
No retry or rollback was attempted. Actual DeviceAllow output requested from
the existing root console; root cause is not yet established.

## Status diagnostic extension prepared after recovery stop

Owner objected to further manual log copying. The prepared status-only update
adds a fixed reader of the reviewed recovery directory: marker presence, allowed
error labels, exception type, approved source basenames/line numbers and fixed
subprocess error categories. No raw trace, source text, arbitrary paths or
exception messages are exported. Commands, permissions and migration requests
are unchanged: AST comparison with the original packaged helper proves all
other statements unchanged after removing the new reader and its result key.

Full suite869 passed (one existing warning); Ruff and diff whitespace passed.
Tests cover redaction, exact update baseline rejection, backup and status-only
readback. Console updater atomically replaces only the root-owned helper after
verifying its original hash and the new package, retaining a private backup.
It does not alter sudoers, SSH, approval, services, GPIO or failed job records.

Package: maintenance-diagnostics-20261014-v1.tar.gz
SHA256: ee0386a41f6a67ab59ea597ded19e3061df11c5005add0d18fab43df8a293822
New helper SHA256: 07eae1c9181f3910cd50e1873f278355c5c0941c450778b5afab1b9b05c4d77c
Target update and new remote diagnostic remain pending.

## Current access and recovery checkpoint

Both diagnostics updates were subsequently installed through the root console.
Fresh restricted SSH status exposes the original recovery failure and the new
hub_recovery success marker. The latter is true with FAILED=false; Hub, pair and
Node-RED are active. A separate original status command verifies GPIO26/20 high.
The final helper candidate SHA is df06b46bd206dbadbbbd201aeb80529df9deb790b7df448b29e1ff2ba15c6a9c.
The root updater pins the earlier helper and verifies replacement; direct remote
helper-hash readback is not part of the status API. Permission forms remain the
same seven exact commands. Prepare/install claims are consumed; do not resubmit.
See [recovery acceptance](2026-10-14-device-allow-recovery.md#target-recovery-verified-over-restricted-ssh).
