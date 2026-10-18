# Lighting target inventory

The paired kernel-ownership migration was verified on 2026-10-14. Lighting is
not activated. This read-only inventory collects the next missing runtime facts
without restarting services, installing packages, requesting GPIO lines,
evaluating settings.js, or changing flows or SSH permissions.

Run the reviewed `inventory.py` with `/usr/bin/python3 -I -B` in the existing
trusted root console on **DietPi**, not Synology. The exact Pi4 ModelB Rev1.1
check runs before any command. Share only its JSON projection. It never prints
raw journal lines, flow code, environment values or settings contents.

It reads known Node-RED files, their hashes and selected flow counts. Version
and path observations come only from the most recent 500 boot journal lines;
missing/older startup records do not establish effective runtime configuration.
It does not evaluate JavaScript to discover Projects, adminAuth, Function
external modules or context stores. Those remain unconfirmed, even if a file
hash or startup path matches. An active Project/custom flow path requires a
separate scoped review; do not install against the default file based on this
report alone. GPIO metadata uses only get_line_info on the verified chip, not
request_lines or value writes. A used=false observation is not a reservation.

No new remote command is added. The installed maintenance helper is still pinned
to the completed paired migration; it cannot run a lighting installation.
The root-console step is necessary until a separately reviewed lighting-specific
maintenance operation is installed. Never rerun consumed migration install jobs.

## Target receipt — 2026-10-15

The operator completed this inventory successfully. See the
[receipt](../../docs/evidence/2026-10-15-lighting-target-inventory.md).
Do not rerun it routinely: line21 was unused, paired ownership was present, and
Node-RED had no enabled light route. Effective settings and physical acceptance
remain unverified; the receipt distinguishes those limits.

## Remaining handoff

1. Inventory actual Node-RED runtime, effective settings and active flow.
2. Record the disconnected-load request/release/restart/crash acceptance for
   GPIO20/21/26. Current high/high snapshots are not transient traces.
3. Verify the real relay board, GPIO21 active level and the lamp circuit.
4. Capture installed Protect version and a redacted authenticated POST with
   original event ID, source, event type, original time and retry behavior.
5. Only then assemble/verify the deployment profile, private credentials and
   additive routes against that baseline, back up, deploy and verify OFF.
6. Provision/flash the exact Dial candidate and test its light UI, manual
   reminder and unchanged shower/Roon/BLE interactions. Connect real loads only
   under the separate bounded physical acceptance procedure.

The camera prerequisite does not prevent preparing the Dial/Pi software, but
no invented source ID or unsigned webhook should be used to bypass it. The
current controller also requires a nonempty allowed-source set, so manual-only
commissioning without a real camera profile needs an explicit reviewed design
change; do not silently fill it with a fabricated camera ID.
