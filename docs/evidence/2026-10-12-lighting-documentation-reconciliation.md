# Lighting documentation reconciliation - 2026-10-12

Scope: documentation only. No implementation, dependency installation, device
request, GPIO write, service restart, flow deployment or new release.

| Source | Evidence / interpretation | Reconciled destination |
| --- | --- | --- |
| Owner conversation | Third relay independent; AUTO accepts camera and ESP; temporary manual ON/OFF with reminder and one-hour default return accepted | Canonical lighting specification sections 1,4,5 |
| Owner load clarification, 2026-10-12 | LED lighting, maximum 20 W total at 220 V mains; reported specification, not measurement or contact-rating approval | Canonical load row and commissioning prerequisites |
| Prior proposed hold duration | Five minutes was proposed, not selected by owner | Spec explicitly marks unconfirmed default |
| 2026-09-11 M1 board record | Waveshare RPi Relay Board, GPIO21/header40 reserved, active-low | Candidate pin map; actual revision/load unverified |
| paired_gpio_daemon.py | PINS=(26,20); no third-relay control | New lighting owner must not change paired pin set |
| Existing Node-RED export | 11 nodes, zero structural issues from skill inspect_flow.py | Separate ingress tab proposed; no current flow changed |
| Current gateway source | Seven exact display paths including weather and history | README and architecture corrected from old three-route description |
| Pi 1.3.1 receipt | Exact wheel/source, USER_OFF/DRAIN, seven history rows on each route | Existing release evidence retained; no new hardware proof |
| Dial v1.3.0-shower.3 | Exact CI flash/readback, operator-visible history confirmed | Companion README no longer calls all custom work undeployed |
| UniFi official webhook docs | Outgoing GET default, POST alarm/timestamp; actual POST auth and identity still require a captured profile | Spec ingress requirements; no invented console version |
| Node-RED security docs | Editor and HTTP-node security are separate | Lighting ingress auth separated from editor/admin auth |

## Canonical source and companion boundaries

The source of truth is
[the lighting specification](../superpowers/specs/2026-10-12-independent-lighting-design.md).
[Node-RED contract](../operations/independent-lighting-node-red.md) owns adapter
constraints. Companion roon-knob docs/operations/independent-lighting.md owns UI
integration notes and links back to the canonical spec. The Roon bridge is not
part of lighting control; it requires no new route, secret, or deployment.

Historical specifications, released tags/binaries, code, GPIO restrictions and
previous evidence are preserved. The future reassignment of GPIO21 is documented
without claiming it already happened. Review/implementation planning is a later
step; unresolved load/auth/fault-enforcement facts are listed concretely in the spec.

## Document checks

Executed local checks: all 90 relative Markdown links across the eight changed
/new documents resolved (77 Pi, 13 Dial), and git diff --check passed in both
repositories. The existing paired Node-RED export inspector reported 11 nodes
and zero structural issues. No code or physical tests are claimed.
