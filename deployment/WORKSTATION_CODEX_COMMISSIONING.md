# Workstation Codex commissioning

This guide defines the workstation-led commissioning route. Use only the
dedicated `freezeprotect-commission` account for remote access.
`freezeprotect` remains the non-login service identity; it owns the Hub's
state and environment and must never be used for SSH. Do not configure an
automation runner or use a privileged remote login. The 24 V valve supply
remains disconnected until Danijel explicitly approves the physical test in
the current session. Keep Pi SSH private-LAN-only; do not expose it publicly.
The bootstrap allows the commissioning account only from the trusted
workstation LAN `192.168.111.0/24` and Pi LAN `192.168.114.0/24`;
do not add a router port-forward for TCP 22.

## 1. Windows workstation prerequisites

Install Codex CLI, Git, OpenSSH client and PlatformIO Core on the Windows
workstation. This deployment's DietPi host is `192.168.114.192` on the private
LAN. Do not expose port 22 through the router.

The following procedure requires the OpenSSH service already verified on port
22. First try the normal connection without changing `known_hosts`:

```powershell
ssh root@192.168.114.192
```

On first contact, `The authenticity of host ... can't be established` is a
trust gate, not an authentication failure. Do not use `StrictHostKeyChecking=no`
or `accept-new`. At the trusted local console, obtain the Pi's ED25519 host-key
fingerprint:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Compare the complete fingerprint with the PowerShell prompt. Only after an
exact match may the operator accept it interactively. Record the verified
fingerprint in the commissioning evidence without copying any private key.

Only after a changed-host-key error, compare the replacement fingerprint
through a trusted existing session or trusted local console. Do not accept the
replacement key merely because SSH prompted for it. After the fingerprint
matches, run this in PowerShell and reconnect:

```powershell
ssh-keygen -R 192.168.114.192
ssh root@192.168.114.192
```

Keep this root SSH session open throughout the bootstrap. It is the recovery
session; do not stop, restart, mask, or close it while a new commissioning key
is being tested.

## 2. Pi bootstrap over OpenSSH

