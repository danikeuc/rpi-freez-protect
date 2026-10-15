# Limited maintenance access v1

## Current target checkpoint - 2026-10-14

Paired migration completed through the separate reviewed Hub-readiness recovery.
Fresh restricted SSH verified its success marker, active services, candidate
hashes and paired output/high readback. Original failed attempts remain recorded;
do not rerun their one-shot commands. Lighting/physical acceptance remains pending.
See [target evidence](../../docs/evidence/2026-10-14-device-allow-recovery.md). Earlier candidate and pending-activation
statements below describe the preceding preparation/installation stages.


Status: implementation candidate, 2026-10-14. Operator installation and an
independent second SSH login are required before any live capability is claimed.
The owner asked Codex to take over the documented maintenance setup. This is a
narrow initial implementation: diagnostics and the already prepared, exact paired
GPIO migration. It is not a general package manager or a generic service restart
endpoint. Later packages require a separate reviewed extension.

## Authority and scope

The original four commissioning commands stay unchanged. The installer extends
the existing forced-command dispatcher with exactly these three commands:

```text
sudo -n /usr/local/sbin/freeze-protect-maintenance status
sudo -n /usr/local/sbin/freeze-protect-maintenance prepare
sudo -n /usr/local/sbin/freeze-protect-maintenance install
```

`status` reads fixed service properties, fixed artifact hashes and sanitized job
receipts. It never prints environment values, unrestricted logs, or exception
payloads. Recognized migration error labels may be exported from private failure
evidence; other failures remain PRIVATE_REVIEW_REQUIRED. Thus not every failure
can be resolved remotely.

`prepare` and `install` each submit one fixed systemd job, once per installation.
They accept no paths, arguments, URLs, stdin scripts or service names. The job uses
only the root-owned migration archive with SHA256
`f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513`.
All fourteen unpacked members must match that archive on every request and run.
The unchanged archive has historical local-console wording; this reviewed wrapper
is the sole scoped delegation for that exact archive. Its guards are preserved.
See [migration operations](../../docs/operations/paired-gpio-migration.md).

An operator starts `install_access.py --loads-disconnected` on the actual Pi from
a root-owned verified package. This confirms both valve 24 V and lamp mains stay
disconnected for this maintenance window. It records approval for this boot and
at most eight hours; status remains available after expiry. The mutating window
cannot be renewed remotely. Installation requires the original helper, dispatcher
and sudoers to match the bundled baseline byte-for-byte; an already present or
partial installation stops for assessment.

The access installer backs up existing files privately, stages the helper and
pinned migration, validates sudoers and changes the dispatcher last. It does not
change SSH configuration, keys, accounts, groups, GPIO, Node-RED flows or service
state. It does not start a migration. The base helper and its original sudoers
remain byte-for-byte unchanged. No SSH reload is required because new connections
invoke the same dispatcher path.

## Runtime and evidence

Installed code/package: `/usr/local/lib/freeze-protect-maintenance-v1` (root0700).
State: `/var/lib/freeze-protect-maintenance` (root0700). Entry point:
`/usr/local/sbin/freeze-protect-maintenance`. Grant:
`/etc/sudoers.d/freeze-protect-maintenance`.

Submission writes and fsyncs a one-shot request before starting the transient
service. Workers run independently of the SSH connection with Restart=no.
Services are not enabled at boot. A worker waits for the submitting process to
release the operation lock, then rechecks approval and package identity. Install
requires a verified prepare receipt; the existing migration independently rechecks
its boot/baseline/settings identity and all physical-isolation software gates.

A submitted response is not success. Use `status` to inspect job `verified` and
the corresponding receipt. PENDING_OR_INTERRUPTED means no final receipt exists;
inspect the fixed job service status and never resubmit blindly. Failed attempts
are consumed; no automatic rollback, restart or retry occurs. The reviewed
migration retains its own backup and failure cleanup. Private logs and database
backups must remain on the Pi.

## Activation acceptance

Keep the operator's administrative recovery session open. From a separate
workstation connection, use the existing dedicated key and strict host-key
checking to verify original `inventory` and the new `status` command. Confirm
that an unrecognized harmless command and a status command with extra arguments
are rejected. These negative tests must not contain any actuator action.
Record the installed dispatcher/helper identities and the receipt before use.
No request for `prepare` or `install` should be sent merely as a connectivity test.

After activation, Codex can run the separately authorized prepare, inspect the
receipt, then run the separately authorized install. Both loads stay disconnected.
Lamp activation, SUPPLY, firmware upload and physical acceptance are outside this
access change. The migration uses only its existing named service sequence.

## Local recovery

The installer prints `/root/freeze-maintenance-access.<id>`. That directory contains
`backup.json`, the exact previous dispatcher/helper/sudoers bytes and metadata,
private effective SSH settings, and INSTALLED.json or STOPPED when available.
A crash may leave neither final marker. Inspect actual files and job status.

If restoring access is necessary, first ensure no maintenance job is running and
preserve all migration evidence. At the trusted console, verify backup hashes,
restore only the previous dispatcher bytes and mode from `backup.json`, and
validate shell syntax. Then remove the **new** maintenance sudoers file after
verifying its identity and run visudo validation. Do not replace the original
commissioning sudoers or keys, delete service data, or undo the GPIO migration as
part of SSH-access recovery. Preserve staged code/state for diagnosis until all
jobs have ended. Prove a second original restricted login before closing recovery.
No automated rollback command is supplied because partial migration recovery must
be assessed separately from access-file recovery.

## Failure boundaries

| Failure | Required handling | Evidence limit |
| --- | --- | --- |
| SSH/network loss | Worker continues under systemd; reconcile durable result with status | No receipt means unknown, not success |
| Worker crash/hang | No automatic retry; retain claim and inspect private state | The wrapper provides no independent physical cutoff |
| Pi reboot | Transient work does not resume; boot-bound approval is invalid | Existing paired startup and hardware behavior remain separate |
| Power loss/restoration | Preserve evidence where durable; do not replay jobs | Physical relay/valve safety is not proven by this wrapper |

Legal energized valve1/valve2/light combinations remain (0,0,0), (0,0,1),
(1,1,0), (1,1,1). This migration envelope leaves lighting disabled and requires
DRAIN high/high at its acceptance gates. No physical position is inferred.

## GPIO21 diagnostic update activated — 2026-10-15

The reviewed status-only extension was installed by the operator and verified
through a separate restricted SSH connection; additional arguments were rejected. It adds sanitized historical bench evidence to the existing exact
maintenance status command. No new SSH command, path argument, permission, device
access, service restart or actuation is introduced. Do not invoke prepare/install
for this update. The new field is available through the existing status command. The separate
root-console updater is already applied; do not rerun it.

[Operator instructions](LIGHT_BENCH_DIAGNOSTICS.md).
