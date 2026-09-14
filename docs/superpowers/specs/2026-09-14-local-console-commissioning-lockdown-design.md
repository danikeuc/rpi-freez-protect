# Superseded: local-console commissioning lockdown design

> Superseded on 2026-09-14 by the verified OpenSSH two-session handover in
> [`2026-09-14-openssh-two-session-commissioning-design.md`](2026-09-14-openssh-two-session-commissioning-design.md).
> DietPi now runs OpenSSH on port 22; preserve an existing root SSH session as
> recovery while bootstrap quarantines and replaces only commissioning access.

# Historical local-console commissioning lockdown design

## Goal

Make a commissioning upgrade fail closed without relying on a best-effort
attempt to stop an already compromised or independently supervised SSH daemon.
The dedicated `freezeprotect-commission` account remains command-only and
private-LAN-only after successful commissioning; `freezeprotect` remains a
non-login service identity.

## Security boundary

The old commissioning key is an external capability. A bootstrap script cannot
prove that it has disabled every possible SSH listener while that capability is
still reachable. The upgrade therefore has two explicitly separated phases:

1. A trusted local Pi-console operator disconnects Pi network access (or blocks
   TCP/22 at the local network boundary) and runs a root-only local preflight.
2. Only after that preflight has installed, reloaded, and attested the
   `DenyUsers` quarantine may the normal bootstrap prepare restricted remote
   commissioning access.

The local console is an HDMI keyboard/display or directly attached serial
console. A `/dev/pts/*` terminal is rejected so the preflight cannot be run
over SSH. The physical/network isolation remains in place until the preflight
reports success. No GPIO, relay, valve, firmware, secret, or 24 V action is
part of either phase.

## Components

### `prepare-freezeprotect-commissioning-local.sh`

This new root-run script is the only component allowed to establish upgrade
quarantine. It consumes a reviewed root-owned repository checkout and the
root-owned `60-freezeprotect-commission-quarantine.conf` asset. It must:

- require an actual local console TTY and root execution;
- validate the policy source, its ancestor directories, `/etc/ssh`, and the
  target as root-controlled and non-symlinked;
- install the `DenyUsers freezeprotect freezeprotect-commission` policy,
  validate it with `sshd -t`/`sshd -T`, and reload a supported active service
  (`ssh.service` or `sshd.service`);
- revoke `/etc/sudoers.d/freeze-protect-commission`, terminate every existing
  commissioning-account process, and remove the account's old
  `authorized_keys` only after proving its home and `.ssh` hierarchy safe to
  modify;
- fail with the quarantine still in place if any cleanup or validation is
  incomplete; and
- write `/var/lib/freeze-protect-commissioning/local-lockdown-v1` as a
  root-owned `0600` attestation only after the policy is active and legacy
  grants are gone.

The preflight never installs a new key, sudo rule, final SSH policy, service,
or any hardware-facing asset. If it fails, recovery is local-console-only and
the operator must not reconnect the network as a commissioning route.

### `bootstrap-freezeprotect-access.sh`

Bootstrap becomes phase two. Before it reads any writable checkout asset,
validates a public key, changes an account, or grants access, it requires all
of the following:

- the root-owned, mode `0600` local-lockdown attestation;
- the active quarantine file with the expected root-owned content; and
- effective `sshd -T` output containing the quarantine `DenyUsers` rule.

If any condition is missing, bootstrap exits without touching SSH, sudoers,
keys, accounts, or deployment files. It keeps the quarantine file active while
it validates all remaining assets, account state, user services, cron, and
`at` jobs.

Bootstrap installs the final restricted policy as a separate root-owned
candidate while quarantine remains active. It validates the candidate with
`sshd -t` and `sshd -T`; it then atomically disables the quarantine file and
reloads SSH. An unsuccessful reload leaves the running quarantined daemon in
place. Because the local preflight has already removed the old key and sudo
rule, a later daemon restart under the validated final policy has no legacy
credential to accept.

New sudoers and key material are installed only after all mutable account/path
validation is complete. The successful final state is recorded only after
their known-safe installation finishes. A failure before that point revokes
the new sudoers file and removes the new key only through the already validated
root-owned hierarchy; it does not try to prove network isolation.

## Failure and recovery contract

- **Preflight unavailable or fails:** network isolation stays in place; no
  workstation SSH action is allowed. Correct the reported condition from the
  local console and repeat preflight.
- **Bootstrap attestation check fails:** no state changes occur. Run the local
  preflight; do not bypass it by reusing an old SSH key.
- **Bootstrap cleanup fails while quarantined:** quarantine remains enabled;
  no new key/sudo grant is installed. Correct it locally and rerun phase two.
- **Final SSH reload fails:** the old running configuration remains quarantine;
  no new key/sudo grant is installed. Correct it locally and rerun phase two.
- **A post-grant validation fails:** remove the new root-owned key and sudoers
  file, restore the quarantine policy, reload SSH, and stop. Recovery remains
  local-console-only.

## Test strategy

Integration tests use extracted production shell functions and controlled
command stand-ins. They must prove:

- a `/dev/pts/*` invocation is rejected and no preflight attestation is made;
- an unvalidated policy, source path, target symlink, or reload failure cannot
  create an attestation;
- the local preflight activates quarantine before it removes legacy sudo, key,
  and processes;
- bootstrap refuses missing, unsafe, or ineffective attestation/quarantine
  before every other mutable operation;
- the quarantine remains active until all user/deferred-state and final-policy
  validation completes; and
- a final-policy or new-grant failure restores quarantine and removes any new
  root-owned grant.

The full Python suite, Ruff, shell syntax checks, `visudo`, and diff checks are
required before every commit. A fresh independent security review is required
before the PR branch is updated, followed by GitHub Codex review of that exact
remote head.

## Acceptance criteria

- The normal bootstrap refuses to run without a successful local-console
  attestation and active effective quarantine.
- No retained legacy key or sudo rule can be used after a successful preflight.
- An unsuccessful bootstrap leaves remote commissioning denied, without
  depending on `pkill`, a runtime-only systemd mask, or assumptions about a
  daemon supervisor.
- The workstation account can execute only the existing exact helper allowlist
  after successful commissioning.
- No Raspberry Pi, GPIO, ESP32, valve, or 24 V operation is performed while
  implementing or reviewing this design.
