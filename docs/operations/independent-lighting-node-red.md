# Independent UniFi lighting ingress in Node-RED

Task 2 implemented in repository, 2026-10-13, flow disabled and not deployed.
[Canonical specification](../superpowers/specs/2026-10-12-independent-lighting-design.md)
owns behavior; [deployment/profile gates](../../deployment/lighting/README.md)
document exact configuration, failures and rollback.

| Boundary | Contract |
| --- | --- |
| HTTP In | Private POST /lighting/unifi; exact new gateway events route |
| Authentication | Separate ingress Bearer token, no URL credentials |
| Profile | Explicit version 1 paths, stable ID/source/time/type; no inferred defaults |
| Validation | JSON 4096 bytes, UTC age 60 seconds / future 5 seconds, source/type allowlist |
| Forward | Fixed loopback 8002 events/unifi, separate camera token |
| Response | Single preserved req/res/_msgid, sanitized accepted/duplicate or error |
| Failure | Absolute 1500 ms, response 8192 bytes, no retries, On Stop cancellation |

Controller alone owns durable deduplication, modes/deadlines and settings/history.
No GPIO/exec/relay nodes, global/flow policy context, startup activation or fallback
commands. Node-local memory context holds transient transport cancellers only.
Redeploy cancellation cannot undo an already accepted event. Repeated deliveries
forward original identity/time unchanged. Ignored manual/duplicate results keep
controller accepted/duplicate flags; fresh status resolves uncertain delivery.

Historical recorded runtime: DietPi RPi, node-red.service, loopback 1880, user
nodered, /mnt/dietpi_userdata/node-red/flows.json. These records are not current
runtime verification. Exact Node-RED/Node.js, settings, palette and Projects
must be captured before deployment. Preserve existing paired route/client and
unrelated flow tabs/IDs. Review built-in http/crypto Function library loading,
functionExternalModules and named memory-only context store memory; secure
editor/Admin API separately using adminAuth and network controls. Tokens remain
in protected external configuration, never Debug/URL/browser/export.

The [official Protect page](https://help.ui.com/hc/en-us/articles/25478744592023-Send-UniFi-Protect-Alerts-to-Web-Services-using-Webhooks)
checked 2026-10-13 documents custom headers for GET and POST alarm data/timestamp.
Stable event ID and authenticated POST on the actual console are unknown.
Keep tab/source gate/LIGHT_UNIFI_ENABLED disabled until actual version,
sanitized samples/retries, stable original identity/time and source/type paths
and authenticated POST are demonstrated and reviewed. Official example lacks
the required stable event ID; synthetic test profile is not claimed compatible.

Adapter tests execute normalization/auth/HTTP transport simulations. Asset tests
check disabled/isolation/flow-source consistency. Inspector checks structure.
These do not prove import/runtime, GPIO release or lamp illumination. Simulated
controller delivery, timeout/redeploy, library/version compatibility, reverse
proxy limits and shared runtime impact need deployment verification. Legal
output combinations, lease/restart bounds, unknown reset/power behavior and
live-test prerequisites are in deployment README. Rollback verifies light OFF
through its owner then restores only lighting assets; no shower/Roon/BLE/paired
GPIO26/20 or deployed assets change.

Official references:
[endpoint security](https://nodered.org/docs/user-guide/runtime/securing-node-red),
[message contract](https://nodered.org/docs/user-guide/messages),
[Function lifecycle/cleanup](https://nodered.org/docs/user-guide/writing-functions).

## GPIO_SHARED_FSEL2_COEXISTENCE — activation blocked

**Installed migration verified on 2026-10-14; lighting acceptance remains open.**
The exact kernel-ownership daemon and paired dropin are installed on the Pi.
Restricted SSH confirmed the separate Hub-recovery success marker, all three
services active and paired output/high readback. See the
[dated recovery evidence](../evidence/2026-10-14-device-allow-recovery.md).

The legacy userspace FSEL writer is no longer the recorded installed backend.
The source repair and installed migration close that part of
GPIO_SHARED_FSEL2_COEXISTENCE. They do not close the disconnected-load
startup/request/release/crash trace or physical acceptance requirements.
Keep lighting templates, flow and gateway disabled. Do not create
/etc/independent-light/commissioned, set LIGHT_GPIO21_ENABLED=commissioned or
grant light DeviceAllow until the remaining disconnected acceptance is recorded.
Kernel-only configuration does not establish atomic initial direction changes,
crash protection, physical independence or valve position. Actual Protect
profile, Node-RED runtime and lamp/wiring gates remain open.

## Owner decision: light may remain ON after process failure — 2026-10-15

The owner explicitly answered "da" after being asked whether the independent
light may remain ON after a process crash or hang until control is restored or
a manual intervention occurs. This accepts an unbounded ON duration for this
light failure case; the regular hold/override timer is not a guarantee while its
enforcing process is unavailable. No independent crash/hang cutoff is required
for this light under this decision.

This is a requirement change, not a successful fail-OFF test. The original
LIGHT_LEVEL_MISMATCH receipt and first crash_release output/LOW sample remain
unchanged. Normal ON/OFF, final OFF recovery and sampled paired HIGH/HIGH were
observed. Executor hang behavior is accepted as a possible retained ON state,
not claimed to have been tested.

The exception applies only to independent light GPIO21. Shower GPIO20/26 safety,
paired transitions, deadlines and fault requirements are unchanged. Keep normal
communication-loss expiry, explicit OFF behavior, startup OFF and prevention of
stale command replay. No new guarantee is made for reset/boot, power domains,
contact wiring, physical position, mains connection or remote actuation rights.
The existing no-repeat marker must not be deleted merely to turn the old failed
test into a pass.

Camera forwarding remains disabled until service, ingress, credential and
functional acceptance are actually completed. Crash-release automatic OFF is
no longer a blocker by itself under this recorded owner decision.
