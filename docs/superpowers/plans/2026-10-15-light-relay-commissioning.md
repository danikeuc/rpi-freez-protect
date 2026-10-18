# Light relay commissioning continuation

Owner authorizes connecting MCP to relay21, lamp disconnected. Confirm valve24V
also disconnected and USER_OFF before driver bench. Fresh read2026-10-15 showed
paired LOW/LOW; do not treat older DRAIN evidence as current.

1. Prepare bounded root-console GPIO21 bench package first. Use installed isolated
   gpiod2.3 interpreter. Require exact Pi4, installed paired daemon hash/ownership,
   USER_OFF, high/high readback and no existing GPIO21 owner. Read-only mmap samples
   capture levels/direction of20/21/26. Only request/write21. Exercise startup OFF,
   shortON/OFF, normal release, child crash whileON, finalOFF recovery. Retain
   samples privately; do not claim high-speed/physical validation from point samples.
2. Test guards, worker GPIO mask, cleanup and failure with fake driver/transport;
   independent review before handoff. Build pinned archive and checksum; serve from
   workstation without a30min expiry. Root-console command is required: existing
   remote helper only authorizes pinned paired migration, not this new bench.
3. Assess the actual bench against the current accepted contract. The2026-10-15
   owner decision accepts retained GPIO21 ON on process crash/hang; the original
   fail-OFF receipt remains failed, but automatic crash-OFF is no longer required.
   Document this exception before service/HTTPS ingress/token provisioning. No
   blind bench repeat, commissioned marker or source-forwarding activation is
   implied by the requirement change; remaining functional/deployment checks apply.

The next package is a driver commissioning test, not finished automation. Full
light controller installation will follow only after the driver gate is resolved.

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
