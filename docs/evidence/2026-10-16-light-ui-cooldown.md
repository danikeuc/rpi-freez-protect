# Light UI and cooldown —2026-10-16
Owner approved modern circular UI and manualON expiry OFF,900s camera inhibition,thenAUTO.
Source: independent lighting branch, two-file Pi policy patch and Dial light UI.
1043 Python tests and Ruff pass;113 installer/commissioning tests included.
All4 native Dial light executables pass. Exact ESP-IDF5.5.5 build passes.
Independent review: cooldown/restart/fault/event fences clear. Missing Slovenian font glyphs
fixed using existing Unicode Lato22; regression failed before correction then passed.
Pi package SHA25635f0a329e3b068f1718f0edbc4da3f7c10972d9f3949a8172fe2fc1c9576b3c6.
Pi timer package NOT_INSTALLED; trusted root console required by current access boundary.
Dial candidate app848847d3ca13f3fbe10f2b505ccad19573e6f6862d81ac4c7170504a423adb71
written/readback verified on COM3 ESP32-S3 MACd0:cf:13:1e:15:44; NVS preserved.
Acceptance FAILED:5 CPU0 interrupt watchdog panics in45s; admin HTTP timed out.
Decoded candidate stack: r_lld_core_init,r_lld_init,r_rwble_init,r_rwip_reset,
btdm_controller_on_reset,btdm_controller_task. Cause not established.
Restoring previous exact appe0876060e4fe55d38819d547e49a0d9e8b2f38758c2456d1bea7f8560e7b68a5:
write/readback and NVS preservation verified; boot outcome recorded separately.
Predeployment Pi initially readlow/low. One documented DRAIN returnedpaired-v2
ok andhigh/high; subsequent status confirmedactive services andhigh/high.
No SUPPLY,lightON,playback or credential-changing command issued.
No release or Git publication. Do not report candidate installed/accepted.

Recovery outcome: previous exact app also reported5 CPU0 interrupt watchdog panics in45s. Admin remained unreachable. Thus rollback is byte-verified but operational recovery NOT_CONFIRMED. Full power-off/on requested; no further blind reflashes.

## Bluetooth startup investigation after full power cycle
ROM ELF decoding identifies r_assert_param <- r_emi_get_mem_addr_by_offset.
Diagnostic app0279d3f720e0a78f76521da4496718d8dba39ae8b86fe1ffd54f7454e9fa6b5f
produced4 panics/45s and explicit ALLOC_FAILURE(size616 or200,caps0x808),
then BLE_INIT Malloc failed and emi.c164 assertion. Caps0x808 are INTERNAL|DMA.
This establishes internal-memory exhaustion; the earlier UI candidate was not the only affected image.
The light HTTP reply was an8KiB ordinary calloc allocation below the16KiB internal-preference threshold.
Targeted fix uses explicit SPIRAM|8BIT with no internal fallback and preserves failure callback/admission release.
Production HTTP transport regression first failed on missing PSRAM allocation, then passed;
it also verifies allocation failure performs no HTTP exchange and releases admission.
All4 native light executables and firmware build passed. Hardware acceptance is pending for
app205d7ee852117212a31aebfe1250b2f9fa2562235de7bdf1444a06eba5d62080.
Pi SSH read-only status timed out during this turn; no new Pi installation attempted.

## Continued physical installation — memory diagnosis and data-only fix

The power cycle did not fix the internal/DMA allocation failure. The initial
PSRAM-reply-only candidate still asserted in the BLE controller. A BLE readiness
gate allowed controller initialization, but artifact75e1438c5b5a44a9d55a60fd569ebc2f0a1483f3d5e64388e3c0cb440d905de6
still failed allocations for mDNS and the HID reconnect worker; it was rejected.

