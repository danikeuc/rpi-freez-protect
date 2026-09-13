# Workstation Codex commissioning

This guide defines the workstation-led commissioning route. Use only the
dedicated `freezeprotect` account for remote access. Do not configure an
automation runner or use a privileged remote login. The 24 V valve supply
remains disconnected until Danijel explicitly approves the physical test in
the current session. Keep Pi SSH private-LAN-only; do not expose it publicly.

## 1. Workstation prerequisites

Install Codex CLI, Git, OpenSSH client and PlatformIO Core on the workstation.

## 2. Pi bootstrap

At the trusted local Pi console, inspect the existing account before provisioning.
The dedicated login profile is home `/home/freezeprotect`, shell `/bin/bash`,
a non-root UID/primary group, and group membership consisting of that primary
group plus `dialout` and `gpio` only. A pre-existing service account from
[`COMMISSIONING.md` step 1](COMMISSIONING.md#1-make-the-pi-service-files)
uses `/var/lib/rpi-freeze-protect` and `/usr/sbin/nologin` and is incompatible.
Bootstrap stops before changing its keys or groups; it does not migrate that
account or silently retain extra groups. Stop and have the trusted-console
operator review service ownership/dependencies and explicitly remediate the
account profile before rerunning. Do not delete the account or its service data.
For a new installation, bootstrap creates the dedicated login account; omit the
older guide's service-account `useradd` command.

Copy a reviewed, trusted repository revision to `/opt/rpi-freez-protect`.
Keep deployment assets and service execution paths root-owned and not writable
by `freezeprotect`; never recursively hand over the entire checkout. Bootstrap
copies the standard-library-only GPIO client to the root-owned
`/usr/local/lib/freeze-protect-commission/paired_gpio_client.py`, invoked by
`/usr/bin/python3 -I`, not from the checkout. Its directory, the outer helper,
and their ancestors must remain root-controlled and non-user-writable.
Updates to either installed artifact are trusted-console deployment work only.

Bootstrap makes the home root-owned `0750`, `.ssh` root-owned `0710`, and
`authorized_keys` root-owned `0640`, using the account's primary group. This
allows SSH to read the key but prevents the account from changing it or
replacing `.ssh`. It validates ownership/modes and account read/non-write access
before reporting success. Keep firmware/build work separate: the workstation
clone is writable; if using Pi-side PlatformIO, the trusted-console operator
must provision only the `firmware/crowpanel` build subtree and dedicated
`/home/freezeprotect/.platformio` and `/home/freezeprotect/.cache` directories
as account-writable. Do not make the home itself, deployment scripts, service
virtual environment, or privileged execution paths writable to enable builds.

Place the workstation public
key in `/tmp/freezeprotect-workstation.pub`, then run this one command from a
trusted local Pi console:

```bash
sudo /opt/rpi-freez-protect/deployment/workstation-codex/bootstrap-freezeprotect-access.sh \
  /tmp/freezeprotect-workstation.pub
```

From the workstation, verify the restricted account and helper over the Pi's
private LAN:

```bash
ssh freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission inventory
```

After that succeeds, remove the temporary `root` key from
`/root/.ssh/authorized_keys` at the trusted local Pi console. Also remove the
temporary public-key file from `/tmp`.

## 3. Local Codex session

Start Codex from the cloned repository on the workstation. Copy the complete
local instruction from
[`workstation-codex/CODEX_COMMISSIONING_PROMPT.md`](workstation-codex/CODEX_COMMISSIONING_PROMPT.md).
It requires the dedicated non-root account, non-interactive read-only SSH
checks, and Danijel's explicit approval before any 24 V stage.

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
ssh -o BatchMode=yes freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission inventory
ssh -o BatchMode=yes freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission usb
ssh -o BatchMode=yes freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission status
ssh freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission drain
```

The `usb` output is an inventory, not permission to select a device. Before
any upload, serial discovery must return exactly one `/dev/serial/by-id`
device. Stop for zero matching devices or for more than one matching device;
do not guess a serial path.

### USB cable on the workstation

From `firmware/crowpanel`, discover the serial-by-id device and proceed only
after confirming that the command returns exactly one entry. Record that
discovered entry as `serial_device`; it is the only path permitted below.

```bash
find /dev/serial/by-id -maxdepth 1 -type l -print
pio run --target upload --upload-port "$serial_device"
pio device monitor --baud 115200 --port "$serial_device"
```

Collect the boot output from the monitor. Stop rather than use either `pio`
command if discovery returned zero or more than one device.

### USB cable on the Pi

Use the same discovery and `pio` commands on the Pi, prefixed with the
dedicated account over the private LAN. The Pi-side discovery must return
exactly one entry before setting `serial_device`; stop for zero or more than
one device and never guess a serial path.

```bash
ssh freezeprotect@<Pi-LAN-IP> find /dev/serial/by-id -maxdepth 1 -type l -print
ssh freezeprotect@<Pi-LAN-IP> "cd /opt/rpi-freez-protect/firmware/crowpanel && pio run --target upload --upload-port \"$serial_device\""
ssh freezeprotect@<Pi-LAN-IP> "cd /opt/rpi-freez-protect/firmware/crowpanel && pio device monitor --baud 115200 --port \"$serial_device\""
```

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
