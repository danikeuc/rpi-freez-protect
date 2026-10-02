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
   bundle as rollback artifacts. Install the reviewed compatible Pi API first.
   Confirm its repository package identity separately from service and deployed
   status. Verify status capability read-only; any empty or explicit timed
   action requires a separately approved, bounded test with 24 V disconnected
   before updating dial firmware. Stop if any receipt,
   readback, service or flow preflight fails.
3. After separate approval, install the exact candidate dial image while
   preserving NVS, and run the acceptance record in the
   `docs/operations/dial-admin-settings.md` runbook of the companion
   `roon-knob` repository.
4. For Pi rollback, first leave requested state DRAIN and verify the approved
   stopping path. A dial with a saved duration below ten minutes blocks START
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
| Hub-to-daemon renewal loss | The daemon lease requests paired DRAIN after renewal stops, subject to the historical possible renewal/reassertion risk below. | Repository lease tests only; deployed timing and physical routing remain pending. |
| Hub process crash or hang | Daemon lease is the intended independent DRAIN enforcer while Hub cannot renew. | Code/tests only for this candidate. A stuck process and energized valve outcome remain unverified. |
| Controller/service restart | Pi startup requests DRAIN; dial must load saved settings and require fresh capability before START. | No new boot interval, relay-contact or hydraulic observation. |
| Power loss/restoration | The design requests conservative startup; software cannot prove valve position while unpowered. | Relay, actuator supply and plumbing behavior remain unknown; test each relevant power domain only under a separately approved safe envelope. |

A historical review flagged two possible baseline risks requiring fresh final
review: Hub renewal may reassert SUPPLY after a daemon lease has expired, and a
delayed queued START may lack an independent wall-clock expiry. These are
carry-forward findings, not new reproductions or claims that this feature
changes the baseline behavior. Resolve their scope before any live acceptance.

The older disconnected GPIO and operator physical observations in PROJECT_STATE
apply only to their recorded revisions and scopes. They do not certify this
candidate's fault response or physical routing.