Candidate79d87da9f3c2541463c38443d1e1c8f1d8a4fff97b7e169cc0f3e822d4cac6dc
additionally moves four Dial-only task data models to external BSS (15,576bytes
verified in the linked ELF), and allocates the12,288-byte playlist parser token
workspace in PSRAM. Task stacks and global allocation threshold remain unchanged.
Independent review found no material issue in the data-only changes. Light,
playlist, and NVS host suites pass; IDF5.5.5 build passes.

The exact app was flashed at0x10000 to ESP32-S3 MACd0:cf:13:1e:15:44 onCOM3,
verified by flash readback. NVS was backed up twice and compared byte-for-byte
after flashing. Fifty seconds of boot capture show zero panics and zero failed
allocations, successful BLE initialization and a running reconnect worker.
A reconnect attempt yields status0x0d; the remote wake state and actual
connection are not yet verified and require the operator test. Admin HTTP GET returns200 and81,738bytes.
Later idle internal free14,447bytes/largest7,680; acceptance is still workload
dependent and not inferred solely from boot.

Pi192.168.114.192 ports22/8082 are unreachable from the workstation while
Synology192.168.111.130:8088 is reachable. The cooldown package remains
NOT_INSTALLED. A user network-state question is pending. No new actuator
commands or credential/settings writes were issued during these checks.

## Operator-confirmed Pi installation completion

The earlier LIGHT_OFF_REQUIRED gate was health-related: the operator's local
status read returned mode AUTO, health FAULT, desired_on=false, gpio_on=false,
reason restart_clock_or_state_fault. This does not identify whether the original
cause was a prior stored fault or a clock discontinuity. No gate was bypassed.

After the recovery instructions, the operator supplied the successful installer
receipt for the same verified package SHA256
35f0a329e3b068f1718f0edbc4da3f7c10972d9f3949a8172fe2fc1c9576b3c6:

- result: LIGHT_COOLDOWN_INSTALLED
- cooldown_seconds: 900
- backup: /root/light-cooldown.o9557tym
- final mode: MANUAL_OFF
- gpio_on: false
- history_rows_before: 102
- actuator_commands: 0
- physical_acceptance: NOT_TESTED

This supersedes the earlier NOT_INSTALLED status. The installer receipt is
operator-provided evidence; no physical timing-cycle acceptance or release is
claimed. The initiating cause of the earlier latched fault remains unverified.

## Admin light status polling correction

The reported repeating unknown-state UI was reproduced in the production admin
JavaScript: the status receipt expired after 10 seconds without any periodic
status read, even when the controller was healthy. Added a status-only poll every
4 seconds while authenticated, visible, and on the Light panel. Busy operations
postpone polling; logout and visibility fences discard late replies. Unsaved
settings are preserved. Failed reads cancel the old render timer and invalidate
command admission; the existing 10-second freshness limit is unchanged.

The regression test failed before the change and passed afterwards, including
healthy refresh beyond expiry, failure/recovery, dirty settings, hidden/logout,
late replies, busy guard, and absence of action/settings writes. Independent
review found no material issue. Embed check and IDF 5.5.5 build pass.

Exact app SHA256:
7efbe2435e3786e787333c3339427205e8400b8795def77362e17c1ee051118f

App-only flash/readback on COM3 ESP32-S3 MAC d0:cf:13:1e:15:44 passed;
NVS before/after bytes match. Live GET /admin returns HTTP 200, 82,915 bytes,
and exactly matches canonical web/admin_dial.html (SHA256
9c1a9664f01df16c614e93e9c574c3f21e7ac3b76c6b5c826208776435b26eb8).
Operator observation after a browser hard refresh is pending. This establishes a
frontend cause of false stale-state reports, not absence of real network faults.
No actuator command, credential change, Git publication, or release was issued.

Post-flash 50-second boot capture completed: zero panics and no allocation-failure markers. Network reached OPERATIONAL. BLE initialized; remote reconnect returned 0x0d, so QGSQ connection acceptance remains pending. Receipt: light-poll-worker-boot.json.

## Operator reports continued unknown-state failures after polling fix

