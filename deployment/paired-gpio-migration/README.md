# Trusted-console paired GPIO migration

This package prepares and installs the reviewed kernel-ownership daemon for the
inventoried Raspberry Pi 4 Model B Rev 1.1, kernel 6.18.39+rpt-rpi-v8,
Python 3.13.5 aarch64. It requires the canonical `/dev/gpiochip0`; aliases and
unknown profiles fail closed. Repository tests are not live hardware evidence.

Keep both the 24 V valve supply and mains lamp load disconnected throughout.
The current conversation authorizes this installation envelope. No SUPPLY,
lighting activation, firmware, Node-RED editing, or physical test is included.
Only the trusted local console operator runs these commands. Do not expand the
restricted commissioning account's four-command allowlist.

## Package trust and preparation

The controller supplies a private, root-owned directory containing these files:
`migrate.py`, `operator_checks.py`, `paired_gpio_daemon.py`,
`paired_gpio_client.py`, `paired-gpio.conf`, `paired-gpio.env`, `pair.service`,
`hub.service`, `hub-readiness.conf`, `preflight-no-legacy-gpio.js`, the exact wheel,
`manifest.json`, this README and `SHA256SUMS`. Verify the reviewed outer archive
SHA256 before extracting; all ancestors and files must remain root-controlled,
without symlinks or group/world write permissions. The package directory is0700.
`manifest.json` has exactly one `files` mapping with the eleven fixed runtime
filenames. README and manifest itself are covered by outer SHA256SUMS. The
manifest cannot choose install destinations or add executable files.

The only wheel is
`gpiod-2.3.0-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl`,
SHA256 `7fdc3f63a277f8ae193f0c9b565bbd48e525e94c39cd463acd7b06250bf26507`.
Preparation uses offline pip with no dependencies or network resolution. It
creates `/opt/freeze-protect-paired-gpio/venv-2.3.0` with copied interpreters,
root ownership and traversable service permissions. It never modifies the Hub
virtual environment or installs OS packages. Missing venv/ensurepip support or
an existing target environment stops for local review; there is no automatic
repair, deletion, or reuse of an incomplete environment.

From the verified package directory, run once:

```sh
/usr/bin/python3 migrate.py prepare --24v-disconnected --mains-lamp-disconnected
```

Keep the printed `/root/paired-gpio-migration.<id>` evidence directory. A success
means PREPARED.json was durably written, binding the exact bundle, interpreter
and environment files, host boot, baseline and source HEAD. Preparation performs
read-only active-service, USER_OFF, database identity, deployed-flow, GPIO level
and platform metadata checks, including the existing read-only `pinctrl get`
level checks. The candidate probe does not construct `KernelOwnedPair`, request
lines or map MMIO. Preparation does not write GPIO or change services. The exact reviewed source
is passed over stdin to the isolated interpreter under `nodered`, so the private
package directory does not have to become readable to the service account.

## Install the prepared candidate

Use the exact evidence directory printed by prepare:

```sh
/usr/bin/python3 migrate.py install --24v-disconnected --mains-lamp-disconnected /root/paired-gpio-migration.<id>
```

Installation verifies the prepared receipt and repeats all live guards. The
existing Hub1.3.1 base unit and exact `30-node-red-readiness.conf` are required
and preserved. Unknown overrides/configurations, active or enabled lighting,
non-USER_OFF status, invalid weather identity, changed daemon/unit/source or
stale preparation stop before cutover.

Before service mutation, the installer writes and verifies private copies of
all affected or preserved files, SQLite and its matching weather identity,
settings/history and runtime inventory. Then it stops Hub, confirms DRAIN once,
stops the paired owner, confirms MainPID0 and both outputs high, and waits two
seconds for old requests to expire. It replaces only the daemon and adds the
reviewed paired dropin, environment and paired-only approval marker. It verifies
systemd configuration, starts the new paired owner, checks one protocol2 DRAIN
receipt, high/high and kernel consumers, then starts Hub through its existing
Node-RED readiness gate and verifies USER_OFF and preserved data.

The new dropin sets `Restart=no`. This intentionally changes the base unit's
`Restart=on-failure`: a failed candidate stops for operator investigation instead
of automatically reacquiring lines repeatedly. Consequently a later daemon
crash will require trusted-console investigation/recovery; automatic process
recovery is disabled. The paired lease and cleanup cannot guarantee safe output
when its process cannot run. Independent crash/power-loss protection remains
unverified. No lighting marker or opt-in is created.

On success, retain SUCCESS.json and the entire protected evidence directory.
Only share the sanitized terminal receipt; private logs, environment backups and
SQLite may contain credentials or private history. Do not paste them into chat.

## Stop and recovery

The first failed receipt/readback latches a stop and is never retried. A partial
cutover keeps Hub stopped; cleanup may request DRAIN once only if the paired
owner is running and no prior receipt/readback failed. Cleanup does not prove
physical position. There is no automatic rollback or second install attempt.
Keep both loads disconnected and inspect private evidence locally. Do not
restart from a failed or partially prepared directory without reviewing the
exact failure and installed files.

For a separately reviewed rollback, first confirm lighting ingress closed,
lighting OFF via its owner if applicable, and both lighting services stopped
and disabled with lighting markers/opt-in removed. Restoring the old raw FSEL
writer while GPIO21 may acquire/release is prohibited. With loads disconnected,
restore only the saved paired daemon and its exact interpreter/unit configuration
and remove the new paired dropin/environment/marker after reviewing their current
hashes. Reload and verify systemd, startup DRAIN, protocol and high/high. Keep
Hub stopped until all gates pass. Never restore databases to undo this migration,
enable legacy individual GPIO flows, or use SUPPLY diagnostically.

Legal energized (valve1,valve2,light) states remain (0,0,0), (0,0,1), (1,1,0),
(1,1,1). The migration envelope leaves lighting disabled. Valve DRAIN reads
HIGH/HIGH; this does not establish contact position or plumbing state.

| Fault | Required result and surviving mechanism | Evidence limitation |
| --- | --- | --- |
| Communications loss | Paired owner requests DRAIN when its60s local lease expires | Physical timing unverified |
| Paired process crash/hang | Independent mechanism must establish DRAIN | No proven surviving cutoff; Restart=no prevents automatic restart; bound unknown |
| Controller reset/reboot | Preserve paired constraint and safe state before ownership | Boot/release behavior and timing unverified |
| Pi power loss/restoration | Reach safe hydraulic state without unintended activation | Independent/passive behavior unverified |
| Valve24V loss/restoration | Preserve coupled contact/valve constraint and safe plumbing | Actual valve position/recovery unverified |
| Lamp mains loss/restoration | Lamp remains safe/off | Lamp load disconnected; electrical acceptance unverified |
