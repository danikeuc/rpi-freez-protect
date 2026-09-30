# Local Codex commissioning prompt

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
