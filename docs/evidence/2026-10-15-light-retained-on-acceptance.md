# Independent lighting process-failure acceptance

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
