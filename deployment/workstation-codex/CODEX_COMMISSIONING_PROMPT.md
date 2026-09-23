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

The only allowed privileged helper subcommands are `inventory`, `status`, and
`drain`. Their only runnable forms are:

sudo -n /usr/local/sbin/freeze-protect-commission inventory
sudo -n /usr/local/sbin/freeze-protect-commission status
sudo -n /usr/local/sbin/freeze-protect-commission drain

The SSH account is command-only: an interactive shell, a local Node-RED call,
port forwarding, extra arguments, and arbitrary sudo commands are rejected.
Deployment, service restarts, legacy-flow export/disable, and deployed-flow
preflight are trusted-local-console tasks outside this allowlist. Require the
mandatory cutover and startup output/high gates in WORKSTATION_CODEX_COMMISSIONING.md
before acceptance; stop on any failed receipt or readback.

Keep the 24 V valve supply disconnected. Do not run SUPPLY. Stop and ask Danijel
for explicit approval in the current conversation before beginning the 24 V
stage or any physical valve test.

The CrowPanel USB cable for this installation is on the Windows workstation.
The operator-confirmed port is COM6. A COM number is not stable device identity:
compare `pio device list --serial --json-output` with the panel disconnected
and reconnected, record the newly appeared exact `hwid`, and require both that
`hwid` and COM6 before proceeding. Set `$CrowPanelPort = 'COM6'` and use that
exact variable for both
`pio run -e crowpanel --target upload --upload-port $CrowPanelPort` and
`pio device monitor --baud 115200 --port $CrowPanelPort`. Never ask the Pi
helper to inventory workstation USB and never allow automatic port selection.
Do not reflash merely to diagnose connectivity: when firmware sources have not
changed, prefer serial observation and preserve the installed image. After the
monitor opens, tap **RESET** once without holding **BOOT** and require a fresh
`Freeze Protect CrowPanel boot` line. If the cable is ever moved to the Pi,
that documented branch is trusted-local-console only; do not read or provision
`secrets.h` over SSH.
```
