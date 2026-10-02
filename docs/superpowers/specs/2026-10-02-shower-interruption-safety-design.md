# Shower interruption recovery and START admission

Date: 2026-10-02
Status: user approved the recovery/expiry behavior with “ok, vredu” after the explicit proposal. Repository implementation only; no deployment or live actuation approved.

## Approved behavior

In manual_timed, once the independent paired daemon drains because its lease expires, recovery must not restart water without fresh user intent. Daemon restart must also reject renewal of the previous interval. Ordinary Dial Wi-Fi loss leaves an already accepted Pi interval running to its original deadline. An unsent Dial START expires at age >= 10,000 monotonic milliseconds; DRAIN is not subject to that admission expiry.

## Existing-path repair

Keep the display API unchanged. Extend the internal Hub → Node-RED → CLI → daemon contract to protocol_version=2 and explicit SUPPLY supply_action=begin|renew. DRAIN has no supply action. No missing/invalid mode defaults to begin. Echo protocol and mode in successful receipts and validate them.

The daemon owns the sole active lease and paired GPIO. Begin requires verified DRAIN/no unresolved GPIO fault and no active lease. Renew requires a still-active unexpired lease. A repeated begin cannot extend an active lease. Expiry is now>=expires_at, enforced before admitting a request after blocking receive. DRAIN, expiry, startup and failed writes invalidate lease eligibility before touching GPIO. A readback failure cannot retain eligibility; later verified DRAIN may clear the GPIO fault but never recreate an old lease. SUPPLY is single attempt; failure falls back only to paired DRAIN. Failed response delivery must not cause automatic begin retry or abandon lease enforcement.

New Hub startup requires a successful non-energizing DRAIN receipt with protocol2 before any SUPPLY. New bridge readiness likewise requires verified DRAIN/protocol2. SUPPLY is rejected at every strict layer if its mode is missing. Safe DRAIN remains available when capability or readiness is unconfirmed, with authentication preserved. New manual START emits begin; periodic active interval renewal emits renew. Renewal rejection preserves the existing best-effort DRAIN, FAULT and cleared timer; no automatic rearm or begin fallback. User DRAIN/clear-fault returns to idle, then a distinct new START can begin again.

Automatic mode is not activated by this change. Preserve its existing initial policy-driven SUPPLY transition using begin and continuing SUPPLY using renew; a failed renewal faults rather than silently beginning again. Existing automatic-to-timed handling must not emit a duplicate begin for an already active supply. The fresh-human-START guarantee is explicitly for manual_timed.

## Dial admission boundary

Capture full-width monotonic time with queued START. Check age before dispatch and again after preflight immediately before calling the POST transport; reject age>=10,000ms or a backwards clock with a timeout completion. Separate expiry admission from session/config validity and delivery of late responses. Never age-expire DRAIN, retry an expired START, or cancel the accepted Pi timer on Dial disconnection. A POST already handed to transport can still be accepted after local UI timeout; reconcile it honestly. This is not a server-enforced network delivery deadline.

## Compatibility and recovery

Mixed versions must fail closed before SUPPLY: startup DRAIN validates the downstream protocol, old clients missing mode are rejected by new strict layers, and no exception-based fallback to old driver signatures is allowed. Safe DRAIN does not require a SUPPLY capability. Upgrade daemon/client, bridge, then Hub while Hub is stopped and outputs are verified DRAIN; coordinated rollback also stops the Hub and restores the whole compatible stack. Hot downgrade during an active interval is unsupported. Preserve v1.0.0 and NVS/config backups. No live action is part of this task.

## Evidence and fault domains

Legal GPIO26/20 pairs remain (1,1) DRAIN and (0,0) SUPPLY, through one atomic mask write; logical DRAIN=0/SUPPLY=1 is a separate user concept. Register readback is not valve-position proof.

| Fault | Required response and surviving owner | Evidence boundary |
| --- | --- | --- |
| Dial link loss | Accepted Pi interval keeps its deadline; unsent commands invalidated/expired | Real client tests with fake transport/clocks; no live result implied |
| Hub/bridge crash or hang | Independent daemon drains on 60s lease; recovery renew rejected | Nominal lease plus scheduling/receive latency; real policy with fake registers/clocks. Daemon hang needs an independent mechanism, still unverified |
| Daemon or controller reboot | No active lease; startup DRAIN; reject old renew. Hub reboot clears timer | Software tests cannot establish electrical boot interval |
| Separate Pi, relay or 24V power loss/restoration | Physical safe state remains required for each power domain | Mechanics, stored energy and timing unverified; no physical acceptance claimed |

## Acceptance

Execute real service/daemon/bridge code with injected transport, registers and clocks: ordinary begin/renew; exact expiry; late renew; fresh daemon; bridge startup DRAIN; failed write/readback; duplicate begin; mismatched/missing mode/version; lost receipt; no automatic low-pair write after expiry/reset. Assert timer clearance and fresh explicit recovery. Dial cases: 9999/10000ms, preflight crossing deadline, backwards time, DRAIN unaffected, late completion delivered, disconnect no cancellation. Existing Python suite/Ruff/mypy, affected Node function fixtures, canonical Dial suites/full shared checks and exact ESP-IDF5.5.5 build form repository gates. Independent reviews and draft PR updates follow; hardware acceptance remains separate.