From the root SSH session on the Windows workstation (or a local console if
available), first create and preserve the non-login
`freezeprotect` service account from
[`COMMISSIONING.md` step 1](COMMISSIONING.md#1-make-the-pi-service-files).
It has home `/var/lib/rpi-freeze-protect` and an `nologin` shell. Bootstrap
refuses to convert or migrate it: that account owns service state and receives
the Hub's environment tokens.

Before bootstrap, ensure the DietPi `nodered` account and paired-GPIO service
prerequisites from [`COMMISSIONING.md` step 2](COMMISSIONING.md#2-bind-node-red-to-loopback-then-add-the-bridge)
exist. Bootstrap fails closed if it cannot validate `nodered`, because the
commissioning identity must be proven distinct from the actuator identity.

Bootstrap creates a separate `freezeprotect-commission` login with home
`/home/freezeprotect-commission`, non-interactive POSIX shell `/bin/sh`, and
only its own dedicated primary group. Its numeric UID and GID must differ from both `freezeprotect`
and `nodered`; it never receives `gpio`, `dialout`, `nodered`, service-data
ownership, service environment files, or a service unit. If either existing
account does not match that profile, bootstrap removes the standard legacy
commissioning grants and does not restore commissioning access. The
administrator's root OpenSSH session remains available. Remediate the reported
account state as root; do not delete service data.

Copy a reviewed, trusted repository revision to `/opt/rpi-freez-protect`.
Keep deployment assets and service execution paths root-owned and not writable
by `freezeprotect`; never recursively hand over the entire checkout. Bootstrap
copies the standard-library-only GPIO client to the root-owned
`/usr/local/lib/freeze-protect-commission/paired_gpio_client.py`, invoked by
`/usr/bin/python3 -I`, not from the checkout. Its directory, the outer helper,
and their ancestors must remain root-controlled and non-user-writable.
Updates to either installed artifact are root-controlled deployment work only.

Bootstrap makes the commissioning home root-owned `0750`, `.ssh` root-owned
`0710`, and `authorized_keys` root-owned `0640`, using the commissioning
account's primary group. It installs a key-only `sshd` policy for this user,
disables password/interactive authentication, forwarding and TTYs, and forces
every SSH request through a root-owned dispatcher. The dispatcher allows only
the four documented helper commands; it never opens a remote shell or permits
access to local-only Node-RED. On an upgrade bootstrap first verifies the
root-controlled legacy grant paths and removes their old key and sudo grant.
It then validates the commissioning identity before signalling its UID and
terminates its processes. A temporary `DenyUsers` quarantine follows, then
cleanup and recheck of user-service/cron/at state, then activation of the
final restricted policy. This prevents a failed cleanup or policy validation
from leaving an old key or deferred user service usable.

DietPi must provide `crontab`, `atq`, `atrm`, and `awk` for this cleanup and
recheck; bootstrap treats any missing or unreadable deferred-job tooling as
unsafe and does not restore commissioning access. If a later validation fails,
the commissioning key and sudo grant remain absent; once quarantine is
active, it remains in force. The root SSH recovery session stays available.

Keep firmware/build work separate: the workstation clone is writable. The
commissioning account must never read `include/secrets.h` or run a Pi-side
firmware build because the display token is able to request a timed shower.
If the USB cable is physically attached to the Pi, the upload is a
trusted-local-console-only task described below. Do not make the home,
deployment scripts, service virtual environment, or privileged execution paths
writable to enable builds.

In a second PowerShell window, create a dedicated commissioning key once and
copy only its public half to the root-controlled Pi path:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\freezeprotect_commission" -C "freezeprotect-commission"
scp "$env:USERPROFILE\.ssh\freezeprotect_commission.pub" root@192.168.114.192:/root/.ssh/freezeprotect-commission-workstation.pub
ssh root@192.168.114.192 'chown root:root /root/.ssh/freezeprotect-commission-workstation.pub && chmod 0600 /root/.ssh/freezeprotect-commission-workstation.pub'
```

Return to the still-open root SSH session and run this one command. The public
key must be a root-owned regular file in `/root/.ssh`; do not use `/tmp` or a
symlink.

```bash
/opt/rpi-freez-protect/deployment/workstation-codex/bootstrap-freezeprotect-access.sh \
  /root/.ssh/freezeprotect-commission-workstation.pub
```

Without closing the root SSH session, use the second PowerShell window to
verify the restricted account and helper over the private LAN:

```powershell
ssh -i "$env:USERPROFILE\.ssh\freezeprotect_commission" -o BatchMode=yes freezeprotect-commission@192.168.114.192 sudo -n /usr/local/sbin/freeze-protect-commission inventory
```

Only after that succeeds should later hardening of root SSH access be planned
as a separate change. Keep the root session available for the remaining
software-only preflight, and remove the temporary public-key file from
`/root/.ssh` only after the restricted account has been rechecked.

## 3. Local Codex handoff

The preferred controller is Codex in the ChatGPT desktop app on the Windows
workstation. Sign in to the same ChatGPT account and workspace, select Codex,
choose `This computer`, and open the workstation clone's repository root. Do
not connect the app directly to the Pi. Do not install Codex on the Pi. The
local Codex process uses the workstation's Git checkout, OpenSSH client, and
commissioning key; the Pi continues to expose only the restricted
`freezeprotect-commission` command boundary.

Codex automatically loads the repository-root [`AGENTS.md`](../AGENTS.md) at
the start of a new run. It directs Codex to this guide and the focused
[`workstation-codex/CODEX_COMMISSIONING_PROMPT.md`](workstation-codex/CODEX_COMMISSIONING_PROMPT.md),
so copying the prompt into every session is no longer required. Restart the
Codex session after changing instruction files because instruction discovery
occurs at session start.

The standalone Codex CLI remains a supported fallback. Start it from the
repository root, then verify instruction discovery before any network action:

```powershell
Set-Location 'C:\Users\danik\Projects\rpi-freez-protect'
codex --ask-for-approval never "Summarize the active repository instructions; do not access the network or Pi."
```

The summary must include the 24 V stop gate, prohibition on SUPPLY, dedicated
commissioning identity, first-contact host-key verification, and prohibition
on installing Codex on the Pi. If any item is absent, stop and restart Codex
from the repository root rather than proceeding with partial instructions.

## 4. Staged acceptance

### Mandatory deployment and cutover prerequisites

Keep the 24 V valve supply disconnected. The trusted-console operator performs
the service installation/restarts, environment configuration, Node-RED edits,
and deployment preflight from
[`COMMISSIONING.md` steps 1–4](COMMISSIONING.md#1-make-the-pi-service-files).
Those actions are outside the remote account's four-command sudo allowlist;
local Codex must hand them off, not widen the allowlist or use arbitrary sudo.
Do not copy secrets into the Codex session or its logs.

Before acceptance or any timed-shower request, record all these gates:

1. Export the legacy relay flow to a rollback file outside the active flow set.
   Disable its tab containing individual GPIO 26/20 outputs and old `/trigger`
   routes before deploying the constrained paired bridge. Do not run both flows.
2. At the trusted console, run the mandatory
   [deployed-flow preflight in step 2](COMMISSIONING.md#2-bind-node-red-to-loopback-then-add-the-bridge)
   against `/mnt/dietpi_userdata/node-red/flows.json`, not just repository JSON.
   Require `Preflight passed` and exit zero: enabled legacy GPIO 26/20 or
   `/trigger` paths, and missing/duplicate bridge routes block cutover.
3. Verify `node-red.service`, the paired GPIO daemon and Hub are active; Node-RED
   is loopback-only and the old `nodered.service` is not active. Confirm startup
   `DRAIN` and BCM 26 and 20 each report output/high (`op` and `hi`) after restart.
   The Hub starts in `FROST_PROTECTION` / `sensor_pending`; the bridge must no
   longer be in its unverified startup/503 state. No flashing or physical test
   is a substitute for these startup checks.

Stop on any failed preflight, service result, receipt, or GPIO readback. Keep
24 V disconnected and the requested state at `DRAIN`; a failed readback is not
proof that physical DRAIN was achieved. Have the trusted-console operator
investigate before continuing; do not retry `SUPPLY` or enable legacy routes.

Run these fixed Pi-helper checks in this exact order:

```bash
ssh -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission inventory
ssh -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission usb
ssh -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission status
ssh -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission drain
```

The `usb` output is an inventory, not permission to select a device. Before
any upload, serial discovery must return exactly one `/dev/serial/by-id`
device. Stop for zero matching devices or for more than one matching device;
do not guess a serial path.

### USB cable on the workstation

Before upload, create `include/secrets.h` locally from
[`CROWPANEL_COMMISSIONING.md` step 1](CROWPANEL_COMMISSIONING.md#1-prepare-the-build-workstation).
Enter Wi-Fi and display-token values only in that ignored local file; never put
them in this guide, a Codex prompt, terminal capture, or Git.

From `firmware/crowpanel`, discover and capture exactly one serial-by-id device.
`serial_device` below is the only permitted upload/monitor path.

```bash
if [ ! -e include/secrets.h ]; then
  cp include/secrets.example.h include/secrets.h
fi
serial_device=$(find /dev/serial/by-id -maxdepth 1 -type l -print)
serial_count=$(printf '%s\n' "$serial_device" | sed '/^$/d' | wc -l)
[ "$serial_count" -eq 1 ] || { echo "expected exactly one serial device" >&2; exit 1; }
printf '%s\n' "$serial_device"
pio run --target upload --upload-port "$serial_device"
pio device monitor --baud 115200 --port "$serial_device"
```

Collect the boot output from the monitor. Stop rather than use either `pio`
command if discovery returned zero or more than one device.

### USB cable on the Pi — trusted-console-only

The `freezeprotect-commission` SSH account must never read the display token
or run a Pi-side firmware build. If the CrowPanel USB cable is attached to the
Pi, a trusted local-console operator performs this step with the 24 V valve
supply still disconnected. The root-owned secret stays local to that console:

```bash
sudo apt install -y python3-venv
sudo python3 -m venv /opt/freezeprotect-local-flash-tools
sudo /opt/freezeprotect-local-flash-tools/bin/pip install --upgrade pip platformio
if [ ! -e /opt/rpi-freez-protect/firmware/crowpanel/include/secrets.h ]; then
  sudo install -o root -g root -m 0600 \
    /opt/rpi-freez-protect/firmware/crowpanel/include/secrets.example.h \
    /opt/rpi-freez-protect/firmware/crowpanel/include/secrets.h
fi
sudoedit /opt/rpi-freez-protect/firmware/crowpanel/include/secrets.h
sudo /bin/sh -c '
set -eu
cd /opt/rpi-freez-protect/firmware/crowpanel
umask 077
rm -rf .pio
serial_device=$(find /dev/serial/by-id -maxdepth 1 -type l -print)
serial_count=$(printf "%s\\n" "$serial_device" | sed "/^$/d" | wc -l)
[ "$serial_count" -eq 1 ] || { echo "expected exactly one serial device" >&2; exit 1; }
/opt/freezeprotect-local-flash-tools/bin/pio run --target upload --upload-port "$serial_device"
chown -R root:root .pio
chmod -R go-rwx .pio
unsafe_artifact=$(find .pio \( ! -user root -o -perm /077 \) -print -quit)
[ -z "$unsafe_artifact" ] || { echo "unsafe firmware artifact: $unsafe_artifact" >&2; exit 1; }
exec /opt/freezeprotect-local-flash-tools/bin/pio device monitor --baud 115200 --port "$serial_device"
'
```

Edit `secrets.h` only with the Wi-Fi credentials, `http://<Pi-LAN-IP>:8081`,
and display token. Do not place these values in SSH commands, terminal logs,
or Git. The local-console operator collects the boot output directly.

Collect the boot output from the monitor.

After a successful upload and boot capture, require `drain` to exit zero with
one successful JSON DRAIN receipt (`ok` boolean true) and both BCM 26 and 20
output/high (`op` and `hi`). Then follow the
[disconnected display test](CROWPANEL_COMMISSIONING.md#4-functional-test-with-valve-power-disconnected):
an authenticated timed-shower request must move both GPIOs low together and
immediate drain must restore both output/high. Do not run `SUPPLY` directly.
Stop on any failed receipt/readback; leave 24 V disconnected and do not proceed
to a physical test. This disconnected test does not approve connecting power.

Keep the 24 V valve supply disconnected through every stage before the final,
explicitly approved test.

### Final physical test — blocked until explicit current-session approval

Stop and ask Danijel. This guide does not grant approval to connect 24 V or
exercise valves. Only after Danijel explicitly approves the physical test in
the current conversation, and all previous gates pass, may the trusted-console
operator follow [the water-isolated test](COMMISSIONING.md#5-connect-and-test-the-valves-with-water-isolated).
First isolate water, confirm the safe physical `Tuš` to `Izpust` path, and
confirm the supply label/rating and wiring are ready. The controlled approved
sequence is one minute `SUPPLY` through the authenticated paired control path,
then immediate `DRAIN`; observe both valves together and record the actual
plumbing paths plus both output/high readbacks. No `SUPPLY` helper or additional
sudo permission is introduced. Any failed receipt/readback stops the test:
request DRAIN, have the local operator safely disconnect valve power, and
investigate without repeating SUPPLY or assuming safe physical position.
DS18B20 commissioning remains a separate later stage.
