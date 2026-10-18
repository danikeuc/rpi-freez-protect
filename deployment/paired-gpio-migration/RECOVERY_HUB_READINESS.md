# Hub HTTP readiness recovery - 2026-10-14

Direct restricted diagnostics established that the first recovery passed pair
startup/DRAIN/ownership/preservation, then failed in operator_checks.status after
starting Hub: ConnectionRefusedError at the HTTP read. Type=simple start completion
and Node-RED ExecStartPre readiness do not guarantee the Hub listener is ready.
The failure cleanup left pair active and Hub stopped. Original evidence remains.

The revised wait_hub_status retries only urllib URLError whose OS reason is
ECONNREFUSED, while Hub remains active with a process, for at most a20-second
startup window. Individual existing HTTP reads keep their5-second timeout.
It never repeats start, DRAIN, or another mutating command. HTTP401/503, malformed
responses, incorrect control state, DNS errors, timeouts and process exit stop.

This root-console recovery is fixed to /root/paired-gpio-migration.xj0q8tgi and
its exact recorded ConnectionRefusedError at the archived recovery callsite.
Both loads remain disconnected. It validates the original archive, preparation,
boot/venv, installed artifacts, backup, data/history/settings, units, flow, paired
ownership and high/high, with Hub stopped and pair already running. It starts
only Hub, waits for verified USER_OFF and rechecks the same preserved state.
No pair restart, database restore, SUPPLY, light activation or firmware action.

The package also extends the existing maintenance status reader to the second
fixed recovery directory. It pins the currently installed diagnostic helper
SHA07eae1c9181f3910cd50e1873f278355c5c0941c450778b5afab1b9b05c4d77c,
backs it up privately and atomically replaces only that file. No SSH/sudo
permissions, one-shot migration claims, approval or service configuration changes.
Mutating helper behavior remains identical. Original failed receipts stay intact.
The status fields recovery and hub_recovery report distinct historical attempts.

Verify the outer hash and SHA256SUMS, then run once:

```sh
/usr/bin/python3 -I -B recover_hub_readiness.py --loads-disconnected
```

A private hub-readiness-recovery subdirectory is single-use. Success writes its
SUCCESS.json and prints PAIRED_RECOVERY_VERIFIED; old job failure is not erased.
On failure, preserve both evidence directories, leave loads disconnected and
inspect diagnostics. No automatic retry/rollback. Cleanup stops Hub and requests
DRAIN only if pair is active and no prior receipt/readback failed. Readback does
not prove physical valve position; crash/power-loss behavior remains unverified.