Operator screenshots show both shower FAULT/startup and Light unknown state.
The polling fix is therefore not full acceptance. Read-only SSH status succeeds:
three exposed services active, GPIO26/20 high. Eight workstation HTTP samples
return Dial session HTTP200 (125-188ms), Pi light gateway HTTP403 (16-94ms,
unauthenticated workstation request). These establish reachability only, not
success of authenticated Dial-to-Pi requests. Passive 45-second serial capture
contains ALLOC_FAILURE size=124 caps=0x80c function=heap_caps_malloc; internal
free=9275 largest=2560. Causation with the user-visible failure is not established.
No new fix or actuator command was issued. Authenticated browser status response
is requested using the current config-generation header. Browser automation
failed with trusted Node process exit; constrained SSH has no live light-status
read command. Root cause and full hardware acceptance remain pending.

## Continued phase diagnostics — 2026-10-17

Installed app-only diagnostic artifact SHA256
d0fe7121b875ee1aab636a0e36b4bc69d7db0f3a1ae2341759f786c0ffa1c777.
This adds bounded serial phase/status/size/elapsed markers, parse rejection and
admin admission-busy markers, without headers, tokens, URLs or response bodies.
Native light and BLE gate tests pass; IDF5.5.5 build passes. App readback and NVS
byte comparison pass. Boot capture 50 seconds: no panic, all status/settings
requests HTTP200. Follow-on capture currently has 32 successful network reads
and no failure markers. The prior failure has NOT been reproduced under browser
load yet. Shared display/admin admission is a hypothesis, not an established root
cause. Browser automation again failed to initialize; operator asked to keep the
Light panel open while serial capture runs. No actuator or configuration writes.

## Controller faults distinguished from transport failure — 2026-10-18

Owner confirms physical shower/light pages open but report fault or no connection.
Serial diagnostics from the exact installed app f71e00612dd940567c4b3d247f04b4353cd652fd753dc0a8333dec76abcc228a
(refer to controller-reason-worker-boot.json for the authoritative SHA) show HTTP200
and successful strict parsing for both services. Light: AUTO/FAULT, desired=0,
gpio=0, reason=clock_or_lease_fault. Shower: parsed state0/operation5,
reason=weather_fault_inhibited. Light UI freshness, validity, configuration and
session checks pass while known=0 due to controller FAULT. These observations
do not establish the initiating fault: the light catch covers clock, lease,
output and storage errors; shower inhibition is a persisted safety state.
Current workstation/Pi HTTP Date agreement does not exclude an earlier clock jump.
No actuator action or fault clear was issued in this diagnostic step.
A root-console GET-only diagnostic is prepared for bounded status/history and
categorized journal evidence; it prints no tokens or raw journal messages.
Restricted SSH does not permit these API/journal reads. Target diagnostic and
controller recovery remain pending.

## Live history retrieved through new restricted diagnostics — 2026-10-18

Shower remains weather_assisted/FAULT/weather_fault_inhibited. The original
fault event is relay_driver_error while requesting SUPPLY on 2026-10-16
17:52:16 UTC (19:52 local). Later restarts retained the inhibit. The sanitized
reader does not export the adapter's original error string, so the specific
transport/receipt failure is not established.

Light remains AUTO/FAULT/clock_or_lease_fault, desired=false and gpio=false,
revision70. Latest fault source is 2026-10-17 01:25:40 UTC (03:25 local),
preceded by manual_expired at 2026-10-16 21:27:59 UTC with desired=false.
No intervening activation appears in the retrieved ordered history. This points
to the clock check because idle AUTO/OFF does not renew a lease or expire
a manual timer; the actual clock discontinuity cause is not yet verified.
Historical rows also show wall-time reversals around restarts.
The bounded service journal search returned no matching categories; that does
not prove absence of clock adjustment or an older driver failure.
No clear-fault, AUTO action, restart or actuator command was issued. Recovery
is still pending and is outside the newly installed diagnostic-only capability.
