# Local Codex commissioning prompt

Copy the following prompt into a local Codex session started from the
workstation clone of this repository.

```text
Commission this Freeze Protect installation from this workstation. Use only
the dedicated non-root freezeprotect-commission account over the Pi private
LAN; freezeprotect is a non-login service identity. Do not use root SSH,
public SSH exposure, credentials, or tokens.

For read-only Pi checks, use the non-interactive form:

ssh -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission inventory
ssh -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission usb
ssh -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission status

The only allowed privileged helper subcommands are `inventory`, `usb`,
`status`, and `drain`. Their only runnable forms are:

sudo -n /usr/local/sbin/freeze-protect-commission inventory
sudo -n /usr/local/sbin/freeze-protect-commission usb
sudo -n /usr/local/sbin/freeze-protect-commission status
sudo -n /usr/local/sbin/freeze-protect-commission drain

Do not run arbitrary sudo commands.
Deployment, service restarts, legacy-flow export/disable, and deployed-flow
preflight are trusted-local-console tasks outside this allowlist. Require the
mandatory cutover and startup output/high gates in WORKSTATION_CODEX_COMMISSIONING.md
before acceptance; stop on any failed receipt or readback.

Keep the 24 V valve supply disconnected. Do not run SUPPLY. Stop and ask Danijel
for explicit approval in the current conversation before beginning the 24 V
stage or any physical valve test.

Before uploading firmware, discover USB serial devices through
/dev/serial/by-id. Continue only when exactly one device is found. Stop for
zero devices or more than one device; do not guess a serial path. With the
single discovered device recorded as serial_device, run
pio run --target upload --upload-port "$serial_device"
and collect boot output with
pio device monitor --baud 115200 --port "$serial_device"
Use that sole discovered path for both commands; do not allow automatic port
selection. Use the workstation or Pi USB-location
branch documented in WORKSTATION_CODEX_COMMISSIONING.md. The Pi USB branch is
trusted-local-console-only; do not read or provision `secrets.h` over SSH.
```
