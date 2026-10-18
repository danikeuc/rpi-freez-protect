# Controller OFF recovery candidate — 2026-10-18

Owner asked to continue using Superpowers and embedded-edge-systems-engineer.
Restricted SSH confirmed both APIs reachable, shower weather_fault_inhibited and
light clock_or_lease_fault, desired_on=false/gpio_on=false/revision70. No actuator
command or Pi mutation was performed during preparation.

## Change

manual_off can recover a configured faulted light only with a fresh OFF receipt.
It persists MANUAL_OFF with the existing manual duration, revision fence and
idempotency behavior. Fresh receipt/storage failure keeps or relatches FAULT.
Camera is blocked during that duration and resumes AUTO afterwards by existing
policy. Manual ON expiry still has the previously installed 900-second cooldown.
Clock discontinuity detection and fault inhibition remain unchanged.

Root-console package backs up both SQLite databases and light source, checks
exact prior cooldown source hashes and output/high, restarts only light-controller,
requires durable FAULT before restart, then issues manual_off and existing shower
CLEAR_FAULT. It verifies MANUAL_OFF/OK/OFF and USER_OFF/DRAIN. POST is never retried.
No direct GPIO writes, ON, SUPPLY, shell grant or general SSH permission added.
The current restricted helper cannot execute this package; trusted-root execution
is still needed under WORKSTATION_CODEX_COMMISSIONING.md.

## Verification

- Controller recovery tests were written first; missing behavior failed.
- 1,103 full pytest tests passed; one existing Starlette/httpx deprecation warning.
- 110 commissioning-assets tests passed; Ruff and git diff --check passed.
- Installer tests exercise real temporary SQLite backups and fake API/systemd,
  source drift, bad receipts, stale state, persistence failures and ambiguous POST.
- Previous packaged cooldown bytes match both required baseline hashes.
- Archive bytes round-trip verified, safe regular-file members only, shell syntax passed.
- No Pi installation, physical relay/contact verification or renewed AUTO shower test.

Original relay/clock causes remain unresolved. Safe recovery is not a permanent
fault-cause fix. The package reports sanitized latest relay error categories and
keeps raw events privately on Pi for investigation. Full four-domain failure matrix,
GPIO ownership/invariants and operator steps are in
[the runbook](../../deployment/lighting/recovery/README.md).

Package SHA256: `77a8beabf154f8fb641f7db5fb5840744e21cb9f314c90a4376c7c2247e16117`.
Controller candidate SHA256: `34b153c78493711199b74d42a856fb644fcbf225239c950c2885e423a40d8c5f`.
Installed status: **PENDING**. No new release or Git commit created in this step.

Delivery verification: workstation HTTP download on private LAN port38765 matched
the archive and every SHA256SUMS entry. Port8785 returned a preexisting unrelated
HTTP server; the recovery delivery was moved without changing that service.
Pi-side download and installation remain pending.

## Installation and independent acceptance — 2026-10-18

Operator supplied CONTROLLERS_RECOVERED_OFF for the exact controller candidate
34b153c78493711199b74d42a856fb644fcbf225239c950c2885e423a40d8c5f.
Backup: /root/controller-off-recovery.m6wcxg7l. The installer reported output/high
on GPIO20/21/26, light MANUAL_OFF/OK and shower USER_OFF/DRAIN.
The sanitized original relay error category is HTTP503; its underlying cause
is not established by that status code.

A separate restricted SSH maintenance status request independently confirmed:
- Shower weather_assisted, MANUAL_DRAIN, reason user_off.
- Light MANUAL_OFF, health OK, desired_on=false, gpio_on=false, revision72,
  manual_remaining_seconds1763 at observation.
- Hub, paired daemon and Node-RED active; PIDs761/436/627 unchanged from preflight.

This supersedes the pending-installation checkpoint above. No subsequent ON,
SUPPLY, AUTO shower activation, physical test or extra service restart was issued.
The light's existing temporary manual OFF expires back to AUTO; the shower stays
USER_OFF until a separate intentional START. UI/physical acceptance and the
original clock/HTTP503 cause remain separate from successful recovery.
