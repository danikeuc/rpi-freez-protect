# GPIO21 disconnected commissioning bench

Prepared after the owner authorized connecting the MCP source to the third relay,
with no lamp attached. This first package measures the remaining driver gate;
it does not install lighting services or enable camera forwarding.

## Required before running

Use trusted root@DietPi console, Raspberry Pi4Brev1.1 only. Both lamp mains and
valve24V must be physically disconnected. Select STOP on Dial shower page so
weather controller is USER_OFF/DRAIN. Fresh remote status before preparation
showed GPIO20/26 bothLOW; historical DRAIN receipts are insufficient.
The script validates local authenticated USER_OFF, persisted inhibition, actual
paired high/high, paired owner and known migrated daemon hash before requesting21.
Existing restricted SSH commands do not authorize this new bench; do not widen
permissions or run on Synology/LinuxVM.

## What is exercised

- Dedicated installed gpiod2.3 interpreter, fixed gpiochip0/offset21 only.
- Initial request inactive/high, half-secondON, commandedOFF, normal release.
- A second half-secondON, killed worker, then immediate released-high check.
- Final explicit inactive/high request and release even after a failed bench.
- Read-only gpiomem samples of20/21/26 every approximately2ms; pair must remain
  high/high output for every sample. Samples are point observations, not an
  oscilloscope trace or proof of no shorter transient/contact behavior.
- Worker stdin EOF or two-second command idle timeout performs OFF/release.
  SIGKILL intentionally tests the kernel release path, not a cleanup callback.

Any failure remains failure even when final recovery restoresOFF. No automatic
retry: /root/light-gpio21-commissioning.started is file-and-directory-fsynced
before first request. Retain this marker and evidence for assessment. Do not
remove it merely to rerun. No service restart, shower command, paired GPIO write,
Protect mutation, new device permission or commissioned marker is performed.

Evidence: private /root/light-gpio21-bench.* directory with receipt.json,
samples.json and sanitized diagnostic frames/private preflight log. Public receipt
contains phase/outcome only. If final_off_readback=false, keep both loads isolated
and investigate locally; no physical safe-state inference is justified.

A PASS permits review of target service installation; it is not complete hardware
acceptance. Reset/power loss, boot interval and actual lamp contact/wiring behavior
are not established. Camera forwarding remains observe until its own deployment
and acceptance steps complete.

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
