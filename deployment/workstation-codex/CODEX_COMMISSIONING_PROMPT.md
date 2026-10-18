# Local Codex commissioning prompt

## Activation checkpoint - 2026-10-14

Limited maintenance access v1 was installed from package v2 and independently
verified through a second SSH connection, including rejected command forms.
The original four commands and exactly three maintenance forms are now allowed
for the pinned migration; no general shell or sudo access is granted.
[Activation evidence](../../docs/evidence/2026-10-14-maintenance-access.md)
records the backup, temporary connection failures and subsequent successful
Hub-readiness recovery. Original failed migration receipts remain historical.
Earlier pending-activation wording below describes the pre-installation stage.


Copy the following prompt into a local Codex session started from the
workstation clone of this repository.

```text
Commission this Freeze Protect installation from this workstation. Use only
the dedicated non-root freezeprotect-commission account over the Pi private
LAN; freezeprotect is a non-login service identity. Do not use root SSH,
public SSH exposure, credentials, or tokens.

A first-contact `The authenticity of host ... can't be established` prompt is
not an authentication failure. Do not retry it as a password/key problem and
stop before accepting the key. Do not use `StrictHostKeyChecking=no` or
`accept-new`. At the trusted local console, ask the operator to run
`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256` and compare the
complete ED25519 fingerprint. Only after an exact match may the operator
establish trust interactively. A changed-host-key event is a separate incident;
do not remove a `known_hosts` entry without the same out-of-band verification.

For read-only Pi checks, use these non-interactive PowerShell forms with the
dedicated identity named explicitly:

ssh -i "$env:USERPROFILE\.ssh\freezeprotect_commission" -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission inventory
ssh -i "$env:USERPROFILE\.ssh\freezeprotect_commission" -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission status
ssh -i "$env:USERPROFILE\.ssh\freezeprotect_commission" -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission diagnose-pair-gpio

The only allowed privileged helper subcommands are `inventory`, `status`,
`diagnose-pair-gpio`, and `drain`. Their only runnable forms are:

sudo -n /usr/local/sbin/freeze-protect-commission inventory
sudo -n /usr/local/sbin/freeze-protect-commission status
sudo -n /usr/local/sbin/freeze-protect-commission diagnose-pair-gpio
sudo -n /usr/local/sbin/freeze-protect-commission drain

`diagnose-pair-gpio` is read-only, accepts no additional arguments, and is
fixed to the paired-GPIO service and three installed artifact paths. It omits
journal messages rather than risk returning secrets. It does not authorize a
restart, service mutation, GPIO command, shell, or arbitrary systemd query.

The SSH account is command-only: an interactive shell, a local Node-RED call,
port forwarding, extra arguments, and arbitrary sudo commands are rejected.
Deployment, service restarts, legacy-flow export/disable, and deployed-flow
preflight are trusted-local-console tasks outside this allowlist. Require the
mandatory cutover and startup output/high gates in WORKSTATION_CODEX_COMMISSIONING.md
before acceptance; stop on any failed receipt or readback.

A limited maintenance implementation is now prepared under
deployment/maintenance-access/README.md, following the owner's later setup
request. Do not assume it is installed. After the exact installation receipt and
second restricted login are verified, its sole additional privileged commands
are these exact forms (with the same dedicated SSH identity and private LAN):

sudo -n /usr/local/sbin/freeze-protect-maintenance status
sudo -n /usr/local/sbin/freeze-protect-maintenance prepare
sudo -n /usr/local/sbin/freeze-protect-maintenance install

These commands never accept paths, package URLs or service arguments. Prepare
and install submit single-use jobs for the pinned paired-GPIO migration only;
submission is not completion. Read status and durable receipts before advancing.
Keep both valve 24 V and lamp mains disconnected for that maintenance window.
This does not add shell access, generic restart, firmware or live-load testing.

Keep the 24 V valve supply disconnected. Do not run SUPPLY. Stop and ask Danijel
for explicit approval in the current conversation before beginning the 24 V
stage or any physical valve test.

The active display is the Waveshare dial from the separate `roon-knob`
repository; the CrowPanel is retired. Follow `deployment/DISPLAY_COMMISSIONING.md`
for exact revision evidence, credential rotation and the Roon/valve acceptance
boundary. Build, flash and provision only from the reviewed workstation clone
of `roon-knob`; never add firmware or USB commands to the Pi helper. Do not flash
merely to diagnose connectivity, and never put the display token in a Codex
prompt, terminal capture, serial log or Git. The disconnected GPIO acceptance
still requires explicit current-conversation approval before any timed action.
```

## GPIO21 diagnostic update activated — 2026-10-15

The reviewed status-only extension was installed by the operator and verified
through a separate restricted SSH connection; additional arguments were rejected. It adds sanitized historical bench evidence to the existing exact
maintenance status command. No new SSH command, path argument, permission, device
access, service restart or actuation is introduced. Do not invoke prepare/install
for this update. The new field is available through the existing status command. The separate
root-console updater is already applied; do not rerun it.

[Operator instructions](../maintenance-access/LIGHT_BENCH_DIAGNOSTICS.md).

## Controller diagnostics extension prepared — 2026-10-18

At the owner's request to remove repeated diagnostic copy/paste, a bounded
status-only extension is prepared in
[controller diagnostics](../maintenance-access/CONTROLLER_DIAGNOSTICS.md).
After verified root-console installation and a second restricted SSH check,
the existing maintenance `status` command may return the fixed controller
status/history fields and categorized journal described there. No new command
form, arbitrary shell/sudo, installation, restart or actuator authority is added.
Activation remains pending; preparation alone does not change Pi permissions.

## Activation verified — 2026-10-18

Owner reported installation complete. Two separate restricted SSH status requests
succeeded and returned diagnostic_version1 and the exact candidate helper hash
dd390a553688b1dc208d2f871e5b3fd17d7cf5ef8cff272f23ac055bc0691a92.
The form `status extra` was independently rejected by the forced dispatcher.
Controller diagnostics are now available through the existing status command.
No shell, generic deployment/restart or actuator authority was added.
This supersedes pending-activation wording in the preparation record.
