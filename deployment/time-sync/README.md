# Continuous time synchronization — prepared, not installed

## Scope

Operator root console only, Raspberry Pi4 ModelB Rev1.1. Requires both valve24V and lamp mains disconnected, light healthy/OFF, shower USER_OFF/DRAIN, exact diagnostic controller hashes, current DietPi mode2 and enabled/inactive systemd-timesyncd. No general SSH permission or package upgrade is introduced.

The observed forward step37.945s at2026-10-17T01:25:40Z preceded the historical light fault by36.309ms. This strongly supports that incident's clock trigger; shower HTTP503 remains unresolved.

## Exact change

Preserve /boot/dietpi.txt byte-for-byte except the single CONFIG_NTP_MODE=2 value becomes4. Preserve existing NTP server configuration; do not invoke DietPi's setter that also rewrites mirror settings. Its v10.6 implementation enables systemd-timesyncd for mode4; this baseline already has it enabled. Start the existing service. No manual clock setting or forced restart of the daemon.

Install root-owned /usr/local/lib/freeze-protect-time-ready.py, /etc/systemd/system/freeze-protect-time-ready.service, and35-time-ready.conf in both controller service drop-in directories. The new oneshot waits up to50seconds for three consecutive active-timesyncd/kernel-synchronized checks. Controllers Require/After this readiness unit. A failed first-boot sync blocks controller startup; GPIO owners remain independent. The oneshot remains active after success: this is a boot gate, not a continuous health monitor. Runtime clock protection remains unchanged. Large steps can still happen on first synchronization or after outages; there is no guarantee of step-free time.

## Operator sequence

Run the hash-verified package from the trusted root@DietPi session, with both loads disconnected:

    python3 -I -B time-sync/install_time_sync.py --loads-disconnected

The script performs preflight, makes root-private config/database backups, requests only manual_off if needed to inhibit the camera, confirms at least600seconds manual inhibition, stops only light-controller and freeze-protect, confirms outputs20/21/26 HIGH, snapshots quiescent databases, applies the time change and gate, verifies synchronization and durable inhibition, and starts controllers again. All other settings and credentials are checked for preservation. No ON/SUPPLY, CLEAR_FAULT, Node-RED restart, reboot or APT operation.

Success must report CONTINUOUS_TIME_SYNC_INSTALLED, synchronized=true, lightMANUAL_OFF/OK, showerUSER_OFF/DRAIN and all three output readbacks HIGH. Follow with separate restricted SSH status. Cold boot and physical acceptance remain NOT_TESTED.

Any failure stops with its last phase and backup path. No automatic retry/rollback. Failed-after-stop may leave controllers stopped; keep loads disconnected and inspect root-private failed.json. Never remove the marker merely to repeat installation. If time went backwards or inhibition expired, do not rewrite durable timers to bypass validation.

## Late synchronization after a failed startup gate

If the first readiness attempt fails, systemd does not automatically requeue either controller when synchronization succeeds later. The controllers stay stopped until a trusted-console operator checks the state and starts them. Keep both loads disconnected during this recovery.

At the root console, inspect the services and synchronization first:

    systemctl show freeze-protect-time-ready.service light-controller.service freeze-protect.service -p Id -p ActiveState -p SubState -p Result --no-pager
    timedatectl show -p NTPSynchronized

If synchronization reports `yes`, retry the bounded gate once and require `active/exited` before starting the controllers:

    systemctl restart freeze-protect-time-ready.service
    systemctl start freeze-protect.service
    systemctl start light-controller.service

Stop if the gate fails again or either controller fails to start. Before restoring any load, verify both services are active, the shower requests DRAIN, and paired GPIO20/26 readback is HIGH/HIGH. A service or GPIO readback does not prove physical valve position or lamp state. This recovery does not authorize ON or SUPPLY.

## Recovery

Before install backup captures original dietpi.txt bytes/metadata, controller databases and weather identity; prior time-service state is enabled/inactive. The original controllers' source and units are not overwritten. On a reviewed rollback, keep controllers stopped and loads disconnected, confirm current files still match this package, restore only the single time mode/config from backup without overwriting unrelated edits, remove only the four newly installed files, daemon-reload, and restore prior time-service state. Verify durable USER_OFF/MANUAL_OFF and HIGH readbacks before any controller restart. Do not restore stale database snapshots as a routine rollback or start controllers with invalid timestamps. Recovery needs an exact reviewed state; no blind rollback command is supplied.

## Fault boundaries

GPIO20/26 are a coupled pair: only HIGH/HIGH(DRAIN) and LOW/LOW(SUPPLY) are legal; this maintenance uses HIGH/HIGH only. GPIO21 independent active-low light remains HIGH/OFF. Readback is not valve/contact feedback.

| Fault | Required/retained behavior | Enforcer and evidence limit |
|---|---|---|
| Network/NTP unavailable at boot | Controller startup blocked after bounded wait | New time gate, locally tested; live cold-boot test pending. Existing GPIO owners initialize OFF/DRAIN; physical interval unverified. |
| Controller process crash/hang | Existing expiry/fault policy retained; no new guarantee | Existing executor and pair ownership unchanged. Light retained-ON crash behavior previously owner-accepted; no new energized test. |
| Pi reset/reboot | Gate waits for sync before controllers; no automatic bypass | systemd dependencies prepared; GPIO boot electrical/mechanical behavior not newly tested. |
| Power loss/restoration | Existing power-domain behavior retained | No claim that de-energization proves valve position. Both loads disconnected for this maintenance; physical test remains separate. |

## References

- https://github.com/MichaIng/DietPi/blob/v10.6/dietpi/func/dietpi-set_software
- https://github.com/MichaIng/DietPi/blob/v10.6/dietpi/func/run_ntpd
- https://github.com/MichaIng/DietPi/blob/v10.6/dietpi/dietpi-config

These upstream sources explain the mode; deployment preflight checks the actual selected baseline. No source match for all deployed DietPi scripts is claimed.
