# Dial admin settings — Pi candidate

**Status:** repository candidate for issue #21 and draft PR #22. This page describes
software behavior and a future staged installation; it is not a deployed Pi or
physical valve observation. See [PROJECT_STATE](../PROJECT_STATE.md) for the
separate historical device evidence and open physical gates.

## Contract and authority

The Pi Hub remains the only timed-shower authority. In `manual_timed`, a display
status response advertises `timed_shower_duration_supported: true`. The dial
may POST exactly `{"duration_seconds":60}` through `{"duration_seconds":600}`
in increments of 60 to `/api/v1/display/actions/timed-shower`. The default and
legacy empty-body POST are 600 seconds. Any explicit invalid value, including a
Boolean or fractional number, is rejected. Repeated START does not extend an
active deadline; a changed dial setting applies to the next accepted shower.
DRAIN is a separate empty-body action. All three display paths remain token
protected on the trusted LAN at Nginx port 8081; do not expose this surface to
the internet. Browser PIN and recovery handling live on the dial, not the Pi.

The internal Hub → Node-RED → client → daemon contract uses protocol version 2.
Each SUPPLY carries an explicit `begin` or `renew` action, echoed by the paired
receipt. Startup first requires a verified DRAIN receipt from the new protocol.
The daemon accepts `begin` only with verified DRAIN and no active lease, and
`renew` only while the original 60-second lease is still active. Daemon expiry
or restart makes old renewal ineligible. In `manual_timed`, renewal rejection
clears the Hub timer, requests best-effort DRAIN, and latches FAULT. A distinct
new START after verified DRAIN and fault clear is needed for recovery. Ordinary
dial Wi-Fi loss does not cancel a shower already accepted by the Pi. Automatic
mode retains its existing policy-driven initial SUPPLY and renewal semantics;
it is not enabled by this candidate.

A saved shorter duration must fail closed if the Pi is rolled back or capability
status is stale/missing. Do not submit an empty-body START as a fallback. The
only legal paired GPIO commands are DRAIN high/high and SUPPLY low/low on BCM
26/20, through the paired daemon. Keep 24 V disconnected absent approval for the
same bounded physical test in the current conversation. GPIO readback is not
valve-position evidence.

## Candidate deployment sequence and rollback

1. Capture the running Pi source/package identity, active mode, service status,
   gateway and deployed-flow preflight through the existing reviewed procedure.
   Back up protected environment/config and Node-RED flow using the existing
   operator backup path without printing credentials; record hashes of redacted
   exports where useful. Keep `manual_timed` and requested DRAIN.
2. Retain the verified v1.0.0 Pi package/source and existing dial four-region
   bundle as rollback artifacts. Stop the Hub and verify requested DRAIN and
   paired readback through the reviewed procedure. Upgrade the daemon and
   client together, then the bridge, then the Hub while outputs remain DRAIN.
   The bridge's startup DRAIN must confirm protocol version 2 before it can
   accept SUPPLY; the Hub separately requires its own successful version 2
   DRAIN receipt. Mixed versions refuse SUPPLY. Confirm package identity
   separately from service and deployed status. Verify display status
   capability read-only; a timed action needs separate bounded approval with
   24 V disconnected. Stop on a failed receipt, readback, service or flow
   preflight.
3. After separate approval, install the exact candidate dial image while
   preserving NVS, and run the acceptance record in the
   `docs/operations/dial-admin-settings.md` runbook of the companion
   `roon-knob` repository.
4. For Pi rollback, stop the Hub, leave requested state DRAIN, verify the
   approved stopping path, and restore the whole compatible daemon/client,
   bridge and Hub stack. Hot downgrade during an active interval is unsupported.
   A dial with a saved duration below ten minutes blocks START
   when the old Pi lacks capability. Keep this block in place; restore the
   compatible Pi API or deliberately choose ten minutes on a supported setup.
   Recheck all service, gateway, flow and readback gates. A repository rollback
   alone does not establish device state.

Do not use the commissioning SSH account as a shell, bypass the forced-command
allowlist, or run a SUPPLY diagnostic. Installation and fault injection require
separate authorization and the workstation commissioning procedure.

## Failure domains

| Fault | Candidate response and surviving owner | Evidence and required acceptance |
| --- | --- | --- |
| Dial-to-Pi communication loss | Dial drops pending START rather than replaying on reconnect. An already accepted Pi deadline continues under Pi authority. | Host tests cover client replay; no new deployed timeline or valve observation. |
| Hub-to-daemon renewal loss | The independent daemon expires the 60-second lease and requests paired DRAIN. Late `renew` is rejected; the Hub faults and clears its timer. | Real service/daemon fake-clock and fake-register tests; scheduling/receive latency and physical routing remain pending. |
| Hub process crash or hang | Daemon lease is the intended independent DRAIN enforcer while Hub cannot renew. | Code/tests only for this candidate. A stuck process and energized valve outcome remain unverified. |
| Controller/service restart | Daemon restart has no lease, and Hub startup clears its timer and requires protocol 2 DRAIN. Old renewal cannot begin a new lease. | Software traces only; electrical boot interval, relay contacts and hydraulic outcome are unverified. |
| Power loss/restoration | The design requests conservative startup; software cannot prove valve position while unpowered. | Relay, actuator supply and plumbing behavior remain unknown; test each relevant power domain only under a separately approved safe envelope. |

The old renewal/reassertion risk is addressed in candidate Pi source and
fake-register tests. The queued Dial START age gate is a separate companion
firmware change; its results belong to that candidate's verification record.
Neither source result establishes an installed version or physical behavior.

The older disconnected GPIO and operator physical observations in PROJECT_STATE
apply only to their recorded revisions and scopes. They do not certify this
candidate's fault response or physical routing.
